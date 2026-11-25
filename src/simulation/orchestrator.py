from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import random

from src.agents.inventory_agent import agente_controlo_inventario
from src.agents.logistics_agent import agente_logistica_doacao
from src.agents.pricing_agent import agente_dynamic_pricing
from src.csp.constraints import validar_regras_csp
from src.database.db_manager import GestorBaseDadosTemporal
from src.rag.retriever import RecuperadorRAG
from src.simulation.mock_db import calcular_preco_efetivo_lote
from src.simulation.weather_service import obter_meteorologia_atual

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
    rag_retriever: RecuperadorRAG,
    perturbacoes_ativas: list[str],
    data_ref: date,
    meteo: dict,
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
        "rag_retriever": rag_retriever,
        "perturbacoes_ativas": perturbacoes_ativas,
        "data_referencia": data_ref,
        "meteorologia": meteo,
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
        "contexto_rag": estado_grafo.get("contexto_rag", []),
    }

    return linha_tabela, log_card


def correr_simulacao(
    cenario_perturbacao: str,
    perturbacoes_ativas: list[str],
    modo_meteo: str = "Automático (Tempo Real - Coimbra)",
) -> dict:
    fecho_loja_2h = "A menos de 2 horas de fechar a loja." in perturbacoes_ativas
    gestor = GestorBaseDadosTemporal(total_produtos=200, seed=2026)
    data_ref = date.today()
    rag_retriever = RecuperadorRAG()
    meteo = obter_meteorologia_atual(modo_override=modo_meteo)

    catalogo_copia, lotes_copia = gestor.gerar_dataset_temporal(data_ref=data_ref)
    catalogo_map = {p["produto_id"]: p for p in catalogo_copia}

    # 1. Ajuste de procura pela meteorologia (Open-Meteo ou simulação)
    if meteo["fator_procura"] != 1.0:
        for p in catalogo_copia:
            if meteo["fator_procura"] < 1.0 or p.get("categoria") in ["bebidas", "fruta", "carne"]:
                p["vendas_medias_diarias"] = max(
                    0.2, round(p["vendas_medias_diarias"] * meteo["fator_procura"], 2)
                )

    # 2. Perturbações operacionais da sidebar
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

    dias_alvo_sacos = 2 if fecho_loja_2h else 1
    stock_total_padaria_urgente = sum(
        l["quantidade_disponivel"] * catalogo_map.get(l["produto_id"], {}).get("conteudo_liquido", 0.10)
        for l in lotes_copia
        if l["dias_para_expirar"] == dias_alvo_sacos
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
                        rag_retriever,
                        perturbacoes_ativas,
                        data_ref,
                        meteo,
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
        "meteorologia_ativa": meteo,
        "db_status": (db_ok, db_msg),
        "snapshot": snapshot,
    }

def formatar_numero_pt(valor: float, casas_decimais: int = 0) -> str:
    formatado = f"{valor:,.{casas_decimais}f}"
    return formatado.replace(",", " ").replace(".", ",")


