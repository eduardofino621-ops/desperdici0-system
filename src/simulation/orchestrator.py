from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import random

from src.agents.inventory_agent import agente_controlo_inventario
from src.agents.logistics_agent import agente_logistica_doacao
from src.agents.pricing_agent import agente_dynamic_pricing
from src.csp.constraints import validar_regras_csp
from src.database.db_manager import GestorBaseDadosTemporal
from src.simulation.mock_db import calcular_preco_efetivo_lote

MAPA_DESTINOS = {
    "prateleira_desconto": "Prateleira (Etiqueta ESL)",
    "sacos_surpresa": "Sacos Surpresa (Fim de Dia)",
    "cozinha_interna": "Cozinha Interna (Retirado)",
    "descarte_obrigatorio": "Descarte Obrigatório",
    "doacao_externa": "Doação Externa (Instituições de Caridade)",
    "racao_animal": "Doação Externa (Parceria com Produção de Ração Animal)",
}


def formatar_eur(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",") + "€"


def sublinhar_texto(texto: str) -> str:
    return "".join(f"{c}\u0332" for c in texto)


def formatar_stock(qtd: float, unidade: str) -> str:
    return f"{qtd:.1f} {unidade}" if unidade == "kg" else f"{int(round(qtd))} {unidade}"


def formatar_destino_legivel(destino: str) -> str:
    return MAPA_DESTINOS.get(destino, destino.replace("_", " ").title())


def classificar_decisao_lote(lote: dict) -> str:
    destino = lote.get("destino_final", "prateleira_desconto")
    mapa_classe = {
        "sacos_surpresa": "Sacos Surpresa",
        "cozinha_interna": "Cozinha Interna",
        "doacao_externa": "Doação (Caridade)",
        "racao_animal": "Doação (Ração Animal)",
        "descarte_obrigatorio": "Descarte Obrigatório",
    }
    if destino in mapa_classe:
        return mapa_classe[destino]
    return "Desc. Validade (ESL)" if lote.get("desconto_validade", 0.0) > 0 else "Prateleira (Normal/Campanha)"


def obter_lotes_ativos_fefo(produto_id: str, lotes_por_prod: dict[str, list[dict]]) -> list[dict]:
    elegiveis = [
        l for l in lotes_por_prod.get(produto_id, [])
        if l.get("quantidade_disponivel", 0.0) > 0
        and l.get("estado") not in ["esgotado", "expirado"]
        and l.get("destino_final", "prateleira_desconto") == "prateleira_desconto"
    ]
    elegiveis.sort(key=lambda x: (x.get("dias_para_expirar", 99), x.get("data_validade", "9999-12-31")))
    return elegiveis


def construir_sacos_surpresa_equilibrados(
    lotes: list[dict],
    catalogo_map: dict[str, dict],
    peso_alvo_kg: float = 0.50,
    max_sacos: int = 10,
) -> list[dict]:
    pool_unidades = []
    for lote in lotes:
        if lote.get("destino_final") != "sacos_surpresa":
            continue
        qtd = int(round(lote.get("quantidade_disponivel", 0)))
        if qtd <= 0:
            continue
        prod = catalogo_map.get(lote["produto_id"], {})
        pvp = prod.get("pvp", 0.0)
        peso_kg = float(prod.get("conteudo_liquido", 0.10))
        desc = max(lote.get("desconto_validade", 0.0), prod.get("desconto_campanha", 0.0))
        preco_un = round(pvp * (1 - desc), 2)
        for _ in range(qtd):
            pool_unidades.append({
                "lote_id": lote["lote_id"],
                "nome": prod.get("nome", "Pão"),
                "pvp": pvp,
                "preco_final": preco_un,
                "peso_kg": peso_kg,
            })

    if sum(u["peso_kg"] for u in pool_unidades) < peso_alvo_kg:
        return []

    rng = random.Random(2026)
    rng.shuffle(pool_unidades)

    sacos, saco_atual, peso_atual = [], [], 0.0
    for item in pool_unidades:
        if len(sacos) >= max_sacos:
            break
        saco_atual.append(item)
        peso_atual += item["peso_kg"]

        if peso_atual >= peso_alvo_kg:
            pvp_total = round(sum(x["pvp"] for x in saco_atual), 2)
            preco_total = round(sum(x["preco_final"] for x in saco_atual), 2)
            desc_pct = int(round((1 - preco_total / max(0.01, pvp_total)) * 100))
            lotes_consumo: dict[str, float] = {}
            for x in saco_atual:
                lotes_consumo[x["lote_id"]] = lotes_consumo.get(x["lote_id"], 0.0) + 1.0

            sacos.append({
                "titulo": "Saco Surpresa Padaria",
                "preco_base": pvp_total,
                "preco_final": preco_total,
                "desconto_pct": desc_pct,
                "peso_kg": round(peso_atual, 2),
                "lotes_consumo": lotes_consumo,
                "vendido": False,
            })
            saco_atual, peso_atual = [], 0.0

    return sacos


