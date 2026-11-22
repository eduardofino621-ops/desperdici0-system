from datetime import date, datetime
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=True)

from src.database.db_manager import GestorBaseDadosTemporal
from src.simulation.mock_db import (
    calcular_pum,
    calcular_preco_efetivo_lote,
)
from src.agents.inventory_agent import agente_controlo_inventario
from src.agents.pricing_agent import agente_dynamic_pricing
from src.agents.logistics_agent import agente_logistica_doacao
from src.csp.constraints import validar_regras_csp

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ==============================================================================
st.set_page_config(
    page_title="Desperdíci0%",
    page_icon="♻️",
    layout="wide"
)

st.markdown("""
<style>
    .kpi-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
    }
    .kpi-title {
        font-size: 12px;
        color: #64748b;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 26px;
        color: #0f172a;
        font-weight: 800;
    }
    .kpi-sub {
        font-size: 11px;
        color: #64748b;
        margin-top: 2px;
    }
    .esl-bezel {
        background: #1e293b;
        padding: 7px;
        border-radius: 10px;
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.14);
        max-width: 360px;
        margin: 0 auto 8px auto;
    }
    .esl-screen {
        background: #e5e7eb;
        border-radius: 5px;
        padding: 11px 12px;
        color: #0f172a;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        min-height: 190px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        border: 1px solid #cbd5e1;
    }
    .esl-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        border-bottom: 1.5px solid #cbd5e1;
        padding-bottom: 5px;
        margin-bottom: 6px;
    }
    .esl-prod-name {
        font-size: 15.5px;
        font-weight: 800;
        color: #090d16;
        line-height: 1.15;
        margin: 0;
    }
    .esl-gtin {
        font-size: 9.5px;
        font-weight: 600;
        color: #475569;
        font-family: 'JetBrains Mono', monospace;
        margin-left: 6px;
        white-space: nowrap;
    }
    .esl-middle {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 6px;
        min-height: 36px;
    }
    .esl-pum {
        font-size: 10px;
        font-weight: 700;
        color: #334155;
        text-transform: uppercase;
    }
    .esl-pvp-clean {
        font-size: 14px;
        font-weight: 700;
        color: #1e293b;
    }
    .esl-strike-wrap {
        position: relative;
        display: inline-block;
        font-size: 13.5px;
        font-weight: 700;
        color: #334155;
    }
    .esl-strike-wrap::after {
        content: "";
        position: absolute;
        left: -2px;
        right: -2px;
        top: 50%;
        border-top: 2px solid #dc2626;
        transform: rotate(-10deg);
    }
    .esl-folheto-box {
        text-align: right;
    }
    .esl-folheto-pct {
        font-size: 15px;
        font-weight: 800;
        color: #0f172a;
    }
    .esl-folheto-price {
        font-size: 16px;
        font-weight: 800;
        color: #0f172a;
    }
    .esl-folheto-dates {
        font-size: 9px;
        font-weight: 600;
        color: #475569;
        margin-top: 1px;
    }
    .esl-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        padding-top: 2px;
    }
    .esl-qr {
        width: 44px;
        height: 44px;
        background: #ffffff;
        padding: 2px;
        border-radius: 3px;
        border: 1px solid #94a3b8;
        flex-shrink: 0;
    }
    .esl-promo-group {
        margin-left: auto;
        display: flex;
        align-items: flex-end;
        gap: 7px;
    }
    .esl-discount-badge {
        font-size: 28px;
        font-weight: 900;
        color: #0369a1;
        line-height: 0.95;
        letter-spacing: -0.8px;
    }
    .esl-price-right {
        text-align: right;
    }
    .esl-big-price {
        font-size: 26px;
        font-weight: 900;
        color: #090d16;
        line-height: 1;
    }
    .esl-folheto-main-price {
        font-size: 22px;
        font-weight: 800;
        color: #090d16;
        line-height: 1;
    }
    .esl-unit-tag {
        font-size: 11px;
        font-weight: 800;
        color: #1e293b;
        text-transform: uppercase;
    }
    .esl-validade-bar {
        margin-top: 6px;
        padding-top: 4px;
        border-top: 1px dashed #94a3b8;
        text-align: right;
        font-size: 10.5px;
        font-weight: 700;
        color: #0369a1;
    }
    .esl-extra-lotes {
        margin-top: 5px;
        padding: 4px 6px;
        background: #dbeafe;
        border-radius: 4px;
        border-left: 3px solid #0369a1;
        font-size: 10px;
        color: #0f172a;
    }
    .esl-extra-lote-row {
        display: flex;
        justify-content: space-between;
        font-weight: 700;
        margin-top: 2px;
    }
    .esl-saco-stock {
        font-size: 10.5px;
        font-weight: 800;
        color: #047857;
        background: #d1fae5;
        padding: 2px 7px;
        border-radius: 4px;
        border: 1px solid #6ee7b7;
    }
</style>
""", unsafe_allow_html=True)