def _simular_baseline_tradicional(
    catalogo_base: list[dict],
    lotes_iniciais: list[dict],
    plano_dias: list[dict],
) -> dict:
    """
    Simula a abordagem tradicional do retalho alimentar (etiqueta fixa):
    - Só aplica desconto a <= 2 dias da validade (30% a 2 dias, 50% a 1 dia);
    - Não usa elasticidade-preço, RAG, CSP, Sacos Surpresa nem encaminhamento para cozinha/ração;
    - Corre sobre o mesmo inventário inicial e exatos mesmos fatores aleatórios diários.
    """
    import copy

    rng = random.Random(2026)
    catalogo_map = {p["produto_id"]: p for p in catalogo_base}
    lotes_base = copy.deepcopy(lotes_iniciais)

    qvd_kg = 0.0
    qexp_kg = 0.0
    total_vendidas = 0.0
    total_desperdicadas = 0.0
    receita_total = 0.0
    custo_desperdicio = 0.0

    for dia_cfg in plano_dias:
        fator_dia = dia_cfg["fator_dia"]
        pico_stock = dia_cfg["pico_stock"]
        feriado_amanha = dia_cfg["feriado_amanha"]

        if pico_stock:
            for lote in lotes_base:
                prod = catalogo_map.get(lote["produto_id"], {})
                if prod.get("categoria") in ["carne", "fruta"] and lote["quantidade_disponivel"] > 0:
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] * 1.4, 1)

        # Regra estática tradicional de retalho (sem agentes, sem clima, sem elasticidade)
        for lote in lotes_base:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            prod = catalogo_map[lote["produto_id"]]
            if feriado_amanha and lote["dias_para_expirar"] <= 2:
                lote["dias_para_expirar"] = 1

            dias = lote["dias_para_expirar"]
            if dias == 2:
                lote["desconto_validade"] = 0.30
            elif dias == 1:
                lote["desconto_validade"] = 0.50
            else:
                lote["desconto_validade"] = 0.0

            _, preco_f = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_f
            lote["destino_final"] = "prateleira_desconto"

        # Mesma procura base do dia (mesma seed rng)
        lotes_por_prod: dict[str, list[dict]] = {}
        for l in lotes_base:
            if l["quantidade_disponivel"] > 0 and l.get("estado") != "expirado":
                lotes_por_prod.setdefault(l["produto_id"], []).append(l)

        for prod_id, _ in lotes_por_prod.items():
            prod = catalogo_map[prod_id]
            peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))
            elegiveis = obter_lotes_ativos_fefo(prod_id, lotes_por_prod)
            if not elegiveis:
                continue

            procura_base = prod.get("vendas_medias_diarias", 2.0) * fator_dia * rng.uniform(0.85, 1.15)
            for lote in elegiveis:
                if procura_base <= 0:
                    break
                desc_ativo = max(lote.get("desconto_validade", 0.0), prod.get("desconto_campanha", 0.0))
                elast = prod.get("elasticidade_preco", 1.2)
                procura_lote = procura_base * (1.0 + desc_ativo * elast)
                qtd_vendida = min(lote["quantidade_disponivel"], procura_lote)
                if prod.get("unidade_medida") != "kg":
                    qtd_vendida = float(int(round(qtd_vendida)))

                if qtd_vendida > 0:
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] - qtd_vendida, 2)
                    receita_total += qtd_vendida * lote.get("preco_final_atual", prod["pvp"])
                    total_vendidas += qtd_vendida
                    if lote.get("desconto_validade", 0.0) > 0:
                        qvd_kg += qtd_vendida * peso_unit
                    procura_base = max(0.0, procura_base - (qtd_vendida / (1.0 + desc_ativo * elast)))

        # Fecho do dia: expirações sem alternativa logística
        for lote in lotes_base:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            lote["dias_para_expirar"] -= 1
            if lote["dias_para_expirar"] <= 0:
                qtd_exp = lote["quantidade_disponivel"]
                prod = catalogo_map[lote["produto_id"]]
                peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))

                qexp_kg += qtd_exp * peso_unit
                total_desperdicadas += qtd_exp
                custo_desperdicio += qtd_exp * (prod["custo_aquisicao"] + prod["custo_descarte"])
                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "expirado"

    total_mov = max(1.0, total_vendidas + total_desperdicadas)
    qtar_kg = qvd_kg + qexp_kg
    ts_pct = (qvd_kg / max(0.01, qtar_kg)) * 100

    return {
        "ts_pct": round(ts_pct, 2),
        "taxa_desperdicio_pct": round((total_desperdicadas / total_mov) * 100, 2),
        "total_vendidas": round(total_vendidas, 1),
        "total_doadas_cozinha": 0.0,
        "total_desperdicadas": round(total_desperdicadas, 1),
        "receita_total": round(receita_total, 2),
        "custo_desperdicio": round(custo_desperdicio, 2),
        "qtar_kg": round(qtar_kg, 1),
    }


