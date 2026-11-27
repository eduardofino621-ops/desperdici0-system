import copy
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import random

from src.agents.inventory_agent import _detetar_chuva_temporal, agente_controlo_inventario
from src.agents.logistics_agent import agente_logistica_doacao
from src.agents.pricing_agent import agente_dynamic_pricing
from src.csp.constraints import (
    CATEGORIAS_PADARIA_PASTELARIA,
    _normalizar_categoria,
    eh_elegivel_saco_padaria,
    validar_regras_csp,
)
from src.database.db_manager import GestorBaseDadosTemporal
from src.rag.retriever import RecuperadorRAG
from src.simulation.mock_db import calcular_preco_efetivo_lote
from src.simulation.weather_service import obter_meteorologia_atual

CATEGORIAS_EXCLUIDAS_LIDL = frozenset({})

SEED_SIMULACAO_PADRAO = 43
SEED_CATALOGO_BASE = 2026

_CACHE_DATASET_BASE: dict[tuple[int, int, str], tuple[list[dict], list[dict]]] = {}
_CACHE_METEO_AUTO: dict[str, dict] = {}
_CACHE_RAG: dict[tuple[str, int], RecuperadorRAG] = {}
_TELEMETRIA_REGISTADA: set[tuple[str, str]] = set()

MAPA_DESTINOS = {
    "prateleira_desconto": "Prateleira (Etiqueta ESL)",
    "sacos_surpresa": "Sacos Surpresa",
    "cozinha_interna": "Cozinha Interna (Retirado)",
    "descarte_obrigatorio": "Desperdício (Ida para o Lixo)",
    "doacao_externa": "Doação Externa (Instituições de Caridade)",
    "racao_animal": "Doação Externa (Parceria com Produção de Ração Animal)",
}

DESTINOS_NAO_DESPERDICIO = [
    "Vendido (Desconto/Saco)",
    "Doação / Cozinha",
    "Ração / Valorização",
]

PARAMETROS_LIDL = {
    "desconto_dll": 0.30,
    "desconto_ultimo_dia": 0.50,
    "unidades_por_saco": 5,
    "contribuicao_social_saco": 0.10,
    "categorias_saco": ("padaria", "pastelaria"),
    "categorias_racao": ("padaria", "pastelaria"),
    "dias_dll": 2,
    "desconto_saco": 0.50,
    "quota_saco": 0.40,
    "fator_janela_saco": 0.85,
    "categorias_doacao": ("fruta", "legumes", "laticinios", "padaria", "pastelaria"),
    "taxa_doacao": 0.45,
    "taxa_doacao_preferencia": 0.35,
    "taxa_racao": 0.40,
    "fator_pescado_feriado": 1.15,
    "reposicao_automatica": False,
    "cobertura_dias": 2.0,
    "aumento_pico": 0.40,
    "semente": SEED_SIMULACAO_PADRAO,
}

_ESTADOS_FORA = ("esgotado", "expirado", "valorizado", "doado_realimenta")