st.title("♻️ Desperdíci0% - Simulação")

# ==============================================================================
# SIDEBAR: SIMULAÇÃO DE STRESS OPERACIONAL
# ==============================================================================
st.sidebar.header("🎛️ Painel de Simulação de Stress")
perturbacao = st.sidebar.selectbox(
    "Injetar Perturbação no Sistema:",
    [
        "Nenhuma (Operação Normal)",
        "Quebra Repentina de Clientes (-50% Procura)",
        "Feriado / Loja Fechada Amanhã (Urgência Máxima)",
        "Pico de Stock Excedente nas Frutas/Frescos"
    ],
    key="select_perturbacao"
)

simular_btn = st.sidebar.button("▶️ Reexecutar Orquestração / Sincronizar DB", type="primary", use_container_width=True)

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================
def formatar_eur(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",") + "€"

def formatar_data_pt(data_iso: str) -> str:
    try:
        return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data_iso

def formatar_destino_legivel(destino: str) -> str:
    mapa = {
        "prateleira_desconto": "Prateleira (Etiqueta ESL)",
        "sacos_surpresa": "Sacos Surpresa (Fim de Dia)",
        "cozinha_interna": "Cozinha Interna (Retirado)",
        "doacao_externa": "Doação Externa (Retirado)",
        "descarte_obrigatorio": "Descarte Obrigatório",
    }
    return mapa.get(destino, destino.replace("_", " ").title())

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
    tamanho_alvo_saco: int = 4,
) -> list[dict]:
    """
    1. Recolhe todos os lotes encaminhados para 'sacos_surpresa' (ex.: padaria/pastelaria).
    2. Distribui as unidades disponíveis em round-robin serpentina por sacos de tamanho
       semelhante (~4 artigos), equilibrando o valor base entre sacos.
    3. Soma os preços base (PVP) de cada saco e aplica o desconto de validade validado pelo CSP.
    """
    lotes_sacos = [
        l for l in lotes
        if l.get("destino_final") == "sacos_surpresa"
        and l.get("quantidade_disponivel", 0.0) > 0
        and l.get("estado") not in ["esgotado", "expirado"]
    ]
    if not lotes_sacos:
        return []

    pool_unidades: list[tuple[dict, dict]] = []
    for lote in lotes_sacos:
        prod = catalogo_map.get(lote["produto_id"], {})
        qtd_unidades = max(1, int(round(lote["quantidade_disponivel"])))
        for _ in range(qtd_unidades):
            pool_unidades.append((lote, prod))

    # Ordena por PVP para que a distribuição serpentina gere lotes de sacos com preços homogéneos
    pool_unidades.sort(key=lambda item: (item[1].get("pvp", 0.0), item[0].get("dias_para_expirar", 99)))

    num_sacos = max(1, round(len(pool_unidades) / tamanho_alvo_saco))
    baldes: list[list[tuple[dict, dict]]] = [[] for _ in range(num_sacos)]

    for idx_u, unidade_item in enumerate(pool_unidades):
        ciclo = idx_u // num_sacos
        pos = idx_u % num_sacos
        indice_balde = pos if ciclo % 2 == 0 else (num_sacos - 1 - pos)
        baldes[indice_balde].append(unidade_item)

    sacos_gerados = []
    for idx_s, itens_saco in enumerate(baldes, start=1):
        if not itens_saco:
            continue

        preco_base_saco = round(sum(prod.get("pvp", 0.0) for _, prod in itens_saco), 2)

        custo_minimo_saco = sum(
            prod.get("custo_aquisicao", 0.0) * (1.0 + prod.get("margem_minima_pct", 0.05))
            for _, prod in itens_saco
        )

        descontos_validade = [
            lote.get("desconto_csp_aprovado")
            or lote.get("desconto_validade")
            or prod.get("desconto_campanha")
            or 0.50
            for lote, prod in itens_saco
        ]
        desc_medio = sum(descontos_validade) / len(descontos_validade)
        desconto_pct = max(10, min(80, int(round(desc_medio * 100))))

        preco_final_saco = round(preco_base_saco * (1.0 - desconto_pct / 100.0), 2)
        if preco_final_saco < custo_minimo_saco:
            preco_final_saco = round(custo_minimo_saco, 2)
            desconto_pct = max(5, int(round((1.0 - (preco_final_saco / max(0.01, preco_base_saco))) * 100)))
            preco_final_saco = round(preco_base_saco * (1.0 - desconto_pct / 100.0), 2)

        lotes_consumo: dict[str, float] = {}
        categorias_saco = set()
        for lote, prod in itens_saco:
            l_id = lote.get("lote_id", "")
            categorias_saco.add(prod.get("categoria", "padaria"))
            lotes_consumo[l_id] = lotes_consumo.get(l_id, 0.0) + 1.0

        # Nomes iguais permitidos apenas nos Sacos Surpresa (sem sufixo #01 ou ID)
        if categorias_saco == {"padaria"}:
            titulo_saco = "Saco Surpresa Padaria"
        elif len(categorias_saco) == 1:
            cat_unica = next(iter(categorias_saco)).capitalize()
            titulo_saco = f"Saco Surpresa {cat_unica}"
        else:
            titulo_saco = "Saco Surpresa Misto"

        sacos_gerados.append({
            "chave_interna": f"saco_int_{idx_s}",
            "titulo": titulo_saco,
            "preco_base": preco_base_saco,
            "desconto_pct": desconto_pct,
            "preco_final": preco_final_saco,
            "lotes_consumo": lotes_consumo,
            "vendido": False,
        })

    return sacos_gerados