def simular_horizonte_temporal(
    dias_simulacao: int = 7,
    modo_meteo: str = "Automático (Tempo Real - Coimbra)",
    combinar_perturbacoes_aleatorias: bool = True,
) -> dict:
    """
    Executa uma simulação acelerada de N dias:
    - Avança o calendário dia a dia;
    - Injeta perturbações e condições meteorológicas variáveis;
    - Simula compras reais (FEFO + elasticidade-preço + Sacos Surpresa);
    - Regista unidades vendidas, encaminhadas (doação/cozinha) e desperdiçadas (expiradas);
    - Calcula a Taxa de Salvamento (TS = ((QVD + QD + QR) / QTAR) * 100) em kg;
    - Executa em paralelo a simulação Baseline Tradicional (30%/50%) sobre os mesmos dados.
    """
    import copy

    qvd_kg_total = 0.0   # Quantidade Vendida com Desconto (kg)
    qd_kg_total = 0.0    # Quantidade Doada (kg)
    qr_kg_total = 0.0    # Quantidade Reaproveitada: cozinha interna + ração animal (kg)
    qexp_kg_total = 0.0  # Quantidade em risco que expirou sem venda (kg)
    passos_execucao = []
    plano_dias = []

    rng = random.Random(2026)
    gestor = GestorBaseDadosTemporal(total_produtos=200, seed=2026)
    data_inicial = date.today()
    rag_retriever = RecuperadorRAG()
    catalogo_base, lotes_ativos = gestor.gerar_dataset_temporal(data_ref=data_inicial)
    lotes_iniciais_copia = copy.deepcopy(lotes_ativos)
    catalogo_map = {p["produto_id"]: p for p in catalogo_base}

    cenarios_possiveis = [
        [],
        ["A menos de 2 horas de fechar a loja."],
        ["Quebra Repentina de Clientes (-50% Procura)"],
        ["Feriado / Loja Fechada Amanhã (Urgência Máxima)"],
        ["Pico de Stock Excedente em Frutas e Carne"],
        ["A menos de 2 horas de fechar a loja.", "Quebra Repentina de Clientes (-50% Procura)"],
    ]
    modos_meteo_ciclo = [
        modo_meteo,
        "Simular: Chuva Intensa / Temporal",
        "Simular: Calor Elevado (> 30°C)",
        "Automático (Tempo Real - Coimbra)",
    ]

    evolucao_diaria = []
    desperdicio_por_categoria: dict[str, float] = {}
    custo_desperdicio_total = 0.0
    receita_total_recuperada = 0.0
    total_un_vendidas = 0.0
    total_un_doadas_cozinha = 0.0
    total_un_desperdicadas = 0.0

    for dia_idx in range(dias_simulacao):
        data_corrente = date.fromordinal(data_inicial.toordinal() + dia_idx)

        if combinar_perturbacoes_aleatorias:
            perturbs_dia = (
                cenarios_possiveis[dia_idx % len(cenarios_possiveis)]
                if dia_idx % 2 == 1
                else rng.choice(cenarios_possiveis[:3])
            )
            meteo_dia_modo = modos_meteo_ciclo[dia_idx % len(modos_meteo_ciclo)]
        else:
            perturbs_dia = []
            meteo_dia_modo = modo_meteo

        fecho_2h = "A menos de 2 horas de fechar a loja." in perturbs_dia
        quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbs_dia
        feriado_amanha = "Feriado / Loja Fechada Amanhã (Urgência Máxima)" in perturbs_dia
        pico_stock = "Pico de Stock Excedente em Frutas e Carne" in perturbs_dia
        meteo = obter_meteorologia_atual(modo_override=meteo_dia_modo)

        fator_dia = meteo["fator_procura"] * (0.50 if quebra_clientes else 1.0)
        plano_dias.append({
            "fator_dia": fator_dia,
            "pico_stock": pico_stock,
            "feriado_amanha": feriado_amanha,
        })

        if pico_stock:
            for lote in lotes_ativos:
                prod = catalogo_map.get(lote["produto_id"], {})
                if prod.get("categoria") in ["carne", "fruta"] and lote["quantidade_disponivel"] > 0:
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] * 1.4, 1)

        dias_alvo_sacos = 2 if fecho_2h else 1
        stock_padaria_urgente = sum(
            l["quantidade_disponivel"] * catalogo_map.get(l["produto_id"], {}).get("conteudo_liquido", 0.10)
            for l in lotes_ativos
            if l["dias_para_expirar"] == dias_alvo_sacos
            and l["quantidade_disponivel"] > 0
            and catalogo_map.get(l["produto_id"], {}).get("categoria") == "padaria"
        )

        # 1. Decisão dos Agentes + CSP para lotes críticos do dia
        tarefas = []
        for idx, lote in enumerate(lotes_ativos):
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            prod = catalogo_map[lote["produto_id"]]
            if feriado_amanha and lote["dias_para_expirar"] <= 2:
                lote["dias_para_expirar"] = 1

            if lote["dias_para_expirar"] <= 5:
                tarefas.append((idx, lote, prod))
            else:
                lote["desconto_validade"] = 0.0
                _, preco_f = calcular_preco_efetivo_lote(lote, prod)
                lote["preco_final_atual"] = preco_f
                lote["destino_final"] = "prateleira_desconto"

        if tarefas:
            with ThreadPoolExecutor(max_workers=8) as executor:
                futs = [
                    executor.submit(
                        _processar_lote_critico,
                        lote,
                        prod,
                        catalogo_base,
                        stock_padaria_urgente,
                        fecho_2h,
                        rag_retriever,
                        perturbs_dia,
                        data_corrente,
                        meteo,
                    )
                    for _, lote, prod in tarefas
                ]
                for fut in futs:
                    fut.result()

        # 2. Simulação de Vendas do Dia (FEFO + Elasticidade + Perturbações)
        lotes_por_prod: dict[str, list[dict]] = {}
        for l in lotes_ativos:
            if l["quantidade_disponivel"] > 0 and l.get("estado") != "expirado":
                lotes_por_prod.setdefault(l["produto_id"], []).append(l)

        vendidas_dia = 0.0
        doadas_dia = 0.0
        desperdicadas_dia = 0.0
        receita_dia = 0.0

        for prod_id, _ in lotes_por_prod.items():
            prod = catalogo_map[prod_id]
            peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))
            elegiveis = obter_lotes_ativos_fefo(prod_id, lotes_por_prod)
            if not elegiveis:
                continue

            procura_base = prod.get("vendas_medias_diarias", 2.0) * fator_dia * rng.uniform(0.85, 1.15)

            for lote in elegiveis:
                if procura_base <= 0:
                    break
                desc_ativo = max(lote.get("desconto_validade", 0.0), prod.get("desconto_campanha", 0.0))
                elast = prod.get("elasticidade_preco", 1.2)
                procura_lote = procura_base * (1.0 + desc_ativo * elast)
                qtd_vendida = min(lote["quantidade_disponivel"], procura_lote)
                if prod.get("unidade_medida") != "kg":
                    qtd_vendida = float(int(round(qtd_vendida)))

                if qtd_vendida > 0:
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] - qtd_vendida, 2)
                    receita_dia += qtd_vendida * lote.get("preco_final_atual", prod["pvp"])
                    vendidas_dia += qtd_vendida
                    if lote.get("desconto_validade", 0.0) > 0:
                        qvd_kg_total += qtd_vendida * peso_unit
                    procura_base = max(0.0, procura_base - (qtd_vendida / (1.0 + desc_ativo * elast)))

        # Vendas de Sacos Surpresa e encaminhamento para Cozinha/Doação/Ração
        sacos_dia = construir_sacos_surpresa_equilibrados(lotes_ativos, catalogo_map, peso_alvo_kg=0.50, max_sacos=10)
        taxa_venda_sacos = 0.65 if quebra_clientes else 0.90
        for saco in sacos_dia:
            if rng.random() <= taxa_venda_sacos:
                receita_dia += saco["preco_final"]
                qvd_kg_total += saco["peso_kg"]
                for lid, q_cons in saco["lotes_consumo"].items():
                    for l in lotes_ativos:
                        if l["lote_id"] == lid:
                            abat = min(l["quantidade_disponivel"], q_cons)
                            l["quantidade_disponivel"] = round(l["quantidade_disponivel"] - abat, 2)
                            vendidas_dia += abat

        for lote in lotes_ativos:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            dest = lote.get("destino_final", "prateleira_desconto")
            if dest in ["cozinha_interna", "doacao_externa", "racao_animal"]:
                prod = catalogo_map[lote["produto_id"]]
                peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))
                kg_lote = lote["quantidade_disponivel"] * peso_unit

                if dest == "doacao_externa":
                    qd_kg_total += kg_lote
                else:
                    qr_kg_total += kg_lote

                doadas_dia += lote["quantidade_disponivel"]
                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "encaminhado"

        # 3. Fim do Dia: Avançar 1 dia na validade e contabilizar desperdício real
        for lote in lotes_ativos:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            lote["dias_para_expirar"] -= 1
            if lote["dias_para_expirar"] <= 0:
                qtd_exp = lote["quantidade_disponivel"]
                prod = catalogo_map[lote["produto_id"]]
                peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))
                cat = prod.get("categoria", "outros").capitalize()

                qexp_kg_total += qtd_exp * peso_unit
                desperdicadas_dia += qtd_exp
                desperdicio_por_categoria[cat] = round(desperdicio_por_categoria.get(cat, 0.0) + qtd_exp, 1)
                custo_desperdicio_total += qtd_exp * (prod["custo_aquisicao"] + prod["custo_descarte"])

                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "expirado"
                lote["dia_expiracao_sim"] = dia_idx + 1

        total_un_vendidas += vendidas_dia
        total_un_doadas_cozinha += doadas_dia
        total_un_desperdicadas += desperdicadas_dia
        receita_total_recuperada += receita_dia

        evolucao_diaria.append({
            "Dia": f"Dia {dia_idx + 1} ({data_corrente.strftime('%d/%m')})",
            "Cenário / Perturbações": ", ".join(perturbs_dia) if perturbs_dia else "Operação Normal",
            "Clima": meteo["descricao"],
            "Vendidas": round(vendidas_dia, 1),
            "Doação / Cozinha": round(doadas_dia, 1),
            "Desperdiçadas (Expiradas)": round(desperdicadas_dia, 1),
            "Receita (€)": round(receita_dia, 2),
        })

        lotes_expirados_nomes = [
            f"{catalogo_map[l['produto_id']]['nome']} ({l['lote_id']})"
            for l in lotes_ativos
            if l.get("estado") == "expirado" and l.get("dia_expiracao_sim") == dia_idx + 1
        ]

        passos_execucao.append({
            "dia_num": dia_idx + 1,
            "data_str": data_corrente.strftime("%d/%m/%Y"),
            "cenario": ", ".join(perturbs_dia) if perturbs_dia else "Operação Normal",
            "clima": meteo["descricao"],
            "fator_procura": round(fator_dia, 2),
            "lotes_analisados_agentes": len(tarefas),
            "sacos_criados": len(sacos_dia),
            "vendidas": round(vendidas_dia, 1),
            "doadas": round(doadas_dia, 1),
            "desperdicadas": round(desperdicadas_dia, 1),
            "receita": round(receita_dia, 2),
            "exemplos_expirados": lotes_expirados_nomes[:4],
        })

    total_movimentado = max(1.0, total_un_vendidas + total_un_doadas_cozinha + total_un_desperdicadas)
    taxa_desperdicio_pct = (total_un_desperdicadas / total_movimentado) * 100

    qtar_kg_total = qvd_kg_total + qd_kg_total + qr_kg_total + qexp_kg_total
    ts_pct = ((qvd_kg_total + qd_kg_total + qr_kg_total) / max(0.01, qtar_kg_total)) * 100

    baseline = _simular_baseline_tradicional(catalogo_base, lotes_iniciais_copia, plano_dias)

    return {
        "dias_simulados": dias_simulacao,
        "total_vendidas": round(total_un_vendidas, 1),
        "total_doadas_cozinha": round(total_un_doadas_cozinha, 1),
        "total_desperdicadas": round(total_un_desperdicadas, 1),
        "taxa_desperdicio_pct": round(taxa_desperdicio_pct, 2),
        "receita_total": round(receita_total_recuperada, 2),
        "custo_desperdicio": round(custo_desperdicio_total, 2),
        "qvd_kg": round(qvd_kg_total, 1),
        "qd_kg": round(qd_kg_total, 1),
        "qr_kg": round(qr_kg_total, 1),
        "qtar_kg": round(qtar_kg_total, 1),
        "ts_pct": round(ts_pct, 2),
        "evolucao_diaria": evolucao_diaria,
        "desperdicio_por_categoria": desperdicio_por_categoria,
        "passos_execucao": passos_execucao,
        "comparacao_baseline": baseline,
    }