def consolidar_sacos_para_esl(sacos_ativos: list[dict]) -> list[dict]:
    agrupados: dict[tuple, dict] = {}
    for saco in sacos_ativos:
        chave = (saco["titulo"], saco["preco_base"], saco["desconto_pct"], saco["preco_final"])
        if chave not in agrupados:
            agrupados[chave] = {
                "titulo": saco["titulo"],
                "preco_base": saco["preco_base"],
                "desconto_pct": saco["desconto_pct"],
                "preco_final": saco["preco_final"],
                "sacos_instancias": [],
            }
        agrupados[chave]["sacos_instancias"].append(saco)
    return list(agrupados.values())


def _processar_lote_critico(
    lote: dict,
    prod: dict,
    catalogo_copia: list[dict],
    stock_total_padaria_urgente: float,
    fecho_loja_2h: bool,
) -> tuple[dict, dict]:
    pvp = prod.get("pvp", 0.0)
    desc_campanha = prod.get("desconto_campanha", 0.0)
    periodo_campanha = prod.get("periodo_campanha", "")
    unidade = prod.get("unidade_medida", "un")
    dias = lote["dias_para_expirar"]

    estado_grafo = {
        "lote_atual": lote,
        "produto_catalogo": prod,
        "catalogo_produtos": catalogo_copia,
        "fecho_loja_2h": fecho_loja_2h,
    }

    res_inv = agente_controlo_inventario(estado_grafo)
    estado_grafo.update(res_inv)

    res_log = agente_logistica_doacao(estado_grafo)
    estado_grafo.update(res_log)

    res_pri = agente_dynamic_pricing(estado_grafo)
    estado_grafo.update(res_pri)

    val_csp = validar_regras_csp(
        lote=lote,
        desconto_proposto=res_pri["desconto_proposto"],
        destino=res_log["destino_proposto"],
        produto_catalogo=prod,
        stock_total_sacos=stock_total_padaria_urgente,
        fecho_loja_2h=fecho_loja_2h,
    )

    desc_final = val_csp["desconto_ajustado"]
    destino_final = val_csp["destino_ajustado"]
    lote["desconto_csp_aprovado"] = desc_final
    lote["desconto_validade"] = (
        desc_final
        if destino_final in ["prateleira_desconto", "sacos_surpresa"] and desc_final > desc_campanha
        else 0.0
    )

    desc_efetivo, preco_final = calcular_preco_efetivo_lote(lote, prod)
    lote["preco_final_atual"] = preco_final
    lote["destino_final"] = destino_final
    lote["estado_csp"] = "Aprovado" if val_csp["valido"] else "Ajustado pelo CSP"
    if lote["desconto_validade"] >= 0.35:
        lote["estado"] = "promocao_critica"

    preco_exibido_tabela = (
        "Retirado (Cozinha/Doação/Ração)"
        if destino_final in ["cozinha_interna", "doacao_externa", "racao_animal"]
        else formatar_eur(preco_final)
    )

    linha_tabela = {
        "Lote": lote["lote_id"],
        "Cód. Artigo": prod["produto_id"],
        "Produto": prod["nome"],
        "Categoria": prod["categoria"].capitalize(),
        "Stock": formatar_stock(lote["quantidade_disponivel"], unidade),
        "Validade": date.fromisoformat(lote["data_validade"]),
        "Dias": int(dias),
        "PVP": formatar_eur(pvp),
        "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
        "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
        "Desc. Validade": f"-{int(lote['desconto_validade'] * 100)}%" if lote["desconto_validade"] > 0 else "—",
        "Preço Ativo": preco_exibido_tabela,
        "Destino Operacional": formatar_destino_legivel(destino_final),
        "Consultar Validação CSP": f"✅ {sublinhar_texto('Aprovado')}" if val_csp["valido"] else f"🛡️ {sublinhar_texto('Ajustado')}",
    }

    log_card = {
        "lote_id": lote["lote_id"],
        "produto_id": prod["produto_id"],
        "nome": prod["nome"],
        "categoria": prod["categoria"].capitalize(),
        "dias": dias,
        "quantidade": formatar_stock(lote["quantidade_disponivel"], unidade),
        "excesso": f"{res_inv.get('excesso_estimado', 0.0):.1f} {unidade}",
        "risco_critico": res_inv.get("risco_critico", False),
        "parecer_inventario": res_inv["parecer_inventario"],
        "destino_proposto": formatar_destino_legivel(res_log["destino_proposto"]),
        "razao_logistica": res_log["razao_logistica"],
        "desconto_proposto": f"{int(res_pri['desconto_proposto'] * 100)}%",
        "raciocinio_pricing": res_pri["raciocinio_pricing"],
        "csp_valido": val_csp["valido"],
        "csp_erros": val_csp["erros"],
        "desconto_final": f"{int(desc_efetivo * 100)}%",
        "preco_final": preco_exibido_tabela,
        "destino_final": formatar_destino_legivel(destino_final),
    }

    return linha_tabela, log_card