def consolidar_sacos_para_esl(sacos_ativos: list[dict]) -> list[dict]:
    """
    Agrupa sacos surpresa idênticos (mesmo nome, preço base, desconto e preço final)
    num único preçário ESL com contador de disponibilidade, evitando 20 preçários iguais.
    """
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

def executar_orquestracao(cenario_perturbacao: str) -> None:
    gestor = GestorBaseDadosTemporal(total_produtos=1000, seed=2026)
    data_ref = date.today()
    catalogo_copia, lotes_copia = gestor.gerar_dataset_temporal(data_ref=data_ref)
    catalogo_map = {p["produto_id"]: p for p in catalogo_copia}

    if cenario_perturbacao == "Quebra Repentina de Clientes (-50% Procura)":
        for p in catalogo_copia:
            p["vendas_medias_diarias"] = max(0.2, round(p["vendas_medias_diarias"] * 0.5, 2))
    elif cenario_perturbacao == "Feriado / Loja Fechada Amanhã (Urgência Máxima)":
        for lote in lotes_copia:
            if lote["dias_para_expirar"] <= 3:
                lote["dias_para_expirar"] = 1
                lote["data_validade"] = data_ref.isoformat()
    elif cenario_perturbacao == "Pico de Stock Excedente nas Frutas/Frescos":
        for lote in lotes_copia:
            prod = catalogo_map.get(lote["produto_id"], {})
            if prod.get("categoria") in ["carne", "fruta"]:
                lote["quantidade_disponivel"] = round(lote["quantidade_disponivel"] * 2.5, 1)

    resultados_lote = []
    logs_cards = []

    for lote in lotes_copia:
        prod = catalogo_map.get(lote["produto_id"], {})
        pvp = prod.get("pvp", 0.0)
        desc_campanha = prod.get("desconto_campanha", 0.0)
        periodo_campanha = prod.get("periodo_campanha", "")
        unidade = prod.get("unidade_medida", "un")
        dias = lote["dias_para_expirar"]

        if dias > 5:
            lote["desconto_validade"] = 0.0
            lote["desconto_csp_aprovado"] = 0.0
            desc_efetivo, preco_final = calcular_preco_efetivo_lote(lote, prod)
            lote["preco_final_atual"] = preco_final
            lote["destino_final"] = "prateleira_desconto"
            lote["estado_csp"] = "Aprovado"

            resultados_lote.append({
                "Lote": lote["lote_id"],
                "Cód. Artigo": prod["produto_id"],
                "Produto": prod["nome"],
                "Categoria": prod["categoria"].capitalize(),
                "Stock": f"{lote['quantidade_disponivel']:.1f} {unidade}",
                "Validade": f"{formatar_data_pt(lote['data_validade'])} ({dias}d)",
                "PVP": formatar_eur(pvp),
                "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
                "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
                "Desc. Validade": "—",
                "Preço Ativo": formatar_eur(preco_final),
                "Destino Operacional": "Prateleira (Etiqueta ESL)",
                "Validação CSP": "✅ Aprovado",
            })
            continue

        estado_grafo = {
            "lote_atual": lote,
            "produto_catalogo": prod,
            "catalogo_produtos": catalogo_copia,
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
        )

        desc_final = val_csp["desconto_ajustado"]
        destino_final = val_csp["destino_ajustado"]
        lote["desconto_csp_aprovado"] = desc_final

        if destino_final in ["prateleira_desconto", "sacos_surpresa"] and desc_final > desc_campanha:
            lote["desconto_validade"] = desc_final
        else:
            lote["desconto_validade"] = 0.0

        desc_efetivo, preco_final = calcular_preco_efetivo_lote(lote, prod)
        lote["preco_final_atual"] = preco_final
        lote["destino_final"] = destino_final
        lote["estado_csp"] = "Aprovado" if val_csp["valido"] else "Ajustado pelo CSP"
        if lote["desconto_validade"] >= 0.35:
            lote["estado"] = "promocao_critica"

        preco_exibido_tabela = (
            "Retirado (Cozinha/Doação)"
            if destino_final in ["cozinha_interna", "doacao_externa"]
            else formatar_eur(preco_final)
        )

        resultados_lote.append({
            "Lote": lote["lote_id"],
            "Cód. Artigo": prod["produto_id"],
            "Produto": prod["nome"],
            "Categoria": prod["categoria"].capitalize(),
            "Stock": f"{lote['quantidade_disponivel']:.1f} {unidade}",
            "Validade": f"{formatar_data_pt(lote['data_validade'])} ({dias}d)",
            "PVP": formatar_eur(pvp),
            "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
            "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
            "Desc. Validade": f"-{int(lote['desconto_validade'] * 100)}%" if lote["desconto_validade"] > 0 else "—",
            "Preço Ativo": preco_exibido_tabela,
            "Destino Operacional": formatar_destino_legivel(destino_final),
            "Validação CSP": "✅ Aprovado" if val_csp["valido"] else "🛡️ Ajustado",
        })

        logs_cards.append({
            "lote_id": lote["lote_id"],
            "produto_id": prod["produto_id"],
            "nome": prod["nome"],
            "categoria": prod["categoria"].capitalize(),
            "dias": dias,
            "quantidade": f"{lote['quantidade_disponivel']:.1f} {unidade}",
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
        })

    sacos_surpresa = construir_sacos_surpresa_equilibrados(lotes_copia, catalogo_map, tamanho_alvo_saco=4)
    db_ok, db_msg = gestor.registar_telemetria_sqlite(data_ref, lotes_copia, cenario_perturbacao)

    st.session_state.resultados_simulacao = resultados_lote
    st.session_state.logs_estruturados = logs_cards
    st.session_state.lotes_simulados = lotes_copia
    st.session_state.catalogo_simulado = catalogo_copia
    st.session_state.sacos_surpresa_lista = sacos_surpresa
    st.session_state.cenario_ativo = cenario_perturbacao
    st.session_state.data_referencia_ativa = data_ref
    st.session_state.db_status = (db_ok, db_msg)