def _simular_baseline_tradicional(
    catalogo_base: list[dict],
    lotes_iniciais: list[dict],
    plano_dias: list[dict],
) -> dict:
    """
    Simula a abordagem tradicional do retalho alimentar (etiqueta fixa):
    - Só aplica desconto a <= 2 dias da validade (30% a 2 dias, 50% a 1 dia);
    - Não usa elasticidade-preço, RAG, CSP, Sacos Surpresa nem encaminhamento para cozinha/ração;
    - Corre sobre o mesmo inventário inicial e exatos mesmos fatores aleatórios diários.
    """
    import copy

    rng = random.Random(2026)
    catalogo_map = {p["produto_id"]: p for p in catalogo_base}
    lotes_base = copy.deepcopy(lotes_iniciais)

    qvd_kg = 0.0
    qexp_kg = 0.0
    total_vendidas = 0.0
    total_desperdicadas = 0.0
    receita_total = 0.0
    custo_desperdicio = 0.0

    for dia_cfg in plano_dias:
        fator_dia = dia_cfg["fator_dia"]
        pico_stock = dia_cfg["pico_stock"]
        feriado_amanha = dia_cfg["feriado_amanha"]

        if pico_stock:
            for lote in lotes_base:
                prod = catalogo_map.get(lote["produto_id"], {})
                if prod.get("categoria") in ["carne", "fruta"] and lote["quantidade_disponivel"] > 0:
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] * 1.4, 1)

        # Regra estática tradicional de retalho (sem agentes, sem clima, sem elasticidade)
        for lote in lotes_base:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            prod = catalogo_map[lote["produto_id"]]
            if feriado_amanha and lote["dias_para_expirar"] <= 2:
                lote["dias_para_expirar"] = 1

            dias = lote["dias_para_expirar"]
            if dias == 2:
                lote["desconto_validade"] = 0.30
            elif dias == 1:
                lote["desconto_validade"] = 0.50
            else:
                lote["desconto_validade"] = 0.0

            _, preco_f = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_f
            lote["destino_final"] = "prateleira_desconto"

        # Mesma procura base do dia (mesma seed rng)
        lotes_por_prod: dict[str, list[dict]] = {}
        for l in lotes_base:
            if l["quantidade_disponivel"] > 0 and l.get("estado") != "expirado":
                lotes_por_prod.setdefault(l["produto_id"], []).append(l)

        for prod_id, _ in lotes_por_prod.items():
            prod = catalogo_map[prod_id]
            peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))
            elegiveis = obter_lotes_ativos_fefo(prod_id, lotes_por_prod)
            if not elegiveis:
                continue

            procura_base = prod.get("vendas_medias_diarias", 2.0) * fator_dia * rng.uniform(0.85, 1.15)
            for lote in elegiveis:
                if procura_base <= 0:
                    break
                desc_ativo = max(lote.get("desconto_validade", 0.0), prod.get("desconto_campanha", 0.0))
                elast = prod.get("elasticidade_preco", 1.2)
                procura_lote = procura_base * (1.0 + desc_ativo * elast)
                qtd_vendida = min(lote["quantidade_disponivel"], procura_lote)
                if prod.get("unidade_medida") != "kg":
                    qtd_vendida = float(int(round(qtd_vendida)))

                if qtd_vendida > 0:
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] - qtd_vendida, 2)
                    receita_total += qtd_vendida * lote.get("preco_final_atual", prod["pvp"])
                    total_vendidas += qtd_vendida
                    if lote.get("desconto_validade", 0.0) > 0:
                        qvd_kg += qtd_vendida * peso_unit
                    procura_base = max(0.0, procura_base - (qtd_vendida / (1.0 + desc_ativo * elast)))

        # Fecho do dia: expirações sem alternativa logística
        for lote in lotes_base:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") == "expirado":
                continue
            lote["dias_para_expirar"] -= 1
            if lote["dias_para_expirar"] <= 0:
                qtd_exp = lote["quantidade_disponivel"]
                prod = catalogo_map[lote["produto_id"]]
                peso_unit = 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))

                qexp_kg += qtd_exp * peso_unit
                total_desperdicadas += qtd_exp
                custo_desperdicio += qtd_exp * (prod["custo_aquisicao"] + prod["custo_descarte"])
                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "expirado"

    total_mov = max(1.0, total_vendidas + total_desperdicadas)
    qtar_kg = qvd_kg + qexp_kg
    ts_pct = (qvd_kg / max(0.01, qtar_kg)) * 100

    return {
        "ts_pct": round(ts_pct, 2),
        "taxa_desperdicio_pct": round((total_desperdicadas / total_mov) * 100, 2),
        "total_vendidas": round(total_vendidas, 1),
        "total_doadas_cozinha": 0.0,
        "total_desperdicadas": round(total_desperdicadas, 1),
        "receita_total": round(receita_total, 2),
        "custo_desperdicio": round(custo_desperdicio, 2),
        "qtar_kg": round(qtar_kg, 1),
    }