def correr_simulacao(cenario_perturbacao: str, perturbacoes_ativas: list[str]) -> dict:
    fecho_loja_2h = "A menos de 2 horas de fechar a loja." in perturbacoes_ativas
    gestor = GestorBaseDadosTemporal(total_produtos=200, seed=2026)
    data_ref = date.today()
    catalogo_copia, lotes_copia = gestor.gerar_dataset_temporal(data_ref=data_ref)
    catalogo_map = {p["produto_id"]: p for p in catalogo_copia}

    if "Quebra Repentina de Clientes (-50% Procura)" in perturbacoes_ativas:
        for p in catalogo_copia:
            p["vendas_medias_diarias"] = max(0.2, round(p["vendas_medias_diarias"] * 0.5, 2))
    if "Feriado / Loja Fechada Amanhã (Urgência Máxima)" in perturbacoes_ativas:
        for lote in lotes_copia:
            if lote["dias_para_expirar"] <= 3:
                lote["dias_para_expirar"] = 1
                lote["data_validade"] = data_ref.isoformat()
    if "Pico de Stock Excedente em Frutas e Carne" in perturbacoes_ativas:
        for lote in lotes_copia:
            prod = catalogo_map.get(lote["produto_id"], {})
            if prod.get("categoria") in ["carne", "fruta"]:
                nova_qtd = lote["quantidade_disponivel"] * 2.5
                lote["quantidade_disponivel"] = (
                    round(nova_qtd, 1) if prod.get("unidade_medida") == "kg" else int(round(nova_qtd))
                )

    stock_total_padaria_urgente = sum(
        l["quantidade_disponivel"] * catalogo_map.get(l["produto_id"], {}).get("conteudo_liquido", 0.10)
        for l in lotes_copia
        if l["dias_para_expirar"] <= 1
        and l["quantidade_disponivel"] > 0
        and catalogo_map.get(l["produto_id"], {}).get("categoria") == "padaria"
    )

    resultados_lote: list[dict | None] = [None] * len(lotes_copia)
    logs_cards: list[dict] = []
    tarefas_criticas: list[tuple[int, dict, dict]] = []

    for idx, lote in enumerate(lotes_copia):
        prod = catalogo_map.get(lote["produto_id"], {})
        dias = lote["dias_para_expirar"]

        if dias > 5:
            pvp = prod.get("pvp", 0.0)
            desc_campanha = prod.get("desconto_campanha", 0.0)
            periodo_campanha = prod.get("periodo_campanha", "")
            unidade = prod.get("unidade_medida", "un")

            lote["desconto_validade"] = 0.0
            lote["desconto_csp_aprovado"] = 0.0
            _, preco_final = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_final
            lote["destino_final"] = "prateleira_desconto"
            lote["estado_csp"] = "Aprovado"

            resultados_lote[idx] = {
                "Lote": lote["lote_id"],
                "Cód. Artigo": prod["produto_id"],
                "Produto": prod["nome"],
                "Categoria": prod["categoria"].capitalize(),
                "Stock": formatar_stock(lote["quantidade_disponivel"], unidade),
                "Validade": date.fromisoformat(lote["data_validade"]),
                "Dias": int(dias),
                "PVP": formatar_eur(pvp),
                "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
                "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
                "Desc. Validade": "—",
                "Preço Ativo": formatar_eur(preco_final),
                "Destino Operacional": "Prateleira (Etiqueta ESL)",
                "Consultar Validação CSP": f"✅ {sublinhar_texto('Aprovado')}",
            }
        else:
            tarefas_criticas.append((idx, lote, prod))

    if tarefas_criticas:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futuros = [
                (
                    idx,
                    executor.submit(
                        _processar_lote_critico,
                        lote,
                        prod,
                        catalogo_copia,
                        stock_total_padaria_urgente,
                        fecho_loja_2h,
                    ),
                )
                for idx, lote, prod in tarefas_criticas
            ]
            for idx, fut in futuros:
                linha_tabela, log_card = fut.result()
                resultados_lote[idx] = linha_tabela
                logs_cards.append(log_card)

    sacos_surpresa = construir_sacos_surpresa_equilibrados(lotes_copia, catalogo_map, peso_alvo_kg=0.50, max_sacos=10)
    db_ok, db_msg = gestor.registar_telemetria_sqlite(data_ref, lotes_copia, cenario_perturbacao)

    total_prods = len(catalogo_copia)
    prods_validade_curta = len({l["produto_id"] for l in lotes_copia if l["dias_para_expirar"] <= 5})
    prods_campanha = sum(1 for p in catalogo_copia if p["desconto_campanha"] > 0)
    lotes_desc_val = sum(
        1 for l in lotes_copia if l.get("desconto_validade", 0.0) > 0 and l["quantidade_disponivel"] > 0
    )
    ajustes_csp = sum(1 for l in lotes_copia if l.get("estado_csp") != "Aprovado")

    registos_decisao = [
        {
            "Categoria": catalogo_map.get(l["produto_id"], {}).get("categoria", "outros").capitalize(),
            "Decisão": classificar_decisao_lote(l),
            "Dias": int(l["dias_para_expirar"]),
        }
        for l in lotes_copia
    ]

    snapshot = {
        "cenario": cenario_perturbacao,
        "hora": datetime.now().strftime("%H:%M"),
        "data_str": data_ref.strftime("%d/%m/%Y"),
        "kpis": {
            "total_prods": total_prods,
            "total_lotes": len(lotes_copia),
            "prods_validade_curta": prods_validade_curta,
            "pct_validade_curta": (prods_validade_curta / max(1, total_prods)) * 100,
            "prods_campanha": prods_campanha,
            "pct_campanha": (prods_campanha / max(1, total_prods)) * 100,
            "lotes_desc_val": lotes_desc_val,
            "ajustes_csp": ajustes_csp,
        },
        "registos_decisao": registos_decisao,
    }

    return {
        "resultados_simulacao": resultados_lote,
        "logs_estruturados": logs_cards,
        "logs_por_lote": {item["lote_id"]: item for item in logs_cards},
        "lotes_simulados": lotes_copia,
        "catalogo_simulado": catalogo_copia,
        "sacos_surpresa_lista": sacos_surpresa,
        "cenario_ativo": cenario_perturbacao,
        "data_referencia_ativa": data_ref,
        "db_status": (db_ok, db_msg),
        "snapshot": snapshot,
    }