# ==============================================================================
# INICIALIZAÇÃO AUTOMÁTICA EM TEMPO REAL
# ==============================================================================
if "resultados_simulacao" not in st.session_state:
    st.session_state.resultados_simulacao = None

precisa_recalcular = (
    st.session_state.resultados_simulacao is None
    or simular_btn
    or st.session_state.get("data_referencia_ativa") != date.today()
)

if precisa_recalcular:
    with st.spinner("A sincronizar base de dados em tempo real (1.000 lotes produtos) e a executar agentes..."):
        executar_orquestracao(perturbacao)

data_ativa = st.session_state.data_referencia_ativa
db_ok, db_msg = st.session_state.db_status

st.info(
    f"📅 **Data Operacional (Tempo Real):** `{data_ativa.strftime('%d/%m/%Y')}` "
    f"&nbsp;|&nbsp; 🗄️ **Base de Dados (SQLite):** {db_msg}"
)

# ==============================================================================
# LAYOUT PRINCIPAL EM ABAS
# ==============================================================================
tab1, tab2, tab3 = st.tabs([
    "📊 Dashboard de Operações (200 Artigos)",
    "🏷️ Etiquetas Eletrónicas (ESL)",
    "🧠 Raciocínio dos Agentes"
])

# ------------------------------------------------------------------------------
# ABA 1: DASHBOARD DE OPERAÇÕES
# ------------------------------------------------------------------------------
with tab1:
    catalogo_atual = st.session_state.catalogo_simulado
    lotes_atual = st.session_state.lotes_simulados

    total_prods = len(catalogo_atual)
    prods_validade_curta = len({l["produto_id"] for l in lotes_atual if l["dias_para_expirar"] <= 5})
    pct_validade_curta = (prods_validade_curta / total_prods) * 100

    prods_campanha = sum(1 for p in catalogo_atual if p["desconto_campanha"] > 0)
    pct_campanha = (prods_campanha / total_prods) * 100

    lotes_com_desc_val = [l for l in lotes_atual if l.get("desconto_validade", 0.0) > 0 and l["quantidade_disponivel"] > 0]
    ajustes_csp = sum(1 for l in lotes_atual if l.get("estado_csp") != "Aprovado")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Catálogo Ativo</div>'
            f'<div class="kpi-value">{total_prods}</div>'
            f'<div class="kpi-sub">{len(lotes_atual)} lotes físicos</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Validade 1 a 5 Dias</div>'
            f'<div class="kpi-value" style="color:#dc2626;">{pct_validade_curta:.1f}%</div>'
            f'<div class="kpi-sub">{prods_validade_curta} produtos</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Em Campanha Semanal</div>'
            f'<div class="kpi-value" style="color:#0369a1;">{pct_campanha:.1f}%</div>'
            f'<div class="kpi-sub">{prods_campanha} produtos</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Lotes c/ Desc. Validade</div>'
            f'<div class="kpi-value" style="color:#059669;">{len(lotes_com_desc_val)}</div>'
            f'<div class="kpi-sub">{ajustes_csp} ajustes CSP</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    f1, f2 = st.columns([2, 1])
    with f1:
        pesquisa_tab = st.text_input("🔎 Filtrar inventário por produto, código ou lote:", placeholder="Ex: Salmão, Pão, PROD-0001, LOTE1001...")
    with f2:
        filtro_validade_tab = st.selectbox("Filtrar por destino/validade:", ["Todos os Lotes", "1 a 5 dias", "Sacos Surpresa", "Superior a 5 dias"])

    df_res = pd.DataFrame(st.session_state.resultados_simulacao)
    if pesquisa_tab:
        mask = (
            df_res["Produto"].str.contains(pesquisa_tab, case=False, na=False)
            | df_res["Cód. Artigo"].str.contains(pesquisa_tab, case=False, na=False)
            | df_res["Lote"].str.contains(pesquisa_tab, case=False, na=False)
        )
        df_res = df_res[mask]

    if filtro_validade_tab == "1 a 5 dias":
        df_res = df_res[df_res["Validade"].str.contains(r"\([1-5]d\)", regex=True)]
    elif filtro_validade_tab == "Sacos Surpresa":
        df_res = df_res[df_res["Destino Operacional"].str.contains("Sacos Surpresa", na=False)]
    elif filtro_validade_tab == "Superior a 5 dias":
        df_res = df_res[~df_res["Validade"].str.contains(r"\([1-5]d\)", regex=True)]

    st.dataframe(df_res, use_container_width=True, hide_index=True, height=440)