def _normalizar_catalogo_e_lotes(
    catalogo: list[dict],
    lotes: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Normaliza categorias mantendo todos os produtos e lotes no inventário/KPIs iniciais."""
    catalogo_norm: list[dict] = []
    for p in catalogo:
        p_norm = dict(p)
        p_norm["categoria"] = _normalizar_categoria(p_norm.get("categoria"), default="outros")
        catalogo_norm.append(p_norm)

    lotes_norm = [copy.deepcopy(l) for l in lotes]
    return catalogo_norm, lotes_norm


def _obter_dataset_base_deterministico(
    gestor: GestorBaseDadosTemporal,
    data_ref: date,
    total_produtos: int = 200,
    seed: int = SEED_CATALOGO_BASE,
) -> tuple[list[dict], list[dict]]:
    """Gera uma única vez e reutiliza o mesmo catálogo e lotes iniciais para garantir reprodutibilidade."""
    chave = (total_produtos, seed, data_ref.isoformat())
    if chave not in _CACHE_DATASET_BASE:
        gestor_base = GestorBaseDadosTemporal(
            total_produtos=total_produtos,
            seed=seed,
            db_path=str(gestor.db_path),
        )
        estado_global_anterior = random.getstate()
        random.seed(seed)
        try:
            catalogo_raw, lotes_raw = gestor_base.gerar_dataset_temporal(data_ref=data_ref)
        finally:
            random.setstate(estado_global_anterior)
        _CACHE_DATASET_BASE[chave] = _normalizar_catalogo_e_lotes(catalogo_raw, lotes_raw)

    cat_cached, lotes_cached = _CACHE_DATASET_BASE[chave]
    return copy.deepcopy(cat_cached), copy.deepcopy(lotes_cached)


def _obter_rag_deterministico(data_ref: date, seed: int = SEED_SIMULACAO_PADRAO) -> RecuperadorRAG:
    chave = (data_ref.isoformat(), seed)
    if chave not in _CACHE_RAG:
        _CACHE_RAG[chave] = RecuperadorRAG()
    return _CACHE_RAG[chave]


def _obter_meteo_deterministica(modo_override: str) -> dict:
    """Garante que a leitura automática não muda entre execuções da mesma sessão."""
    if modo_override == "Automático (Tempo Real - Coimbra)":
        if modo_override not in _CACHE_METEO_AUTO:
            _CACHE_METEO_AUTO[modo_override] = copy.deepcopy(
                obter_meteorologia_atual(modo_override=modo_override)
            )
        return copy.deepcopy(_CACHE_METEO_AUTO[modo_override])
    return copy.deepcopy(obter_meteorologia_atual(modo_override=modo_override))


def _lote_contabilizado_simulacao(lote: dict, catalogo_map: dict[str, dict]) -> bool:
    prod = catalogo_map.get(lote.get("produto_id", ""), {})
    return _normalizar_categoria(prod.get("categoria"), default="outros") not in CATEGORIAS_EXCLUIDAS_LIDL


def _peso_unitario_produto(prod: dict) -> float:
    return 1.0 if prod.get("unidade_medida") == "kg" else float(prod.get("conteudo_liquido", 0.10))


def _calcular_stock_padaria_elegivel_sacos(
    lotes: list[dict],
    catalogo_map: dict[str, dict],
    fecho_loja_2h: bool,
    quota_fracao: float,
) -> float:
    total_kg = 0.0
    for l in lotes:
        if not _lote_contabilizado_simulacao(l, catalogo_map):
            continue
        if l.get("quantidade_disponivel", 0.0) <= 0:
            continue
        if l.get("estado") in ["esgotado", "expirado", "encaminhado", "lixo"]:
            continue
        prod = catalogo_map.get(l["produto_id"], {})
        if _normalizar_categoria(prod.get("categoria"), default="outros") not in CATEGORIAS_PADARIA_PASTELARIA:
            continue
        dias = int(l.get("dias_para_expirar", 3))
        if not (dias == 1 or (dias == 2 and fecho_loja_2h)):
            continue
        if not eh_elegivel_saco_padaria(l.get("lote_id", ""), quota_fracao=quota_fracao):
            continue
        total_kg += float(l["quantidade_disponivel"]) * _peso_unitario_produto(prod)
    return round(total_kg, 4)


def _registar_salvamento_categoria(
    mapa: dict[str, dict[str, float]],
    cat_nome: str,
    destino_col: str,
    qtd_kg: float,
) -> None:
    if qtd_kg <= 0:
        return
    cat_norm = _normalizar_categoria(cat_nome, default="outros")
    if cat_norm in CATEGORIAS_EXCLUIDAS_LIDL:
        return
    c = cat_norm.capitalize()
    mapa.setdefault(c, {d: 0.0 for d in DESTINOS_NAO_DESPERDICIO})
    mapa[c][destino_col] = round(mapa[c].get(destino_col, 0.0) + float(qtd_kg), 2)


def formatar_eur(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",") + "€"


def sublinhar_texto(texto: str) -> str:
    return "".join(f"{c}\u0332" for c in texto)


def formatar_numero_pt(valor: float, casas_decimais: int = 0) -> str:
    formatado = f"{valor:,.{casas_decimais}f}"
    return formatado.replace(",", " ").replace(".", ",")


def _formatar_delta_pt(valor: float, sufixo: str = "", casas: int = 1) -> str:
    modulo = formatar_numero_pt(abs(valor), casas)
    if valor > 0:
        return f"+{modulo}{sufixo}"
    if valor < 0:
        return f"-{modulo}{sufixo}"
    return f"0{sufixo}"


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
        "descarte_obrigatorio": "Desperdício (Lixo)",
    }
    if destino in mapa_classe:
        return mapa_classe[destino]
    return "Desc. Validade (ESL)" if lote.get("desconto_validade", 0.0) > 0 else "Prateleira (Normal/Campanha)"


def obter_lotes_ativos_fefo(produto_id: str, lotes_por_prod: dict[str, list[dict]]) -> list[dict]:
    elegiveis = [
        l for l in lotes_por_prod.get(produto_id, [])
        if l.get("quantidade_disponivel", 0.0) > 0
        and l.get("estado") not in ["esgotado", "expirado", "encaminhado", "lixo"]
        and l.get("destino_final", "prateleira_desconto") == "prateleira_desconto"
    ]
    elegiveis.sort(key=lambda x: (x.get("dias_para_expirar", 99), x.get("data_validade", "9999-12-31")))
    return elegiveis


def calcular_max_sacos_padaria(
    catalogo_map: dict[str, dict],
    peso_alvo_kg: float = 0.50,
    fator_producao: float = 0.50,
) -> int:
    producao_diaria_kg = sum(
        float(prod.get("vendas_medias_diarias", 0.0)) * _peso_unitario_produto(prod)
        for prod in catalogo_map.values()
        if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_PADARIA_PASTELARIA
    )
    peso_max_sacos_kg = producao_diaria_kg * fator_producao
    if peso_max_sacos_kg < peso_alvo_kg:
        return 0
    return int(math.floor(peso_max_sacos_kg / max(0.01, peso_alvo_kg)))


def aplicar_regras_pos_criacao_sacos(
    sacos: list[dict],
    lotes_by_id: dict[str, dict],
    catalogo_map: dict[str, dict],
    permitir_doacao_externa: bool = False,
) -> list[dict]:
    for saco in sacos:
        saco["desfeito"] = False
        if saco.get("vendido"):
            saco["destino_pos_saco"] = "vendido"
            continue

        lotes_consumo = saco.get("lotes_consumo", {})
        destinos_itens: list[str] = []
        destinos_por_lote: dict[str, str] = {}

        for lid, _qtd_cons in lotes_consumo.items():
            lote = lotes_by_id.get(lid)
            if not lote:
                continue
            prod = catalogo_map.get(lote.get("produto_id", ""), {})
            cat = _normalizar_categoria(prod.get("categoria"), default="outros")
            dias = int(lote.get("dias_para_expirar", 1))
            tipo_val = (prod.get("tipo_validade") or "consumir_ate").lower()

            if (
                permitir_doacao_externa
                and dias >= 2
                and cat not in ("pescado", "carne")
                and tipo_val == "preferencia_antes"
            ):
                destino_item = "doacao_externa"
            elif cat in CATEGORIAS_PADARIA_PASTELARIA:
                destino_item = "racao_animal"
            elif dias <= 0 and tipo_val == "consumir_ate":
                destino_item = "descarte_obrigatorio"
            else:
                destino_item = (
                    "racao_animal"
                    if cat in CATEGORIAS_PADARIA_PASTELARIA
                    else "descarte_obrigatorio"
                )

            destinos_itens.append(destino_item)
            destinos_por_lote[lid] = destino_item
            lote["ultimo_destino_saco"] = destino_item

        saco["destinos_por_lote"] = destinos_por_lote
        if "descarte_obrigatorio" in destinos_itens:
            saco["destino_pos_saco"] = "descarte_obrigatorio"
        elif "doacao_externa" in destinos_itens:
            saco["destino_pos_saco"] = "doacao_externa"
        else:
            saco["destino_pos_saco"] = "racao_animal"

    return sacos


def construir_sacos_surpresa_equilibrados(
    lotes: list[dict],
    catalogo_map: dict[str, dict],
    peso_alvo_kg: float = 0.50,
    max_sacos: int | None = None,
    fator_producao: float = 0.50,
    seed: int = SEED_SIMULACAO_PADRAO,
) -> list[dict]:
    if max_sacos is None:
        max_sacos = calcular_max_sacos_padaria(
            catalogo_map, peso_alvo_kg=peso_alvo_kg, fator_producao=fator_producao
        )

    if max_sacos <= 0:
        return []

    pool_unidades = []
    for lote in lotes:
        if not _lote_contabilizado_simulacao(lote, catalogo_map):
            continue
        if lote.get("destino_final") != "sacos_surpresa":
            continue
        qtd = int(round(lote.get("quantidade_disponivel", 0)))
        if qtd <= 0:
            continue
        prod = catalogo_map.get(lote["produto_id"], {})
        pvp = float(prod.get("pvp", 0.0))
        peso_kg = _peso_unitario_produto(prod)
        desc = max(float(lote.get("desconto_validade", 0.0)), float(prod.get("desconto_campanha", 0.0)))
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

    rng = random.Random(seed)
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

    lotes_by_id = {l["lote_id"]: l for l in lotes if "lote_id" in l}
    return aplicar_regras_pos_criacao_sacos(sacos, lotes_by_id, catalogo_map)


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


def _aplicar_politica_padaria_lote(lote: dict, prod: dict, fecho_loja_2h: bool) -> None:
    """Ajusta o desconto ESL de padaria/pastelaria cumprindo piso financeiro e regra +5% da campanha."""
    if _normalizar_categoria(prod.get("categoria"), default="outros") not in CATEGORIAS_PADARIA_PASTELARIA:
        return
    if lote.get("quantidade_disponivel", 0.0) <= 0:
        return
    if int(lote.get("dias_para_expirar", 3)) == 1 and lote.get("destino_final") == "prateleira_desconto":
        desc_campanha = float(prod.get("desconto_campanha", 0.0))
        desc_alvo = 0.45 if fecho_loja_2h else 0.25
        min_com_campanha = round(desc_campanha + 0.05, 2) if desc_campanha > 0 else 0.0
        if desc_campanha > 0 and desc_alvo < min_com_campanha:
            desc_alvo = min_com_campanha

        pvp = float(prod.get("pvp", 0.0))
        custo_descarte = float(prod.get("custo_descarte", 0.0))
        if pvp > 0:
            piso_critico = max(custo_descarte, pvp * 0.15)
            desc_max_critico = max(0.0, math.floor((1 - (piso_critico / pvp)) * 100) / 100)
            teto_efetivo = min(desc_max_critico, 0.70)
            if desc_campanha > 0 and teto_efetivo + 1e-9 < min_com_campanha:
                desc_alvo = 0.0
            else:
                desc_alvo = min(desc_alvo, teto_efetivo)

        if desc_alvo > lote.get("desconto_validade", 0.0):
            lote["desconto_validade"] = round(desc_alvo, 2)
            _, preco_f = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_f
            if lote["desconto_validade"] >= 0.35:
                lote["estado"] = "promocao_critica"


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
    pvp = float(prod.get("pvp", 0.0))
    desc_campanha = float(prod.get("desconto_campanha", 0.0))
    periodo_campanha = prod.get("periodo_campanha", "")
    unidade = prod.get("unidade_medida", "un")
    cat_norm = _normalizar_categoria(prod.get("categoria"), default="outros")
    dias = int(lote["dias_para_expirar"])
    quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbacoes_ativas

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

    chuva_temporal = _detetar_chuva_temporal(meteo)

    val_csp = validar_regras_csp(
        lote=lote,
        desconto_proposto=res_pri["desconto_proposto"],
        destino=res_log["destino_proposto"],
        produto_catalogo=prod,
        stock_total_sacos=stock_total_padaria_urgente,
        fecho_loja_2h=fecho_loja_2h,
        quebra_clientes=quebra_clientes,
        chuva_temporal=chuva_temporal,
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
        "Categoria": cat_norm.capitalize(),
        "Stock": formatar_stock(lote["quantidade_disponivel"], unidade),
        "Validade": date.fromisoformat(lote["data_validade"]),
        "Dias": int(dias),
        "PVP": formatar_eur(pvp),
        "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
        "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
        "Desc. Validade": f"-{int(lote['desconto_validade'] * 100)}%" if lote["desconto_validade"] > 0 else "—",
        "Preço Ativo": preco_exibido_tabela,
        "Destino Operacional": formatar_destino_legivel(destino_final),
        "Decisão dos agentes": f"✅ {sublinhar_texto('Aprovado')}" if val_csp["valido"] else f"🛡️ {sublinhar_texto('Ajustado')}",
    }

    log_card = {
        "lote_id": lote["lote_id"],
        "produto_id": prod["produto_id"],
        "nome": prod["nome"],
        "categoria": cat_norm.capitalize(),
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
    seed: int = SEED_SIMULACAO_PADRAO,
    data_ref: date | None = None,
) -> dict:
    fecho_loja_2h = "A menos de 2 horas de fechar a loja." in perturbacoes_ativas
    quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbacoes_ativas
    feriado_amanha = "Feriado / Loja Fechada Amanhã (Urgência Máxima)" in perturbacoes_ativas
    data_operacional = data_ref or date.today()
    gestor = GestorBaseDadosTemporal(total_produtos=200, seed=SEED_CATALOGO_BASE)
    rag_retriever = _obter_rag_deterministico(data_operacional, seed=seed)
    meteo = _obter_meteo_deterministica(modo_meteo)

    catalogo_copia, lotes_copia = _obter_dataset_base_deterministico(
        gestor=gestor,
        data_ref=data_operacional,
        total_produtos=200,
        seed=SEED_CATALOGO_BASE,
    )
    catalogo_map = {p["produto_id"]: p for p in catalogo_copia}

    # Perturbações aplicadas de forma determinística a todos os produtos/lotes
    if meteo["fator_procura"] != 1.0:
        for p in catalogo_copia:
            if meteo["fator_procura"] < 1.0 or p.get("categoria") in ["bebidas", "fruta", "carne", "pescado"]:
                p["vendas_medias_diarias"] = max(
                    0.2, round(p["vendas_medias_diarias"] * meteo["fator_procura"], 2)
                )

    if quebra_clientes:
        for p in catalogo_copia:
            p["vendas_medias_diarias"] = max(0.2, round(p["vendas_medias_diarias"] * 0.5, 2))
    if feriado_amanha:
        for p in catalogo_copia:
            if p.get("categoria") in ["pescado", "carne"]:
                p["vendas_medias_diarias"] = max(0.2, round(p["vendas_medias_diarias"] * 1.15, 2))
        for lote in lotes_copia:
            if lote["dias_para_expirar"] <= 2:
                lote["dias_para_expirar"] = 1
                lote["data_validade"] = data_operacional.isoformat()
    if "Pico de Stock Excedente em Frutas e Carne" in perturbacoes_ativas:
        fator_pico = 1.0 + PARAMETROS_LIDL["aumento_pico"]
        for lote in lotes_copia:
            prod = catalogo_map.get(lote["produto_id"], {})
            if prod.get("categoria") in ["carne", "fruta"]:
                nova_qtd = lote["quantidade_disponivel"] * fator_pico
                lote["quantidade_disponivel"] = (
                    round(nova_qtd, 1) if prod.get("unidade_medida") == "kg" else int(round(nova_qtd))
                )

    fator_sacos_dia = 0.50 if (fecho_loja_2h or quebra_clientes) else 0.35
    stock_total_padaria_urgente = _calcular_stock_padaria_elegivel_sacos(
        lotes_copia, catalogo_map, fecho_loja_2h=fecho_loja_2h, quota_fracao=fator_sacos_dia
    )

    resultados_lote: list[dict | None] = [None] * len(lotes_copia)
    logs_cards: list[dict] = []
    tarefas_criticas: list[tuple[int, dict, dict]] = []

    for idx, lote in enumerate(lotes_copia):
        prod = catalogo_map.get(lote["produto_id"], {})
        dias = int(lote["dias_para_expirar"])
        contabiliza = _lote_contabilizado_simulacao(lote, catalogo_map)

        if not contabiliza or dias > 5:
            pvp = float(prod.get("pvp", 0.0))
            desc_campanha = float(prod.get("desconto_campanha", 0.0))
            periodo_campanha = prod.get("periodo_campanha", "")
            unidade = prod.get("unidade_medida", "un")
            cat_norm = prod.get("categoria", "outros")

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
                "Categoria": cat_norm.capitalize(),
                "Stock": formatar_stock(lote["quantidade_disponivel"], unidade),
                "Validade": date.fromisoformat(lote["data_validade"]),
                "Dias": int(dias),
                "PVP": formatar_eur(pvp),
                "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
                "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
                "Desc. Validade": "—",
                "Preço Ativo": formatar_eur(preco_final),
                "Destino Operacional": "Prateleira (Etiqueta ESL)",
                "Decisão dos agentes": "— (Validade > 5d)" if dias > 5 else "— (Fora da simulação)",
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
                        data_operacional,
                        meteo,
                    ),
                )
                for idx, lote, prod in tarefas_criticas
            ]
            for idx, fut in futuros:
                linha_tabela, log_card = fut.result()
                resultados_lote[idx] = linha_tabela
                logs_cards.append(log_card)

    sacos_surpresa = construir_sacos_surpresa_equilibrados(
        lotes_copia,
        catalogo_map,
        peso_alvo_kg=0.50,
        fator_producao=fator_sacos_dia,
        seed=seed,
    )

    qtd_em_sacos_por_lote: dict[str, float] = {}
    for saco in sacos_surpresa:
        for lid, q_cons in (saco.get("lotes_consumo") or {}).items():
            qtd_em_sacos_por_lote[lid] = qtd_em_sacos_por_lote.get(lid, 0.0) + float(q_cons)

    logs_por_id = {item["lote_id"]: item for item in logs_cards}
    for idx, lote in enumerate(lotes_copia):
        if not _lote_contabilizado_simulacao(lote, catalogo_map):
            continue
        if lote.get("destino_final") != "sacos_surpresa":
            continue
        lid = lote["lote_id"]
        prod = catalogo_map.get(lote["produto_id"], {})
        unidade = prod.get("unidade_medida", "un")
        qtd_total = float(lote.get("quantidade_disponivel", 0.0))
        qtd_nos_sacos = qtd_em_sacos_por_lote.get(lid, 0.0)

        if qtd_nos_sacos <= 0:
            lote["destino_final"] = "prateleira_desconto"
            lote["desconto_validade"] = 0.0
            _aplicar_politica_padaria_lote(lote, prod, fecho_loja_2h)
            desc_efetivo, preco_f = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_f
            if resultados_lote[idx] is not None:
                resultados_lote[idx]["Destino Operacional"] = formatar_destino_legivel("prateleira_desconto")
                resultados_lote[idx]["Desc. Validade"] = (
                    f"-{int(lote['desconto_validade'] * 100)}%" if lote.get("desconto_validade", 0.0) > 0 else "—"
                )
                resultados_lote[idx]["Preço Ativo"] = formatar_eur(preco_f)
            if lid in logs_por_id:
                logs_por_id[lid]["destino_final"] = formatar_destino_legivel("prateleira_desconto")
                logs_por_id[lid]["desconto_final"] = f"{int(desc_efetivo * 100)}%"
                logs_por_id[lid]["preco_final"] = formatar_eur(preco_f)
        elif qtd_nos_sacos + 1e-9 < qtd_total:
            sacos_fmt = formatar_stock(qtd_nos_sacos, unidade)
            total_fmt = formatar_stock(qtd_total, unidade)
            rotulo_parcial = f"Sacos Surpresa"
            lote_sobra = dict(lote)
            lote_sobra["destino_final"] = "prateleira_desconto"
            lote_sobra["desconto_validade"] = 0.0
            _aplicar_politica_padaria_lote(lote_sobra, prod, fecho_loja_2h)
            lote["desconto_validade"] = lote_sobra.get("desconto_validade", 0.0)
            desc_efetivo, preco_f = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_f
            if resultados_lote[idx] is not None:
                resultados_lote[idx]["Destino Operacional"] = rotulo_parcial
                resultados_lote[idx]["Desc. Validade"] = (
                    f"-{int(lote['desconto_validade'] * 100)}%" if lote.get("desconto_validade", 0.0) > 0 else "—"
                )
                resultados_lote[idx]["Preço Ativo"] = formatar_eur(preco_f)
            if lid in logs_por_id:
                logs_por_id[lid]["destino_final"] = rotulo_parcial
                logs_por_id[lid]["desconto_final"] = f"{int(desc_efetivo * 100)}%"
                logs_por_id[lid]["preco_final"] = formatar_eur(preco_f)

    chave_telemetria = (data_operacional.isoformat(), cenario_perturbacao)
    if chave_telemetria not in _TELEMETRIA_REGISTADA:
        db_ok, db_msg = gestor.registar_telemetria_sqlite(
            data_operacional, lotes_copia, cenario_perturbacao
        )
        if db_ok:
            _TELEMETRIA_REGISTADA.add(chave_telemetria)
    else:
        db_ok, db_msg = True, "Telemetria já registada para este cenário."

    total_prods = len(catalogo_copia)
    prods_validade_curta = len({l["produto_id"] for l in lotes_copia if l["dias_para_expirar"] <= 5})
    prods_campanha = sum(1 for p in catalogo_copia if p["desconto_campanha"] > 0)
    lotes_desc_val = sum(
        1
        for l in lotes_copia
        if _lote_contabilizado_simulacao(l, catalogo_map)
        and l.get("desconto_validade", 0.0) > 0
        and l["quantidade_disponivel"] > 0
    )
    ajustes_csp = sum(
        1
        for l in lotes_copia
        if _lote_contabilizado_simulacao(l, catalogo_map) and l.get("estado_csp") != "Aprovado"
    )

    registos_decisao = [
        {
            "Categoria": catalogo_map.get(l["produto_id"], {}).get("categoria", "outros").capitalize(),
            "Decisão": classificar_decisao_lote(l),
            "Dias": int(l["dias_para_expirar"]),
        }
        for l in lotes_copia
        if _lote_contabilizado_simulacao(l, catalogo_map)
    ]

    resultados_finalizados = [r for r in resultados_lote if r is not None]

    snapshot = {
        "cenario": cenario_perturbacao,
        "hora": datetime.now().strftime("%H:%M"),
        "data_str": data_operacional.strftime("%d/%m/%Y"),
        "meteorologia": meteo,
        "perturbacoes_ativas": list(perturbacoes_ativas),
        "resultados_simulacao": [dict(r) for r in resultados_finalizados],
        "sacos_surpresa_lista": copy.deepcopy(sacos_surpresa),
        "logs_por_lote": copy.deepcopy(logs_por_id),
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
        "resultados_simulacao": resultados_finalizados,
        "logs_estruturados": logs_cards,
        "logs_por_lote": logs_por_id,
        "lotes_simulados": lotes_copia,
        "catalogo_simulado": catalogo_copia,
        "sacos_surpresa_lista": sacos_surpresa,
        "cenario_ativo": cenario_perturbacao,
        "data_referencia_ativa": data_operacional,
        "meteorologia_ativa": meteo,
        "db_status": (db_ok, db_msg),
        "snapshot": snapshot,
    }


def _simular_baseline_lidl(
    catalogo_base: list[dict],
    lotes_iniciais: list[dict],
    plano_dias: list[dict],
    parametros: dict | None = None,
) -> dict:
    cfg = {**PARAMETROS_LIDL, **(parametros or {})}

    catalogo_norm, lotes_norm = _normalizar_catalogo_e_lotes(catalogo_base, lotes_iniciais)
    catalogo = {p["produto_id"]: p for p in catalogo_norm}

    def a_peso(prod):
        return prod.get("unidade_medida") == "kg"

    def peso(prod):
        return 1.0 if a_peso(prod) else float(prod.get("conteudo_liquido") or 0.10)

    def quantizar(prod, qtd):
        return round(qtd, 2) if a_peso(prod) else float(int(qtd + 1e-9))

    def tipo(prod):
        return (prod.get("tipo_validade") or "consumir_ate").lower()

    totais = dict.fromkeys(
        ["inicial", "entregas", "vendidas", "doadas", "racao", "lixo", "vendidas_desconto"], 0.0
    )
    receita = doacao_eur = custo_lixo = 0.0
    desperdicio_cat: dict[str, float] = {}
    salvamento_cat: dict[str, dict[str, float]] = {}

    def preparar(lote):
        lote = copy.deepcopy(lote)
        lote["quantidade_disponivel"] = quantizar(
            catalogo[lote["produto_id"]], max(0.0, lote["quantidade_disponivel"])
        )
        return lote

    lotes = [
        preparar(l)
        for l in lotes_norm
        if l.get("estado") not in _ESTADOS_FORA
        and l.get("produto_id") in catalogo
        and _lote_contabilizado_simulacao(l, catalogo)
    ]
    totais["inicial"] = sum(l["quantidade_disponivel"] * peso(catalogo[l["produto_id"]]) for l in lotes)

    validade_entrega: dict[str, int] = {}
    stock_base: dict[str, float] = {}
    for l in lotes:
        pid = l["produto_id"]
        validade_entrega[pid] = max(validade_entrega.get(pid, 1), l["dias_para_expirar"])
        stock_base[pid] = stock_base.get(pid, 0.0) + l["quantidade_disponivel"]

    def ativos(pid=None):
        return sorted(
            (l for l in lotes
             if l["quantidade_disponivel"] > 0 and l.get("estado") not in _ESTADOS_FORA
             and (pid is None or l["produto_id"] == pid)),
            key=lambda l: (l["dias_para_expirar"], l.get("data_validade", "9999-12-31")),
        )

    def entregar(lote):
        if lote.get("produto_id") not in catalogo:
            return
        if not _lote_contabilizado_simulacao(lote, catalogo):
            return
        lote = preparar(lote)
        lotes.append(lote)
        totais["entregas"] += lote["quantidade_disponivel"] * peso(catalogo[lote["produto_id"]])

    def sair(lote, qtd, destino):
        nonlocal custo_lixo
        if qtd <= 0:
            return
        prod = catalogo[lote["produto_id"]]
        cat = prod.get("categoria", "outros")
        kg = qtd * peso(prod)
        lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] - qtd, 2)
        totais[destino] += kg
        if destino == "lixo":
            desperdicio_cat[cat.capitalize()] = desperdicio_cat.get(cat.capitalize(), 0.0) + kg
            custo_lixo += qtd * (prod["custo_aquisicao"] + prod["custo_descarte"])
        else:
            rotulo = "Doação / Cozinha" if destino == "doadas" else "Ração / Valorização"
            _registar_salvamento_categoria(salvamento_cat, cat, rotulo, kg)

    def vender(lote, qtd, preco, saco=False):
        nonlocal receita, doacao_eur
        prod = catalogo[lote["produto_id"]]
        kg = qtd * peso(prod)
        valor = qtd * preco
        social = valor * cfg["contribuicao_social_saco"] if saco else 0.0
        doacao_eur += social
        receita += valor - social
        lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] - qtd, 2)
        totais["vendidas"] += kg
        if saco or lote.get("desconto_validade", 0.0) > 0:
            totais["vendidas_desconto"] += kg
            _registar_salvamento_categoria(
                salvamento_cat, prod.get("categoria", "outros"), "Vendido (Desconto/Saco)", kg
            )

    for n_dia, dia in enumerate(plano_dias):
        feriado = dia["feriado_amanha"]

        for lote in dia.get("entregas", []):
            entregar(lote)
        for pid, prod in catalogo.items():
            if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_EXCLUIDAS_LIDL:
                continue
            if pid not in validade_entrega:
                continue
            qtd = 0.0
            if cfg["reposicao_automatica"] and n_dia > 0 and "entregas" not in dia:
                fresco = sum(l["quantidade_disponivel"] for l in ativos(pid) if l["dias_para_expirar"] > 1)
                qtd = max(0.0, prod.get("vendas_medias_diarias", 2.0) * cfg["cobertura_dias"] - fresco)
            if dia["pico_stock"] and prod.get("categoria") in ("carne", "fruta"):
                qtd += stock_base[pid] * cfg["aumento_pico"]
            if quantizar(prod, qtd) > 0:
                entregar({"produto_id": pid, "quantidade_disponivel": qtd,
                          "dias_para_expirar": validade_entrega[pid]})

        for lote in ativos():
            if lote["dias_para_expirar"] <= 0 and tipo(catalogo[lote["produto_id"]]) == "consumir_ate":
                sair(lote, lote["quantidade_disponivel"], "lixo")

        fator_meteo = dia.get("fator_meteo", dia.get("fator_dia", 1.0))
        fator_clientes = dia.get("fator_clientes", 1.0)
        sorteio, procura = {}, {}
        for pid, prod in catalogo.items():
            if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_EXCLUIDAS_LIDL:
                continue
            rng = random.Random(f"{cfg['semente']}-{n_dia}-{pid}")
            fator_cat_meteo = (
                fator_meteo
                if (fator_meteo < 1.0 or prod.get("categoria") in ("bebidas", "fruta", "carne", "pescado"))
                else 1.0
            )
            extra = (
                cfg["fator_pescado_feriado"]
                if feriado and prod.get("categoria") in ("pescado", "carne")
                else 1.0
            )
            procura[pid] = (
                prod.get("vendas_medias_diarias", 2.0)
                * fator_cat_meteo
                * fator_clientes
                * extra
                * rng.uniform(0.85, 1.15)
            )
            sorteio[pid] = rng

        for lote in ativos():
            dias = lote["dias_para_expirar"]
            if dias <= 1 or (feriado and dias == 2):
                desc, destino = cfg["desconto_ultimo_dia"], "ultimo_dia"
            elif dias <= cfg["dias_dll"]:
                desc, destino = cfg["desconto_dll"], "dll"
            else:
                desc, destino = 0.0, "prateleira_normal"
            lote["desconto_validade"] = desc
            lote["destino_final"] = destino

        for pid, prod in catalogo.items():
            if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_EXCLUIDAS_LIDL:
                continue
            if tipo(prod) != "consumir_ate" or prod.get("categoria") not in cfg["categorias_doacao"]:
                continue
            por_vender = procura[pid]
            for lote in ativos(pid):
                desc = max(lote["desconto_validade"], prod.get("desconto_campanha", 0.0))
                previsto = por_vender * (1 + desc * prod.get("elasticidade_preco", 1.2))
                excedente = max(0.0, lote["quantidade_disponivel"] - previsto)
                por_vender = max(0.0, por_vender - lote["quantidade_disponivel"])
                if lote["dias_para_expirar"] == 1:
                    sair(lote, quantizar(prod, excedente * cfg["taxa_doacao"]), "doadas")

        for cat in cfg["categorias_saco"]:
            reservas, procura_saco = [], 0.0
            for pid, prod in catalogo.items():
                if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_EXCLUIDAS_LIDL:
                    continue
                if prod.get("categoria") != cat or a_peso(prod):
                    continue
                vespera = [l for l in ativos(pid) if l["dias_para_expirar"] == 1]
                quota = quantizar(prod, sum(l["quantidade_disponivel"] for l in vespera) * cfg["quota_saco"])
                elast = prod.get("elasticidade_preco", 1.2)
                if quota > 0:
                    procura_saco += (
                        procura[pid] * (1 + cfg["desconto_saco"] * elast) * cfg["fator_janela_saco"]
                    )
                for lote in vespera:
                    q = min(quota, lote["quantidade_disponivel"])
                    if q > 0:
                        reservas.append((lote, int(q)))
                        quota -= q
            n = cfg["unidades_por_saco"]
            por_vender = int(min(sum(q for _, q in reservas), procura_saco)) // n * n
            for lote, q in reservas:
                q = min(q, por_vender)
                if q <= 0:
                    continue
                prod = catalogo[lote["produto_id"]]
                pid = lote["produto_id"]
                vender(lote, float(q), prod["pvp"] * (1 - cfg["desconto_saco"]), saco=True)
                por_vender -= q
                elast = prod.get("elasticidade_preco", 1.2)
                procura[pid] = max(
                    0.0, procura[pid] - q / ((1 + cfg["desconto_saco"] * elast) * cfg["fator_janela_saco"])
                )

        for pid, prod in catalogo.items():
            if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_EXCLUIDAS_LIDL:
                continue
            restante = procura.get(pid, 0.0)
            for lote in ativos(pid):
                if restante <= 0:
                    break
                desc = max(lote["desconto_validade"], prod.get("desconto_campanha", 0.0))
                mult = max(0.01, 1 + desc * prod.get("elasticidade_preco", 1.2))
                alvo = restante * mult
                if not a_peso(prod):
                    alvo = int(alvo) + (sorteio[pid].random() < alvo - int(alvo))
                qtd = quantizar(prod, min(lote["quantidade_disponivel"], alvo))
                if qtd > 0:
                    _, preco = calcular_preco_efetivo_lote(lote, prod)
                    lote["preco_final_atual"] = preco
                    vender(lote, qtd, preco)
                restante = max(0.0, restante - qtd / mult)

        for lote in ativos():
            lote["dias_para_expirar"] -= 1
            if lote["dias_para_expirar"] > 0:
                continue
            prod = catalogo[lote["produto_id"]]
            if tipo(prod) == "preferencia_antes":
                sair(lote, quantizar(prod, lote["quantidade_disponivel"] * cfg["taxa_doacao_preferencia"]), "doadas")
            if prod.get("categoria") in cfg["categorias_racao"]:
                sair(lote, quantizar(prod, lote["quantidade_disponivel"] * cfg["taxa_racao"]), "racao")
            sair(lote, lote["quantidade_disponivel"], "lixo")
            lote["quantidade_disponivel"] = 0.0
            lote["estado"] = "expirado"

    stock_final = sum(l["quantidade_disponivel"] * peso(catalogo[l["produto_id"]]) for l in ativos())
    salvo = totais["vendidas_desconto"] + totais["doadas"] + totais["racao"]
    qtar = salvo + totais["lixo"]
    movimento = totais["vendidas"] + totais["doadas"] + totais["racao"] + totais["lixo"]

    return {
        "ts_pct": round(salvo / qtar * 100, 2) if qtar else 0.0,
        "taxa_desperdicio_pct": round(totais["lixo"] / movimento * 100, 2) if movimento else 0.0,
        "total_vendidas": round(totais["vendidas"], 2),
        "total_doadas_cozinha": round(totais["doadas"], 2),
        "total_racao_valorizacao": round(totais["racao"], 2),
        "total_encaminhadas_total": round(totais["doadas"] + totais["racao"], 2),
        "total_desperdicadas": round(totais["lixo"], 2),
        "receita_total": round(receita, 2),
        "doacao_rede_emergencia_eur": round(doacao_eur, 2),
        "custo_desperdicio": round(custo_lixo, 2),
        "qtar_kg": round(qtar, 2),
        "desperdicio_por_categoria": {k: round(v, 2) for k, v in desperdicio_cat.items()},
        "salvamento_por_categoria": salvamento_cat,
        "stock_inicial_kg": round(totais["inicial"], 2),
        "entregas_kg": round(totais["entregas"], 2),
        "stock_final_kg": round(stock_final, 2),
        "parametros": cfg,
    }


def _gerar_cenario_dia_deterministico(
    dia_idx: int,
    modo_meteo_base: str,
    combinar_perturbacoes_aleatorias: bool,
    seed: int = SEED_SIMULACAO_PADRAO,
) -> tuple[list[str], str]:
    """Devolve sempre as mesmas perturbações e meteorologia para cada dia_idx."""
    if not combinar_perturbacoes_aleatorias:
        return [], modo_meteo_base

    cenarios_possiveis = [
        [],
        ["A menos de 2 horas de fechar a loja."],
        ["Quebra Repentina de Clientes (-50% Procura)"],
        ["Feriado / Loja Fechada Amanhã (Urgência Máxima)"],
        ["Pico de Stock Excedente em Frutas e Carne"],
        ["A menos de 2 horas de fechar a loja.", "Quebra Repentina de Clientes (-50% Procura)"],
    ]
    modos_meteo_ciclo = [
        modo_meteo_base,
        "Simular: Chuva Intensa / Temporal",
        "Simular: Calor Elevado (> 30°C)",
        "Simular: Céu Limpo / Normal",
    ]

    rng_dia = random.Random(f"{seed}-cenario-dia-{dia_idx}")
    perturbs_dia = (
        list(cenarios_possiveis[dia_idx % len(cenarios_possiveis)])
        if dia_idx % 2 == 1
        else list(rng_dia.choice(cenarios_possiveis[:3]))
    )
    meteo_dia_modo = modos_meteo_ciclo[dia_idx % len(modos_meteo_ciclo)]
    return perturbs_dia, meteo_dia_modo


def simular_horizonte_temporal(
    dias_simulacao: int = 7,
    modo_meteo: str = "Automático (Tempo Real - Coimbra)",
    combinar_perturbacoes_aleatorias: bool = True,
    seed: int = SEED_SIMULACAO_PADRAO,
    data_ref: date | None = None,
) -> dict:
    qvd_kg_total = 0.0
    qd_kg_total = 0.0      # Doação externa + Ração animal
    qci_kg_total = 0.0     # Cozinha interna
    qexp_kg_total = 0.0
    plano_dias = []

    gestor = GestorBaseDadosTemporal(total_produtos=200, seed=SEED_CATALOGO_BASE)
    data_inicial = data_ref or date.today()
    rag_retriever = _obter_rag_deterministico(data_inicial, seed=seed)
    catalogo_base, lotes_ativos = _obter_dataset_base_deterministico(
        gestor=gestor,
        data_ref=data_inicial,
        total_produtos=200,
        seed=SEED_CATALOGO_BASE,
    )
    catalogo_base_map = {p["produto_id"]: p for p in catalogo_base}
    lotes_iniciais_copia = copy.deepcopy(lotes_ativos)

    evolucao_diaria = []
    desperdicio_por_categoria: dict[str, float] = {}
    salvamento_por_categoria: dict[str, dict[str, float]] = {}
    custo_desperdicio_total = 0.0
    receita_total_recuperada = 0.0
    total_kg_vendidas = 0.0
    total_kg_doadas_cozinha = 0.0
    total_kg_racao = 0.0
    total_kg_desperdicadas = 0.0

    for dia_idx in range(dias_simulacao):
        data_corrente = date.fromordinal(data_inicial.toordinal() + dia_idx)
        perturbs_dia, meteo_dia_modo = _gerar_cenario_dia_deterministico(
            dia_idx=dia_idx,
            modo_meteo_base=modo_meteo,
            combinar_perturbacoes_aleatorias=combinar_perturbacoes_aleatorias,
            seed=seed,
        )

        fecho_2h = "A menos de 2 horas de fechar a loja." in perturbs_dia
        quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbs_dia
        feriado_amanha = "Feriado / Loja Fechada Amanhã (Urgência Máxima)" in perturbs_dia
        pico_stock = "Pico de Stock Excedente em Frutas e Carne" in perturbs_dia
        meteo = _obter_meteo_deterministica(meteo_dia_modo)

        fator_meteo = meteo["fator_procura"]
        fator_clientes = 0.50 if quebra_clientes else 1.0
        plano_dias.append({
            "fator_meteo": fator_meteo,
            "fator_clientes": fator_clientes,
            "pico_stock": pico_stock,
            "feriado_amanha": feriado_amanha,
        })

        catalogo_dia_list = []
        catalogo_dia_map: dict[str, dict] = {}
        for p in catalogo_base:
            p_dia = dict(p)
            if fator_meteo != 1.0 and (
                fator_meteo < 1.0 or p_dia.get("categoria") in ["bebidas", "fruta", "carne", "pescado"]
            ):
                p_dia["vendas_medias_diarias"] = max(0.2, round(p_dia["vendas_medias_diarias"] * fator_meteo, 2))
            if quebra_clientes:
                p_dia["vendas_medias_diarias"] = max(0.2, round(p_dia["vendas_medias_diarias"] * 0.50, 2))
            if feriado_amanha and p_dia.get("categoria") in ["pescado", "carne"]:
                p_dia["vendas_medias_diarias"] = max(0.2, round(p_dia["vendas_medias_diarias"] * 1.15, 2))
            catalogo_dia_list.append(p_dia)
            catalogo_dia_map[p_dia["produto_id"]] = p_dia

        if pico_stock:
            fator_pico = 1.0 + PARAMETROS_LIDL["aumento_pico"]
            for lote in lotes_ativos:
                prod = catalogo_dia_map.get(lote["produto_id"], {})
                if prod.get("categoria") in ["carne", "fruta"] and lote["quantidade_disponivel"] > 0:
                    nova_qtd = lote["quantidade_disponivel"] * fator_pico
                    lote["quantidade_disponivel"] = (
                        round(nova_qtd, 1) if prod.get("unidade_medida") == "kg" else float(int(round(nova_qtd)))
                    )

        dias_originais_dia: dict[int, int] = {}
        for idx, lote in enumerate(lotes_ativos):
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") in ["expirado", "encaminhado", "lixo"]:
                continue
            dias_originais_dia[idx] = lote["dias_para_expirar"]
            if feriado_amanha and lote["dias_para_expirar"] <= 2:
                lote["dias_para_expirar"] = 1

        fator_sacos_dia = 0.50 if (fecho_2h or quebra_clientes) else 0.35
        stock_padaria_urgente = _calcular_stock_padaria_elegivel_sacos(
            lotes_ativos, catalogo_dia_map, fecho_loja_2h=fecho_2h, quota_fracao=fator_sacos_dia
        )

        tarefas = []
        for idx, lote in enumerate(lotes_ativos):
            if not _lote_contabilizado_simulacao(lote, catalogo_dia_map):
                continue
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") in ["expirado", "encaminhado", "lixo"]:
                continue
            prod = catalogo_dia_map[lote["produto_id"]]
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
                        catalogo_dia_list,
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

        lotes_by_id = {l["lote_id"]: l for l in lotes_ativos}
        sacos_dia = construir_sacos_surpresa_equilibrados(
            lotes_ativos,
            catalogo_dia_map,
            peso_alvo_kg=0.50,
            fator_producao=fator_sacos_dia,
            seed=seed + dia_idx,
        )
        qtd_reservada_sacos: dict[str, float] = {}
        for saco in sacos_dia:
            for lid, q_cons in (saco.get("lotes_consumo") or {}).items():
                qtd_reservada_sacos[lid] = qtd_reservada_sacos.get(lid, 0.0) + float(q_cons)

        for lote in lotes_ativos:
            if not _lote_contabilizado_simulacao(lote, catalogo_dia_map):
                continue
            if lote.get("destino_final") != "sacos_surpresa":
                continue
            lid = lote["lote_id"]
            reservada = min(lote["quantidade_disponivel"], qtd_reservada_sacos.get(lid, 0.0))
            sobra_prateleira = round(lote["quantidade_disponivel"] - reservada, 2)
            lote["destino_final"] = "prateleira_desconto"
            if sobra_prateleira > 0:
                lote["quantidade_disponivel"] = sobra_prateleira
                lote["desconto_validade"] = 0.0
                _aplicar_politica_padaria_lote(lote, catalogo_dia_map[lote["produto_id"]], fecho_2h)
            else:
                lote["quantidade_disponivel"] = 0.0

        vendidas_kg_dia = 0.0
        doadas_kg_dia = 0.0
        racao_kg_dia = 0.0
        desperdicadas_kg_dia = 0.0
        receita_dia = 0.0

        procura_por_prod: dict[str, float] = {}
        for pid, prod in catalogo_dia_map.items():
            if _normalizar_categoria(prod.get("categoria"), default="outros") in CATEGORIAS_EXCLUIDAS_LIDL:
                continue
            rng_prod = random.Random(f"{seed}-procura-{dia_idx}-{pid}")
            procura_por_prod[pid] = prod.get("vendas_medias_diarias", 2.0) * rng_prod.uniform(0.85, 1.15)

        for lid, reservada in qtd_reservada_sacos.items():
            l = lotes_by_id.get(lid)
            if l is not None and reservada > 0:
                l["quantidade_disponivel"] = round(l["quantidade_disponivel"] + reservada, 2)

        taxa_venda_sacos = 0.65 if quebra_clientes else 0.90
        for idx_saco, saco in enumerate(sacos_dia):
            rng_saco = random.Random(f"{seed}-saco-{dia_idx}-{idx_saco}")
            vendido_saco = rng_saco.random() <= taxa_venda_sacos
            saco["vendido"] = vendido_saco
            if vendido_saco:
                receita_dia += saco["preco_final"]
                qvd_kg_total += saco["peso_kg"]
                for lid, q_cons in saco["lotes_consumo"].items():
                    l = lotes_by_id.get(lid)
                    if l is not None:
                        abat = min(l["quantidade_disponivel"], q_cons)
                        if abat > 0:
                            pid_saco = l["produto_id"]
                            prod_saco = catalogo_dia_map.get(pid_saco, {})
                            kg_abat = abat * _peso_unitario_produto(prod_saco)
                            l["quantidade_disponivel"] = round(l["quantidade_disponivel"] - abat, 2)
                            vendidas_kg_dia += kg_abat
                            cat_saco = prod_saco.get("categoria", "padaria")
                            _registar_salvamento_categoria(
                                salvamento_por_categoria, cat_saco, "Vendido (Desconto/Saco)", kg_abat
                            )
                            elast = prod_saco.get("elasticidade_preco", 1.2)
                            desc_saco = saco["desconto_pct"] / 100.0
                            if pid_saco in procura_por_prod:
                                procura_por_prod[pid_saco] = max(
                                    0.0,
                                    procura_por_prod[pid_saco]
                                    - abat / max(0.01, (1.0 + desc_saco * elast) * 0.85),
                                )
            else:
                for lid, q_cons in saco["lotes_consumo"].items():
                    l = lotes_by_id.get(lid)
                    if l is None:
                        continue
                    abat = min(l["quantidade_disponivel"], q_cons)
                    if abat <= 0:
                        continue
                    if int(l.get("dias_para_expirar", 1)) > 1:
                        continue

                    prod_saco = catalogo_dia_map.get(l["produto_id"], {})
                    cat_saco = prod_saco.get("categoria", "padaria")
                    l["quantidade_disponivel"] = round(l["quantidade_disponivel"] - abat, 2)

                    # 50% para doação e os restantes 50% para o lixo
                    if prod_saco.get("unidade_medida") == "kg":
                        qtd_doada = round(abat * 0.50, 2)
                    else:
                        qtd_doada = float(int(abat * 0.50 + 1e-9))
                    qtd_lixo = round(max(0.0, abat - qtd_doada), 2)

                    kg_doada = qtd_doada * _peso_unitario_produto(prod_saco)
                    kg_lixo = qtd_lixo * _peso_unitario_produto(prod_saco)

                    if kg_doada > 0:
                        qd_kg_total += kg_doada
                        doadas_kg_dia += kg_doada
                        _registar_salvamento_categoria(
                            salvamento_por_categoria, cat_saco, "Doação / Cozinha", kg_doada
                        )

                    if kg_lixo > 0:
                        qexp_kg_total += kg_lixo
                        desperdicadas_kg_dia += kg_lixo
                        cat_label = cat_saco.capitalize()
                        desperdicio_por_categoria[cat_label] = round(
                            desperdicio_por_categoria.get(cat_label, 0.0) + kg_lixo, 2
                        )
                        custo_desperdicio_total += qtd_lixo * (
                            prod_saco.get("custo_aquisicao", 0.0) + prod_saco.get("custo_descarte", 0.0)
                        )

        lotes_por_prod: dict[str, list[dict]] = {}
        for l in lotes_ativos:
            if not _lote_contabilizado_simulacao(l, catalogo_dia_map):
                continue
            if l["quantidade_disponivel"] > 0 and l.get("estado") not in ["expirado", "encaminhado", "lixo"]:
                lotes_por_prod.setdefault(l["produto_id"], []).append(l)

        for prod_id, _ in lotes_por_prod.items():
            prod = catalogo_dia_map[prod_id]
            cat = prod.get("categoria", "outros")
            peso_unit = _peso_unitario_produto(prod)
            elegiveis = obter_lotes_ativos_fefo(prod_id, lotes_por_prod)
            if not elegiveis:
                continue

            procura_base = procura_por_prod.get(prod_id, 0.0)

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
                    kg_vend = qtd_vendida * peso_unit
                    lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] - qtd_vendida, 2)
                    receita_dia += qtd_vendida * lote.get("preco_final_atual", prod["pvp"])
                    vendidas_kg_dia += kg_vend
                    if lote.get("desconto_validade", 0.0) > 0:
                        qvd_kg_total += kg_vend
                        _registar_salvamento_categoria(
                            salvamento_por_categoria, cat, "Vendido (Desconto/Saco)", kg_vend
                        )
                    procura_base = max(0.0, procura_base - (qtd_vendida / (1.0 + desc_ativo * elast)))

        for lote in lotes_ativos:
            if not _lote_contabilizado_simulacao(lote, catalogo_dia_map):
                continue
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") in ["expirado", "encaminhado", "lixo"]:
                continue
            dest = lote.get("destino_final", "prateleira_desconto")
            prod = catalogo_dia_map[lote["produto_id"]]
            peso_unit = _peso_unitario_produto(prod)

            if dest in ["cozinha_interna", "doacao_externa", "racao_animal"]:
                qtd_enc = lote["quantidade_disponivel"]
                kg_lote = qtd_enc * peso_unit

                if dest == "cozinha_interna":
                    qci_kg_total += kg_lote
                    doadas_kg_dia += kg_lote
                    _registar_salvamento_categoria(
                        salvamento_por_categoria, prod.get("categoria", "outros"), "Doação / Cozinha", kg_lote
                    )
                elif dest == "doacao_externa":
                    qd_kg_total += kg_lote
                    doadas_kg_dia += kg_lote
                    _registar_salvamento_categoria(
                        salvamento_por_categoria, prod.get("categoria", "outros"), "Doação / Cozinha", kg_lote
                    )
                else:
                    qd_kg_total += kg_lote
                    racao_kg_dia += kg_lote
                    _registar_salvamento_categoria(
                        salvamento_por_categoria, prod.get("categoria", "outros"), "Ração / Valorização", kg_lote
                    )

                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "encaminhado"

            elif dest == "descarte_obrigatorio":
                qtd_lixo = lote["quantidade_disponivel"]
                kg_lixo = qtd_lixo * peso_unit
                cat_label = prod.get("categoria", "outros").capitalize()

                qexp_kg_total += kg_lixo
                desperdicadas_kg_dia += kg_lixo
                desperdicio_por_categoria[cat_label] = round(
                    desperdicio_por_categoria.get(cat_label, 0.0) + kg_lixo, 2
                )
                custo_desperdicio_total += qtd_lixo * (prod["custo_aquisicao"] + prod["custo_descarte"])

                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "lixo"
                lote["dia_expiracao_sim"] = dia_idx + 1

        for idx_lote, dias_orig in dias_originais_dia.items():
            l_ref = lotes_ativos[idx_lote]
            if l_ref["quantidade_disponivel"] > 0 and l_ref.get("estado") not in ["expirado", "encaminhado", "lixo"]:
                l_ref["dias_para_expirar"] = dias_orig

        for lote in lotes_ativos:
            if lote["quantidade_disponivel"] <= 0 or lote.get("estado") in ["expirado", "encaminhado", "lixo"]:
                continue
            lote["dias_para_expirar"] -= 1
            if not _lote_contabilizado_simulacao(lote, catalogo_dia_map):
                continue
            if lote["dias_para_expirar"] <= 0:
                qtd_exp = lote["quantidade_disponivel"]
                prod = catalogo_dia_map[lote["produto_id"]]
                cat_raw = prod.get("categoria", "outros")
                tipo_val = (prod.get("tipo_validade") or "consumir_ate").lower()
                peso_unit = _peso_unitario_produto(prod)
                cat_label = cat_raw.capitalize()

                if cat_raw in CATEGORIAS_PADARIA_PASTELARIA:
                    kg_pad = qtd_exp * peso_unit
                    qd_kg_total += kg_pad
                    racao_kg_dia += kg_pad
                    _registar_salvamento_categoria(
                        salvamento_por_categoria, cat_raw, "Ração / Valorização", kg_pad
                    )
                    lote["quantidade_disponivel"] = 0.0
                    lote["estado"] = "encaminhado"
                    continue

                if tipo_val == "preferencia_antes":
                    qtd_doada = (
                        round(qtd_exp * PARAMETROS_LIDL["taxa_doacao_preferencia"], 2)
                        if prod.get("unidade_medida") == "kg"
                        else float(int(qtd_exp * PARAMETROS_LIDL["taxa_doacao_preferencia"] + 1e-9))
                    )
                    if qtd_doada > 0:
                        kg_doada = qtd_doada * peso_unit
                        qd_kg_total += kg_doada
                        doadas_kg_dia += kg_doada
                        _registar_salvamento_categoria(
                            salvamento_por_categoria, cat_raw, "Doação / Cozinha", kg_doada
                        )
                        qtd_exp = round(qtd_exp - qtd_doada, 2)

                if qtd_exp > 0:
                    kg_exp = qtd_exp * peso_unit
                    qexp_kg_total += kg_exp
                    desperdicadas_kg_dia += kg_exp
                    desperdicio_por_categoria[cat_label] = round(
                        desperdicio_por_categoria.get(cat_label, 0.0) + kg_exp, 2
                    )
                    custo_desperdicio_total += qtd_exp * (prod["custo_aquisicao"] + prod["custo_descarte"])

                lote["quantidade_disponivel"] = 0.0
                lote["estado"] = "expirado"
                lote["dia_expiracao_sim"] = dia_idx + 1

        encaminhadas_kg_dia = doadas_kg_dia + racao_kg_dia
        total_kg_vendidas += vendidas_kg_dia
        total_kg_doadas_cozinha += doadas_kg_dia
        total_kg_racao += racao_kg_dia
        total_kg_desperdicadas += desperdicadas_kg_dia
        receita_total_recuperada += receita_dia

        evolucao_diaria.append({
            "Dia": f"Dia {dia_idx + 1} ({data_corrente.strftime('%d/%m')})",
            "Cenário / Perturbações": ", ".join(perturbs_dia) if perturbs_dia else "Operação Normal",
            "Clima": meteo["descricao"],
            "Vendidas": round(vendidas_kg_dia, 1),
            "Doação / Cozinha": round(encaminhadas_kg_dia, 1),
            "Desperdício (Lixo)": round(desperdicadas_kg_dia, 1),
            "Receita (€)": round(receita_dia, 2),
        })

    total_encaminhadas_total = total_kg_doadas_cozinha + total_kg_racao
    total_movimentado = max(1.0, total_kg_vendidas + total_encaminhadas_total + total_kg_desperdicadas)
    taxa_desperdicio_pct = (total_kg_desperdicadas / total_movimentado) * 100

    qtar_kg_total = qvd_kg_total + qd_kg_total + qci_kg_total + qexp_kg_total
    ts_pct = ((qvd_kg_total + qd_kg_total + qci_kg_total) / max(0.01, qtar_kg_total)) * 100

    baseline = _simular_baseline_lidl(
        catalogo_base,
        lotes_iniciais_copia,
        plano_dias,
        parametros={"semente": seed},
    )
    prods_contabilizados = sum(
        1 for p in catalogo_base if _normalizar_categoria(p.get("categoria"), default="outros") not in CATEGORIAS_EXCLUIDAS_LIDL
    )
    lotes_contabilizados = sum(
        1 for l in lotes_iniciais_copia if _lote_contabilizado_simulacao(l, catalogo_base_map)
    )

    return {
        "dias_simulados": dias_simulacao,
        "total_produtos": len(catalogo_base),
        "total_lotes_iniciais": len(lotes_iniciais_copia),
        "total_produtos_simulados": prods_contabilizados,
        "total_lotes_simulados": lotes_contabilizados,
        "total_vendidas": round(total_kg_vendidas, 1),
        "total_doadas_cozinha": round(total_kg_doadas_cozinha, 1),
        "total_racao_valorizacao": round(total_kg_racao, 1),
        "total_encaminhadas_total": round(total_encaminhadas_total, 1),
        "total_desperdicadas": round(total_kg_desperdicadas, 1),
        "taxa_desperdicio_pct": round(taxa_desperdicio_pct, 2),
        "receita_total": round(receita_total_recuperada, 2),
        "custo_desperdicio": round(custo_desperdicio_total, 2),
        "qvd_kg": round(qvd_kg_total, 1),
        "qd_kg": round(qd_kg_total, 1),
        "qci_kg": round(qci_kg_total, 1),
        "qr_kg": round(total_kg_racao, 1),
        "qtar_kg": round(qtar_kg_total, 1),
        "ts_pct": round(ts_pct, 2),
        "evolucao_diaria": evolucao_diaria,
        "desperdicio_por_categoria": desperdicio_por_categoria,
        "salvamento_por_categoria": salvamento_por_categoria,
        "comparacao_baseline": baseline,
    }