# ------------------------------------------------------------------------------
# ABA 2: ETIQUETAS ELETRÓNICAS (ESL) UNIFICADAS (PRODUTOS + SACOS SURPRESA)
# ------------------------------------------------------------------------------
with tab2:
    st.subheader("🏷️ Etiquetas Eletrónicas de Prateleira (ESL)")

    lotes_esl = st.session_state.lotes_simulados
    catalogo_esl = st.session_state.catalogo_simulado
    sacos_ativos = [s for s in st.session_state.get("sacos_surpresa_lista", []) if not s.get("vendido")]
    grupos_sacos_esl = consolidar_sacos_para_esl(sacos_ativos)

    lotes_por_prod: dict[str, list[dict]] = {}
    for l in lotes_esl:
        lotes_por_prod.setdefault(l["produto_id"], []).append(l)

    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        pesquisa_esl = st.text_input("🔎 Pesquisar artigo na ESL:", placeholder="Ex: Saco Surpresa, Salmão, Bife, Pão, Iogurte...")

    # Lista unificada: Sacos Surpresa consolidados + Produtos do catálogo na mesma grelha
    itens_unificados = []
    for grupo_saco in grupos_sacos_esl:
        if not pesquisa_esl or pesquisa_esl.lower() in grupo_saco["titulo"].lower():
            itens_unificados.append({"tipo": "saco", "dados": grupo_saco})

    for prod in catalogo_esl:
        if (
            not pesquisa_esl
            or pesquisa_esl.lower() in prod["nome"].lower()
            or pesquisa_esl.lower() in prod["produto_id"].lower()
        ):
            itens_unificados.append({"tipo": "produto", "dados": prod})

    por_pagina = 18
    total_paginas = max(1, (len(itens_unificados) + por_pagina - 1) // por_pagina)
    with col_f2:
        pagina_atual = st.number_input(f"Página (1 a {total_paginas}):", min_value=1, max_value=total_paginas, value=1)

    inicio = (pagina_atual - 1) * por_pagina
    fim = inicio + por_pagina
    pagina_items = itens_unificados[inicio:fim]

    cols = st.columns(3, gap="medium")

    for idx, item_esl in enumerate(pagina_items):
        if item_esl["tipo"] == "saco":
            grupo = item_esl["dados"]
            qtd_disp = len(grupo["sacos_instancias"])
            qr_saco = f"https://api.qrserver.com/v1/create-qr-code/?size=80x80&data={quote(grupo['titulo'] + '|' + str(grupo['preco_final']))}"

            # Sem conteúdo revelado e sem ID no cabeçalho; múltiplos lotes de sacos partilham o mesmo nome
            esl_html = (
                f'<div class="esl-bezel">'
                f'<div class="esl-screen">'
                f'<div>'
                f'<div class="esl-header">'
                f'<div class="esl-prod-name">{grupo["titulo"]}</div>'
                f'</div>'
                f'<div class="esl-middle">'
                f'<div>'
                f'<div class="esl-pum">PREÇO BASE</div>'
                f'<div class="esl-strike-wrap">PVP {formatar_eur(grupo["preco_base"])} <span class="esl-unit-tag">SACO</span></div>'
                f'</div>'
                f'<div class="esl-saco-stock">{qtd_disp} {"saco disp." if qtd_disp == 1 else "sacos disp."}</div>'
                f'</div>'
                f'</div>'
                f'<div>'
                f'<div class="esl-footer">'
                f'<img src="{qr_saco}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group">'
                f'<div class="esl-discount-badge">-{grupo["desconto_pct"]}%</div>'
                f'<div class="esl-price-right">'
                f'<div class="esl-pum">DESC. VALIDADE</div>'
                f'<div class="esl-big-price">{formatar_eur(grupo["preco_final"])} <span class="esl-unit-tag">SACO</span></div>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div class="esl-validade-bar">Desconto a produtos com Data de Validade: &nbsp; {formatar_data_pt(data_ativa.isoformat())}</div>'
                f'</div>'
                f'</div>'
                f'</div>'
            )

            with cols[idx % 3]:
                st.markdown(esl_html, unsafe_allow_html=True)
                btn_saco_key = f"sell_saco_grp_{pagina_atual}_{idx}"
                if st.button(f"🛍️ Vender 1 {grupo['titulo']}", key=btn_saco_key, use_container_width=True):
                    saco_vender = grupo["sacos_instancias"][0]
                    saco_vender["vendido"] = True
                    lotes_map_sim = {l["lote_id"]: l for l in st.session_state.lotes_simulados}
                    for l_id, qtd_abater in saco_vender["lotes_consumo"].items():
                        lote_ref = lotes_map_sim.get(l_id)
                        if lote_ref:
                            lote_ref["quantidade_disponivel"] = max(0.0, round(lote_ref["quantidade_disponivel"] - qtd_abater, 1))
                            if lote_ref["quantidade_disponivel"] <= 0:
                                lote_ref["estado"] = "esgotado"
                            for row in st.session_state.resultados_simulacao:
                                if row["Lote"] == l_id:
                                    un_row = row["Stock"].split(" ")[-1]
                                    row["Stock"] = f"{lote_ref['quantidade_disponivel']:.1f} {un_row}"
                                    if lote_ref["quantidade_disponivel"] <= 0:
                                        row["Destino Operacional"] = "Vendido em Saco Surpresa"
                    st.rerun()
            continue

        # Renderização de produto normal na mesma grelha
        prod = item_esl["dados"]
        prod_id = prod["produto_id"]
        gtin = prod.get("gtin", "")
        nome = prod.get("nome", "Produto")
        unidade = prod.get("unidade_medida", "un")
        pvp = prod.get("pvp", 0.0)
        desc_campanha = prod.get("desconto_campanha", 0.0)
        periodo_campanha = prod.get("periodo_campanha", "")

        lotes_ativos_prod = obter_lotes_ativos_fefo(prod_id, lotes_por_prod)
        lotes_com_validade = [
            l for l in lotes_ativos_prod
            if l.get("desconto_validade", 0.0) > desc_campanha
        ]

        pum_base = calcular_pum(pvp, prod).replace(".", ",")
        qr_payload = f"01|{gtin}|SKU|{prod_id}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=80x80&data={quote(qr_payload)}"

        tem_desconto_validade = len(lotes_com_validade) > 0
        tem_folheto = desc_campanha > 0

        if tem_folheto:
            bloco_pvp_html = (
                f'<div>'
                f'<div class="esl-pum">{pum_base}</div>'
                f'<div class="esl-strike-wrap">PVP {formatar_eur(pvp)} <span class="esl-unit-tag">{unidade}</span></div>'
                f'</div>'
            )
        else:
            bloco_pvp_html = (
                f'<div>'
                f'<div class="esl-pum">{pum_base}</div>'
                f'<div class="esl-pvp-clean">PVP {formatar_eur(pvp)} <span class="esl-unit-tag">{unidade}</span></div>'
                f'</div>'
            )

        if tem_desconto_validade:
            lote_principal = lotes_com_validade[0]
            lotes_seguintes = lotes_com_validade[1:]

            desc_principal = lote_principal["desconto_validade"]
            _, preco_principal = calcular_preco_efetivo_lote(lote_principal, prod)
            pum_principal = calcular_pum(preco_principal, prod).replace(".", ",")
            data_val_principal = formatar_data_pt(lote_principal.get("data_validade", ""))

            topo_esq = bloco_pvp_html

            if tem_folheto:
                preco_folheto = round(pvp * (1 - desc_campanha), 2)
                pum_folheto = calcular_pum(preco_folheto, prod).replace(".", ",")
                topo_dir = (
                    f'<div class="esl-folheto-box">'
                    f'<div class="esl-pum">{pum_folheto}</div>'
                    f'<div><span class="esl-folheto-pct">-{int(desc_campanha * 100)}%</span> '
                    f'<span class="esl-folheto-price">{formatar_eur(preco_folheto)}</span> <span class="esl-unit-tag">{unidade}</span></div>'
                    f'<div class="esl-folheto-dates">Válido de {periodo_campanha}</div>'
                    f'</div>'
                )
            else:
                topo_dir = ""

            extras_html = ""
            if lotes_seguintes:
                linhas_extras = []
                for l_seg in lotes_seguintes:
                    d_efetivo, p_efetivo = calcular_preco_efetivo_lote(l_seg, prod)
                    val_seg = formatar_data_pt(l_seg.get("data_validade", ""))
                    linhas_extras.append(
                        f'<div class="esl-extra-lote-row">'
                        f'<span>-{int(d_efetivo * 100)}% ({formatar_eur(p_efetivo)} {unidade})</span>'
                        f'<span>Val. {val_seg}</span>'
                        f'</div>'
                    )
                extras_html = (
                    f'<div class="esl-extra-lotes">'
                    f'<div style="font-size:9.5px;font-weight:700;color:#334155;">Outros Descontos com Aproximação de Prazo de Validade:</div>'
                    f'{"".join(linhas_extras)}'
                    f'</div>'
                )

            footer_html = (
                f'<div class="esl-footer">'
                f'<img src="{qr_url}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group">'
                f'<div class="esl-discount-badge">-{int(desc_principal * 100)}%</div>'
                f'<div class="esl-price-right">'
                f'<div class="esl-pum">{pum_principal}</div>'
                f'<div class="esl-big-price">{formatar_eur(preco_principal)} <span class="esl-unit-tag">{unidade}</span></div>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div class="esl-validade-bar">Desconto a produtos com Data de Validade: &nbsp; {data_val_principal}</div>'
                f'{extras_html}'
            )

        elif tem_folheto:
            preco_folheto = round(pvp * (1 - desc_campanha), 2)
            pum_folheto = calcular_pum(preco_folheto, prod).replace(".", ",")
            topo_esq = bloco_pvp_html
            topo_dir = ""
            footer_html = (
                f'<div class="esl-footer">'
                f'<img src="{qr_url}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group">'
                f'<div class="esl-discount-badge" style="color:#0f172a;font-size:25px;">-{int(desc_campanha * 100)}%</div>'
                f'<div class="esl-price-right">'
                f'<div class="esl-pum">{pum_folheto}</div>'
                f'<div class="esl-folheto-main-price">{formatar_eur(preco_folheto)} <span class="esl-unit-tag">{unidade}</span></div>'
                f'</div>'
                f'</div>'
                f'</div>'
                f'<div class="esl-validade-bar" style="color:#334155;">Campanha válida de {periodo_campanha}</div>'
            )

        else:
            topo_esq = ""
            topo_dir = ""
            footer_html = (
                f'<div class="esl-footer">'
                f'<img src="{qr_url}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group">'
                f'<div class="esl-price-right">'
                f'<div class="esl-pum">{pum_base}</div>'
                f'<div class="esl-big-price">{formatar_eur(pvp)} <span class="esl-unit-tag">{unidade}</span></div>'
                f'</div>'
                f'</div>'
                f'</div>'
            )

        esl_html = (
            f'<div class="esl-bezel">'
            f'<div class="esl-screen">'
            f'<div>'
            f'<div class="esl-header">'
            f'<div class="esl-prod-name">{nome}</div>'
            f'<div class="esl-gtin">{gtin}</div>'
            f'</div>'
            f'<div class="esl-middle">{topo_esq}{topo_dir}</div>'
            f'</div>'
            f'<div>{footer_html}</div>'
            f'</div>'
            f'</div>'
        )

        with cols[idx % 3]:
            st.markdown(esl_html, unsafe_allow_html=True)
            if tem_desconto_validade:
                lote_prioritario = lotes_com_validade[0]
                btn_key = f"sell_{prod_id}_{lote_prioritario['lote_id']}_{pagina_atual}_{idx}"
                if st.button(f"🛒 Vender {lote_prioritario['lote_id']}", key=btn_key, use_container_width=True):
                    lote_prioritario["quantidade_disponivel"] = 0.0
                    lote_prioritario["estado"] = "esgotado"
                    for row in st.session_state.resultados_simulacao:
                        if row["Lote"] == lote_prioritario["lote_id"]:
                            row["Stock"] = f"0.0 {unidade}"
                            row["Destino Operacional"] = "Vendido na Caixa (Esgotado)"
                    st.rerun()

# ------------------------------------------------------------------------------
# ABA 3: RACIOCÍNIO DOS AGENTES
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("🧠 Cadeia de Decisão e Debate entre Agentes")
    logs_exibir = st.session_state.logs_estruturados[:30]
    for item in logs_exibir:
        badge_risco = "🔴 Risco Crítico" if item["risco_critico"] else "🟢 Controlado"
        badge_csp = "✅ CSP Aprovado" if item["csp_valido"] else "🛡️ Ajustado pelo CSP"
        titulo_expander = (
            f"{item['produto_id']} ({item['lote_id']}) | {item['nome']} — "
            f"Validade: {item['dias']}d | {badge_risco} | Resultado: {item['preco_final']} [{badge_csp}]"
        )

        with st.expander(titulo_expander, expanded=(item["produto_id"] in ["PROD-0001", "PROD-0002"])):
            st.markdown(f"**1️⃣ Agente de Controlo de Inventário** *(Stock: {item['quantidade']} | Excesso previsto: {item['excesso']})*")
            st.info(item["parecer_inventario"])

            st.markdown(f"**2️⃣ Agente de Logística e Destino Operacional** → Proposta: `{item['destino_proposto']}`")
            st.write(item["razao_logistica"])

            st.markdown(f"**3️⃣ Agente de Dynamic Pricing** → Desconto Proposto: `{item['desconto_proposto']}`")
            st.write(item["raciocinio_pricing"])

            st.markdown("**4️⃣ Auditoria do Módulo Regulador (CSP)**")
            if item["csp_valido"]:
                st.success(f"Conformidade legal e financeira validada. Preço final: **{item['preco_final']}** | Destino: **{item['destino_final']}**.")
            else:
                for erro in item["csp_erros"]:
                    st.warning(f"Intervenção CSP: {erro}")
                st.markdown(f"**Resultado Corrigido:** Desconto **{item['desconto_final']}** ({item['preco_final']}) | Destino: **{item['destino_final']}**.")