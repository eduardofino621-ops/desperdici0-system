import altair as alt
import random
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, ColumnsAutoSizeMode
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
        "A menos de 2 horas de fechar a loja.",
        "Quebra Repentina de Clientes (-50% Procura)",
        "Feriado / Loja Fechada Amanhã (Urgência Máxima)",
        "Pico de Stock Excedente nas Frutas/Frescos",
    ],

    key="select_perturbacao"
)

simular_btn = st.sidebar.button("▶️ Reexecutar Orquestração / Sincronizar DB", type="primary", width="stretch")
if st.sidebar.button("🗑️ Limpar Histórico da Sessão", width="stretch"):
    if st.session_state.get("historico_sessao"):
        st.session_state.historico_sessao = [st.session_state.historico_sessao[0]]
        st.rerun()

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================
@st.dialog("🧠 Cadeia de Decisão dos Agentes", width="large")
def mostrar_popup_agentes(lote_id: str):
    item = next(
        (x for x in st.session_state.get("logs_estruturados", []) if x.get("lote_id") == lote_id),
        None,
    )
    if not item:
        st.info(
            f"O lote **{lote_id}** tem validade superior a 5 dias, pelo que se mantém em operação normal "
            "sem necessidade de intervenção dos agentes de IA."
        )
        return

    badge_risco = "🔴 Risco Crítico" if item["risco_critico"] else "🟢 Controlado"
    badge_csp = "✅ CSP Aprovado" if item["csp_valido"] else "🛡️ Ajustado pelo CSP"
    st.markdown(f"### {item['produto_id']} ({item['lote_id']}) — {item['nome']}")
    st.caption(f"Validade: {item['dias']}d | {badge_risco} | Resultado: {item['preco_final']} [{badge_csp}]")

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

def formatar_eur(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",") + "€"

def sublinhar_texto(texto: str) -> str:
    return "".join(f"{c}\u0332" for c in texto)

def formatar_stock(qtd: float, unidade: str) -> str:
    if unidade == "kg":
        return f"{qtd:.1f} {unidade}"
    return f"{int(round(qtd))} {unidade}"

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
        "descarte_obrigatorio": "Descarte Obrigatório",
        "doacao_externa": "Doação Externa (Instituições de Caridade)",
        "racao_animal": "Doação Externa (Parceria com Produção de Ração Animal)",
    }
    return mapa.get(destino, destino.replace("_", " ").title())

CORES_DECISAO = {
    "Prateleira (Normal/Campanha)": "#52606D",
    "Desc. Validade (ESL)": "#1E6F8C",
    "Sacos Surpresa": "#C88A2E",
    "Cozinha Interna": "#8B3A7B",
    "Doação (Caridade)": "#3E8E41",
    "Doação (Ração Animal)": "#CC6633",
    "Descarte Obrigatório": "#B8433E",
}

def classificar_decisao_lote(lote: dict) -> str:
    destino = lote.get("destino_final", "prateleira_desconto")
    if destino == "sacos_surpresa":
        return "Sacos Surpresa"
    if destino == "cozinha_interna":
        return "Cozinha Interna"
    if destino == "doacao_externa":
        return "Doação (Caridade)"
    if destino == "racao_animal":
        return "Doação (Ração Animal)"
    if destino == "descarte_obrigatorio":
        return "Descarte Obrigatório"
    if lote.get("desconto_validade", 0.0) > 0:
        return "Desc. Validade (ESL)"
    return "Prateleira (Normal/Campanha)"

def _formatar_delta(atual: float, base: float, sufixo: str = "", casas: int = 0) -> str:
    diff = atual - base
    if abs(diff) < 1e-6:
        return '<span style="color:#64748b;font-weight:600;">(= igual ao início)</span>'
    sinal = "+" if diff > 0 else ""
    cor = "#059669" if diff > 0 else "#dc2626"
    val_fmt = f"{diff:.{casas}f}".replace(".", ",") if casas > 0 else f"{int(round(diff))}"
    return f'<span style="color:{cor};font-weight:700;">({sinal}{val_fmt}{sufixo} vs. início)</span>'

def renderizar_cartoes_kpi(kpis: dict, kpis_base: dict | None = None) -> None:
    d_val = ""
    d_desc = ""
    d_csp = ""
    if kpis_base is not None:
        d_val = " " + _formatar_delta(kpis["pct_validade_curta"], kpis_base["pct_validade_curta"], " pp", casas=1)
        d_desc = " " + _formatar_delta(kpis["lotes_desc_val"], kpis_base["lotes_desc_val"])
        d_csp = " " + _formatar_delta(kpis["ajustes_csp"], kpis_base["ajustes_csp"])

    pct_val_str = f"{kpis['pct_validade_curta']:.1f}%".replace(".", ",")
    pct_camp_str = f"{kpis['pct_campanha']:.1f}%".replace(".", ",")
    total_lotes_str = f"{kpis['total_lotes']:,}".replace(",", ".")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Catálogo Ativo</div>'
            f'<div class="kpi-value">{kpis["total_prods"]}</div>'
            f'<div class="kpi-sub">{total_lotes_str} lotes</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Validade 1 a 5 Dias</div>'
            f'<div class="kpi-value" style="color:#dc2626;">{pct_val_str}</div>'
            f'<div class="kpi-sub">{kpis["prods_validade_curta"]} produtos{d_val}</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Em Campanha Semanal</div>'
            f'<div class="kpi-value" style="color:#0369a1;">{pct_camp_str}</div>'
            f'<div class="kpi-sub">{kpis["prods_campanha"]} produtos</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Lotes c/ Desc. Validade</div>'
            f'<div class="kpi-value" style="color:#059669;">{kpis["lotes_desc_val"]}</div>'
            f'<div class="kpi-sub">{kpis["ajustes_csp"]} ajustes CSP{d_desc}</div></div>',
            unsafe_allow_html=True,
        )

def renderizar_analise_decisoes(snapshot: dict, snapshot_base: dict | None = None, chave_prefixo: str = "atual") -> None:
    df_dec = pd.DataFrame(snapshot["registos_decisao"])
    so_risco = st.toggle(
        "Focar apenas nos lotes analisados pelos Agentes (Validade ≤ 5 dias)",
        value=True,
        key=f"toggle_risco_{chave_prefixo}",
    )

    df_filt = df_dec[df_dec["Dias"] <= 5] if so_risco else df_dec
    if df_filt.empty:
        st.info("Sem lotes para apresentar neste filtro.")
        return

    # 1. Quantificação global das decisões (Gráfico de Barras + Tabela Comparativa)
    contagem = df_filt["Decisão"].value_counts().reset_index()
    contagem.columns = ["Decisão", "Lotes"]
    total_lotes_filt = int(contagem["Lotes"].sum())
    contagem["Percentagem"] = contagem["Lotes"].apply(
        lambda x: f"{(x / max(1, total_lotes_filt)) * 100:.1f}%".replace(".", ",")
    )

    col_bar, col_tab = st.columns([3, 2], gap="large")
    with col_bar:
        st.markdown("**📊 Quantificação das Decisões por Destino (n.º de lotes)**")
        max_lotes = int(contagem["Lotes"].max()) if not contagem.empty else 10
        base_bar = alt.Chart(contagem).encode(
            y=alt.Y("Decisão:N", sort="-x", title=None),
            x=alt.X(
                "Lotes:Q",
                title="Nº de Lotes",
                scale=alt.Scale(domain=[0, max(10, int(max_lotes * 1.15))]),
            ),
            tooltip=["Decisão:N", "Lotes:Q", "Percentagem:N"],
        )
        barras = base_bar.mark_bar(cornerRadiusEnd=5, height=24).encode(
            color=alt.Color(
                "Decisão:N",
                scale=alt.Scale(domain=list(CORES_DECISAO.keys()), range=list(CORES_DECISAO.values())),
                legend=None,
            )
        )
        rotulos = base_bar.mark_text(align="left", dx=6, fontWeight="bold").encode(
            text=alt.Text("Lotes:Q")
        )
        grafico_bar = (
            (barras + rotulos)
            .properties(height=max(190, len(contagem) * 38))
            .configure_view(stroke=None)
            .configure_axis(labelLimit=220)
        )
        st.altair_chart(grafico_bar, theme="streamlit", width="stretch")

    with col_tab:
        st.markdown("**📋 Resumo Quantitativo**")
        df_resumo = contagem[["Decisão", "Lotes", "Percentagem"]].copy()
        if snapshot_base is not None:
            df_b = pd.DataFrame(snapshot_base["registos_decisao"])
            df_b = df_b[df_b["Dias"] <= 5] if so_risco else df_b
            mapa_base = df_b["Decisão"].value_counts().to_dict()
            df_resumo["Início"] = df_resumo["Decisão"].map(lambda d: int(mapa_base.get(d, 0)))
            df_resumo["Δ"] = df_resumo["Lotes"] - df_resumo["Início"]
            df_resumo["Δ"] = df_resumo["Δ"].apply(lambda v: f"+{v}" if v > 0 else str(v))
            df_resumo = df_resumo[["Decisão", "Início", "Lotes", "Δ", "Percentagem"]]
        st.dataframe(df_resumo, hide_index=True, width="stretch")

    # 2. Gráfico Stacked Bar (100%) por Categoria
    st.markdown("**📊 Distribuição das Decisões por Categoria (%)**")
    legenda_html = " &nbsp;&nbsp; ".join(
        f'<span style="font-size:12px;color:inherit;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{cor};margin-right:5px;"></span>'
        f'{nome}</span>'
        for nome, cor in CORES_DECISAO.items()
        if nome in set(df_filt["Decisão"])
    )
    st.markdown(f'<div style="margin-bottom:10px;">{legenda_html}</div>', unsafe_allow_html=True)

    ordem_decisoes = list(CORES_DECISAO.keys())
    mapa_ordem = {d: i for i, d in enumerate(ordem_decisoes)}

    df_stack = (
        df_filt.groupby(["Categoria", "Decisão"])
        .size()
        .reset_index(name="Lotes")
    )
    totais_cat = df_stack.groupby("Categoria")["Lotes"].transform("sum")
    df_stack["Pct"] = (df_stack["Lotes"] / totais_cat) * 100.0
    df_stack["Ordem"] = df_stack["Decisão"].map(lambda d: mapa_ordem.get(d, 99))
    df_stack = df_stack.sort_values(["Categoria", "Ordem"]).reset_index(drop=True)

    df_stack["y_end"] = df_stack.groupby("Categoria")["Pct"].cumsum()
    df_stack["y_start"] = df_stack["y_end"] - df_stack["Pct"]
    df_stack["y_mid"] = (df_stack["y_start"] + df_stack["y_end"]) / 2.0
    df_stack["Pct_Fmt"] = df_stack["Pct"].apply(lambda v: f"{v:.1f}%".replace(".", ","))
    df_stack["Rotulo"] = df_stack.apply(
        lambda r: (
            f"{r['Pct']:.0f}%\n({int(r['Lotes'])} {'lote' if int(r['Lotes']) == 1 else 'lotes'})"
            if r["Pct"] >= 9.0
            else ""
        ),
        axis=1,
    )

    barras_stack = (
        alt.Chart(df_stack)
        .mark_bar(cornerRadius=5, width={"band": 0.62}, stroke="rgba(128,128,128,0.25)", strokeWidth=1)
        .encode(
            x=alt.X(
                "Categoria:N",
                title=None,
                axis=alt.Axis(labelAngle=0, labelFontSize=12, labelFontWeight="bold"),
            ),
            y=alt.Y(
                "y_start:Q",
                title="% de Lotes",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(labelExpr="datum.value + '%'"),
            ),
            y2="y_end:Q",
            color=alt.Color(
                "Decisão:N",
                scale=alt.Scale(domain=ordem_decisoes, range=list(CORES_DECISAO.values())),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Categoria:N", title="Categoria"),
                alt.Tooltip("Decisão:N", title="Decisão"),
                alt.Tooltip("Lotes:Q", title="Nº de Lotes"),
                alt.Tooltip("Pct_Fmt:N", title="Percentagem"),
            ],
        )
    )

    rotulos_stack = (
        alt.Chart(df_stack)
        .mark_text(color="#ffffff", fontSize=11, fontWeight="bold", lineBreak="\n")
        .encode(
            x=alt.X("Categoria:N"),
            y=alt.Y("y_mid:Q"),
            text=alt.Text("Rotulo:N"),
        )
    )

    grafico_stack = (
        (barras_stack + rotulos_stack)
        .properties(height=400)
        .configure_view(stroke=None)
    )
    st.altair_chart(grafico_stack, theme="streamlit", width="stretch")


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

    # Baralha com seed fixa para misturar pães grandes e pequenos em cada saco
    rng = random.Random(2026)
    rng.shuffle(pool_unidades)

    sacos = []
    saco_atual = []
    peso_atual = 0.0

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
            saco_atual = []
            peso_atual = 0.0

    return sacos

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
    fecho_loja_2h = (cenario_perturbacao == "A menos de 2 horas de fechar a loja.")
    gestor = GestorBaseDadosTemporal(total_produtos=200, seed=2026)
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
                nova_qtd = lote["quantidade_disponivel"] * 2.5
                lote["quantidade_disponivel"] = round(nova_qtd, 1) if prod.get("unidade_medida") == "kg" else int(round(nova_qtd))

    resultados_lote = []
    logs_cards = []

    stock_total_padaria_urgente = sum(
    l["quantidade_disponivel"] * catalogo_map.get(l["produto_id"], {}).get("conteudo_liquido", 0.10)
    for l in lotes_copia
    if l["dias_para_expirar"] <= 1
    and l["quantidade_disponivel"] > 0
    and catalogo_map.get(l["produto_id"], {}).get("categoria") == "padaria"
)

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
                "Stock": formatar_stock(lote['quantidade_disponivel'], unidade),
                "Validade": date.fromisoformat(lote["data_validade"]),
                "Dias": int(dias),
                "PVP": formatar_eur(pvp),
                "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
                "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
                "Desc. Validade": "—",
                "Preço Ativo": formatar_eur(preco_final),
                "Destino Operacional": "Prateleira (Etiqueta ESL)",
                "Consultar Validação CSP": f"✅ {sublinhar_texto('Aprovado')}",
            })
            continue

        estado_grafo = {
            "lote_atual": lote,
            "produto_catalogo": prod,
            "catalogo_produtos": catalogo_copia,
            "fecho_loja_2h": fecho_loja_2h
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
            fecho_loja_2h=fecho_loja_2h
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
            "Retirado (Cozinha/Doação/Ração)"
            if destino_final in ["cozinha_interna", "doacao_externa", "racao_animal"]
            else formatar_eur(preco_final)
        )

        resultados_lote.append({
            "Lote": lote["lote_id"],
            "Cód. Artigo": prod["produto_id"],
            "Produto": prod["nome"],
            "Categoria": prod["categoria"].capitalize(),
            "Stock": formatar_stock(lote['quantidade_disponivel'], unidade),
            "Validade": date.fromisoformat(lote["data_validade"]),
            "Dias": int(dias),
            "PVP": formatar_eur(pvp),
            "Campanha": f"-{int(desc_campanha * 100)}%" if desc_campanha > 0 else "—",
            "Período Campanha": periodo_campanha if desc_campanha > 0 else "—",
            "Desc. Validade": f"-{int(lote['desconto_validade'] * 100)}%" if lote["desconto_validade"] > 0 else "—",
            "Preço Ativo": preco_exibido_tabela,
            "Destino Operacional": formatar_destino_legivel(destino_final),
            "Consultar Validação CSP": (
            f"✅ {sublinhar_texto('Aprovado')}" if val_csp["valido"] else f"🛡️ {sublinhar_texto('Ajustado')}"),
        })

        logs_cards.append({
            "lote_id": lote["lote_id"],
            "produto_id": prod["produto_id"],
            "nome": prod["nome"],
            "categoria": prod["categoria"].capitalize(),
            "dias": dias,
            "quantidade": formatar_stock(lote['quantidade_disponivel'], unidade),
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

    sacos_surpresa = construir_sacos_surpresa_equilibrados(lotes_copia, catalogo_map, peso_alvo_kg=0.50, max_sacos=10)
    db_ok, db_msg = gestor.registar_telemetria_sqlite(data_ref, lotes_copia, cenario_perturbacao)

    st.session_state.resultados_simulacao = resultados_lote
    st.session_state.logs_estruturados = logs_cards
    st.session_state.lotes_simulados = lotes_copia
    st.session_state.catalogo_simulado = catalogo_copia
    st.session_state.sacos_surpresa_lista = sacos_surpresa
    st.session_state.cenario_ativo = cenario_perturbacao
    st.session_state.data_referencia_ativa = data_ref
    st.session_state.db_status = (db_ok, db_msg)

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

    if "historico_sessao" not in st.session_state:
        st.session_state.historico_sessao = []
    st.session_state.historico_sessao.append(snapshot)


# ==============================================================================
# INICIALIZAÇÃO AUTOMÁTICA EM TEMPO REAL
# ==============================================================================
if "resultados_simulacao" not in st.session_state:
    st.session_state.resultados_simulacao = None

precisa_recalcular = (
    st.session_state.resultados_simulacao is None
    or simular_btn
    or st.session_state.get("cenario_ativo") != perturbacao
    or st.session_state.get("data_referencia_ativa") != date.today()
)

if precisa_recalcular:
    with st.spinner("A sincronizar base de dados em tempo real (500 lotes) e a executar agentes..."):
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

    historico = st.session_state.get("historico_sessao", [])
    if historico:
        snap_inicial = historico[0]
        st.markdown(
            f"📌 **Início de Sessão:** `{snap_inicial['cenario']}` às **{snap_inicial['hora']}** do dia **{snap_inicial['data_str']}**"
        )
        renderizar_cartoes_kpi(snap_inicial["kpis"])

        # Histórico acumulado de todas as perturbações testadas nesta sessão
        for idx_h, snap in enumerate(historico[1:], start=1):
            st.markdown(
                f"<hr style='margin:14px 0;border-color:#2c2c2c;'>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"⚡ **Perturbação #{idx_h}:** \"{snap['cenario']}\" às **{snap['hora']}** do dia **{snap['data_str']}**"
            )
            renderizar_cartoes_kpi(snap["kpis"], kpis_base=snap_inicial["kpis"])

        # Painel de Quantificação + Queijinhos por Categoria (mostra a execução mais recente)
        snap_atual = historico[-1]
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander(
            f"📊 Quantificação das Decisões & Gráficos por Categoria — {snap_atual['cenario']} ({snap_atual['hora']})",
            expanded=True,
        ):
            renderizar_analise_decisoes(
                snapshot=snap_atual,
                snapshot_base=snap_inicial if len(historico) > 1 else None,
                chave_prefixo=f"snap_{len(historico)}",
            )

    st.markdown("<br>", unsafe_allow_html=True)

    if "filtro_cat_tab1" not in st.session_state:
        st.session_state.filtro_cat_tab1 = None

    categorias_tab1 = [
        ("bebidas", "🧃 Bebidas"),
        ("carne", "🥩 Carne"),
        ("charcutaria", "🥓 Charcutaria"),
        ("fruta", "🍎 Fruta"),
        ("laticinios", "🥛 Laticínios"),
        ("mercearia", "🛒 Mercearia"),
        ("padaria", "🥖 Padaria"),
        ("pescado", "🐟 Pescado"),
        
    ]
    for linha_cats in (categorias_tab1[:4], categorias_tab1[4:]):
        cols_cat = st.columns(4)
        for col_c, (cat_key, cat_label) in zip(cols_cat, linha_cats):
            with col_c:
                ativa = st.session_state.filtro_cat_tab1 == cat_key
                if st.button(
                    cat_label,
                    key=f"btn_tab1_cat_{cat_key}",
                    type="primary" if ativa else "secondary",
                    width="stretch",
                ):
                    st.session_state.filtro_cat_tab1 = None if ativa else cat_key
                    st.rerun()

    f1, f2 = st.columns([2, 1])
    with f1:
        pesquisa_tab = st.text_input(
            "🔎 Filtrar inventário por produto, código ou lote:",
            placeholder="Ex: Salmão, Pão, PROD-0001, LOTE1001...",
        )
    with f2:
        filtro_validade_tab = st.selectbox(
            "Filtrar por destino/validade:",
            ["Todos os Lotes", "1 a 5 dias", "Sacos Surpresa", "Superior a 5 dias"],
        )

    df_res = pd.DataFrame(st.session_state.resultados_simulacao)
    if st.session_state.filtro_cat_tab1:
        df_res = df_res[df_res["Categoria"].str.lower() == st.session_state.filtro_cat_tab1]

    if st.session_state.filtro_cat_tab1:
        df_res = df_res[df_res["Categoria"].str.lower() == st.session_state.filtro_cat_tab1]

    if pesquisa_tab:
        mask = (
            df_res["Produto"].str.contains(pesquisa_tab, case=False, na=False)
            | df_res["Cód. Artigo"].str.contains(pesquisa_tab, case=False, na=False)
            | df_res["Lote"].str.contains(pesquisa_tab, case=False, na=False)
        )
        df_res = df_res[mask]

    if filtro_validade_tab == "1 a 5 dias":
        df_res = df_res[df_res["Dias"] <= 5]
    elif filtro_validade_tab == "Sacos Surpresa":
        df_res = df_res[df_res["Destino Operacional"].str.contains("Sacos Surpresa", na=False)]
    elif filtro_validade_tab == "Superior a 5 dias":
        df_res = df_res[df_res["Dias"] > 5]

    df_estilo = df_res.style.set_properties(
        subset=["Consultar Validação CSP"],
        **{"color": "#38bdf8"},
    )

    if df_res.empty:
        st.info("ℹ️ Nenhum lote encontrado para os filtros selecionados.")
    else:
        df_grid = df_res.copy()
        df_grid["Validade"] = df_grid["Validade"].astype(str)

        fmt_data_pt = JsCode("""
            function(params) {
                if (!params.value) return '';
                var p = String(params.value).split('-');
                return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : params.value;
            }
        """)
        fmt_dias = JsCode("function(params) { return params.value != null ? params.value + 'd' : ''; }")
        clicar_csp = JsCode("""
            function(params) {
                params.node.setSelected(true, true);
            }
        """)

        gb = GridOptionsBuilder.from_dataframe(df_grid)
        gb.configure_default_column(
            sortable=True,
            filter=False,
            resizable=True,
            suppressSizeToFit=True,
            wrapHeaderText=True,
            autoHeaderHeight=True,
        )
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
        gb.configure_selection(selection_mode="single", use_checkbox=False)
        gb.configure_grid_options(
            enableCellTextSelection=True,
            ensureDomOrder=True,
            suppressRowClickSelection=True,
        )

        # Largura dinâmica com base na maior string de cada coluna (+ pequena folga)
        for col_nome in df_grid.columns:
            if col_nome == "Consultar Validação CSP":
                continue
            max_chars = int(df_grid[col_nome].astype(str).str.len().max())
            if col_nome == "Validade":
                larg = 110
            elif col_nome == "Dias":
                larg = 70
            else:
                larg = int(max(85, min(360, max_chars * 8.2 + 26)))

            if col_nome == "Validade":
                gb.configure_column(col_nome, width=larg, minWidth=larg, valueFormatter=fmt_data_pt)
            elif col_nome == "Dias":
                gb.configure_column(col_nome, width=larg, minWidth=larg, valueFormatter=fmt_dias)
            else:
                gb.configure_column(col_nome, width=larg, minWidth=larg)

        # Deteta automaticamente se o utilizador está em Light Mode ou Dark Mode
        tema_atual = getattr(getattr(st.context, "theme", None), "type", "dark") or "dark"
        eh_light = tema_atual == "light"

# Coluna fixa à direita, compacta (o título faz wrap em 2 linhas)
        gb.configure_column(
            "Consultar Validação CSP",
            width=135,
            minWidth=135,
            pinned="right",
            cellStyle={
                "color": "#0ea5e9",
                "textDecoration": "underline",
                "cursor": "pointer",
                "fontWeight": "600",
            },
            onCellClicked=clicar_csp,
        )

        # Paleta adaptativa automática via variáveis CSS nativas do Streamlit (Light & Dark)
        custom_css = {
            ".ag-root-wrapper": {
                "background-color": "var(--background-color) !important",
                "border": "1px solid rgba(128, 128, 128, 0.3) !important",
                "border-radius": "8px !important",
            },
            ".ag-header": {
                "background-color": "var(--secondary-background-color) !important",
                "border-bottom": "1px solid rgba(128, 128, 128, 0.3) !important",
            },
            ".ag-header-cell-text": {
                "color": "var(--text-color) !important",
                "font-weight": "600 !important",
                "line-height": "1.2 !important",
            },
            ".ag-row": {
                "background-color": "var(--background-color) !important",
                "color": "var(--text-color) !important",
                "border-bottom": "1px solid rgba(128, 128, 128, 0.18) !important",
            },
            ".ag-row-odd": {
                "background-color": "color-mix(in srgb, var(--text-color) 4%, var(--background-color)) !important",
            },
            ".ag-row-hover": {
                "background-color": "rgba(255, 75, 75, 0.14) !important",
            },
            ".ag-row-selected": {
                "background-color": "rgba(128, 128, 128, 0.22) !important",
            },
            ".ag-cell": {
                "color": "var(--text-color) !important",
            },
            ".ag-paging-panel": {
                "background-color": "var(--secondary-background-color) !important",
                "color": "var(--text-color) !important",
                "border-top": "1px solid rgba(128, 128, 128, 0.3) !important",
            },
            ".ag-icon": {
                "color": "var(--text-color) !important",
            },
        }
        
        if "aggrid_key_v" not in st.session_state:
            st.session_state["aggrid_key_v"] = 0
        if "popup_lote_pendente" not in st.session_state:
            st.session_state["popup_lote_pendente"] = None

        grid_resp = AgGrid(
            df_grid,
            key=f"tabela_operacoes_{st.session_state['aggrid_key_v']}",
            gridOptions=gb.build(),
            update_on=["selectionChanged"],
            columns_auto_size_mode=ColumnsAutoSizeMode.NO_AUTOSIZE,
            allow_unsafe_jscode=True,
            custom_css=custom_css,
            theme="streamlit",
            height=540,
            fit_columns_on_grid_load=False,
        )

        sel = grid_resp.get("selected_rows")
        lote_clicado = None
        if isinstance(sel, pd.DataFrame) and not sel.empty:
            lote_clicado = sel.iloc[0]["Lote"]
        elif isinstance(sel, list) and len(sel) > 0:
            lote_clicado = sel[0]["Lote"]

        if lote_clicado:
            st.session_state["popup_lote_pendente"] = lote_clicado
            st.session_state["aggrid_key_v"] += 1
            st.rerun()

        if st.session_state["popup_lote_pendente"]:
            lote_abrir = st.session_state["popup_lote_pendente"]
            st.session_state["popup_lote_pendente"] = None
            mostrar_popup_agentes(lote_abrir)

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

    # Identifica produtos cujas etiquetas sofreram alteração por decisão dos agentes (desconto de validade ativo)
    prods_alterados_agentes: set[str] = set()
    for p in catalogo_esl:
        p_id = p["produto_id"]
        desc_camp = p.get("desconto_campanha", 0.0)
        lotes_ativos_p = obter_lotes_ativos_fefo(p_id, lotes_por_prod)
        if any(l.get("desconto_validade", 0.0) > desc_camp for l in lotes_ativos_p):
            prods_alterados_agentes.add(p_id)

    # Estado do filtro selecionado
    if "filtro_esl_ativo" not in st.session_state:
        st.session_state.filtro_esl_ativo = "todos"

    def _definir_filtro_esl(novo_filtro: str) -> None:
        st.session_state.filtro_esl_ativo = novo_filtro
        st.session_state.esl_pagina = 1

    # Linha 1 de botões: Vistas principais (4 Casos no Topo / Risco Agentes / Sacos Surpresa)
    total_em_risco = len(prods_alterados_agentes) + len(grupos_sacos_esl)
    b_top1, b_top2, b_top3 = st.columns(3)
    with b_top1:
        if st.button(
            "⭐ Todos (4 Casos Demo no Topo)",
            key="btn_esl_todos",
            type="primary" if st.session_state.filtro_esl_ativo == "todos" else "secondary",
            width="stretch",
        ):
            _definir_filtro_esl("todos")
            st.rerun()
    with b_top2:
        if st.button(
            f"⚠️ Alterados pelos Agentes ({len(prods_alterados_agentes)} art. + {len(grupos_sacos_esl)} sacos surpresa)",
            key="btn_esl_risco",
            type="primary" if st.session_state.filtro_esl_ativo == "risco" else "secondary",
            width="stretch",
        ):
            _definir_filtro_esl("risco")
            st.rerun()
    with b_top3:
        if st.button(
            f"🛍️ Sacos Surpresa ({len(grupos_sacos_esl)})",
            key="btn_esl_sacos",
            type="primary" if st.session_state.filtro_esl_ativo == "sacos" else "secondary",
            width="stretch",
        ):
            _definir_filtro_esl("sacos")
            st.rerun()

    # Linhas 2 e 3 de botões: Categorias do catálogo
    categorias_botoes = [
        ("bebidas", "🧃 Bebidas"),
        ("carne", "🥩 Carne"),
        ("charcutaria", "🥓 Charcutaria"),
        ("fruta", "🍎 Fruta"),
        ("laticinios", "🥛 Laticínios"),
        ("mercearia", "🛒 Mercearia")
        ("padaria", "🥖 Padaria"),
        ("pescado", "🐟 Pescado"),
        
    ]
    for linha_cats in (categorias_botoes[:4], categorias_botoes[4:]):
        cols_cat = st.columns(4)
        for col_c, (cat_key, cat_label) in zip(cols_cat, linha_cats):
            with col_c:
                if st.button(
                    cat_label,
                    key=f"btn_esl_cat_{cat_key}",
                    type="primary" if st.session_state.filtro_esl_ativo == cat_key else "secondary",
                    width="stretch",
                ):
                    _definir_filtro_esl(cat_key)
                    st.rerun()

    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        pesquisa_esl = st.text_input(
            "🔎 Pesquisar artigo na ESL:",
            placeholder="Ex: Saco Surpresa, Salmão, Bife, Pão, Iogurte...",
        )

    filtro_atual = st.session_state.filtro_esl_ativo
    ids_demo = ["PROD-0001", "PROD-0002", "PROD-0003", "PROD-0004"]

    # Construção ordenada da lista de etiquetas conforme o filtro ativo
    itens_unificados = []

    def _passa_pesquisa_prod(prod: dict) -> bool:
        return (
            not pesquisa_esl
            or pesquisa_esl.lower() in prod["nome"].lower()
            or pesquisa_esl.lower() in prod["produto_id"].lower()
        )

    def _passa_pesquisa_saco(grupo: dict) -> bool:
        return not pesquisa_esl or pesquisa_esl.lower() in grupo["titulo"].lower()

    if filtro_atual == "todos":
        # 1.º: Os 4 casos de demonstração logo no topo (Validade+Campanha, Só Validade, Só Campanha, Sem Descontos)
        prods_por_id = {p["produto_id"]: p for p in catalogo_esl}
        for pid_demo in ids_demo:
            prod_demo = prods_por_id.get(pid_demo)
            if prod_demo and _passa_pesquisa_prod(prod_demo):
                itens_unificados.append({"tipo": "produto", "dados": prod_demo})

        # 2.º: Sacos Surpresa consolidados
        for grupo_saco in grupos_sacos_esl:
            if _passa_pesquisa_saco(grupo_saco):
                itens_unificados.append({"tipo": "saco", "dados": grupo_saco})

        # 3.º: Restantes artigos do catálogo
        for prod in catalogo_esl:
            if prod["produto_id"] not in ids_demo and _passa_pesquisa_prod(prod):
                itens_unificados.append({"tipo": "produto", "dados": prod})

    elif filtro_atual == "risco":
        # Primeiro produtos alterados pelos agentes (PROD-0001 e PROD-0002 no topo), depois Sacos Surpresa
        for prod in catalogo_esl:
            if prod["produto_id"] in prods_alterados_agentes and _passa_pesquisa_prod(prod):
                itens_unificados.append({"tipo": "produto", "dados": prod})
        for grupo_saco in grupos_sacos_esl:
            if _passa_pesquisa_saco(grupo_saco):
                itens_unificados.append({"tipo": "saco", "dados": grupo_saco})

    elif filtro_atual == "sacos":
        for grupo_saco in grupos_sacos_esl:
            if _passa_pesquisa_saco(grupo_saco):
                itens_unificados.append({"tipo": "saco", "dados": grupo_saco})

    else:
        # Filtro por categoria específica (mostra primeiro os que têm desconto de validade nessa categoria)
        prods_cat = [
            p for p in catalogo_esl
            if p.get("categoria") == filtro_atual and _passa_pesquisa_prod(p)
        ]
        prods_cat.sort(key=lambda p: (0 if p["produto_id"] in prods_alterados_agentes else 1, p["produto_id"]))
        for prod in prods_cat:
            itens_unificados.append({"tipo": "produto", "dados": prod})

        if filtro_atual == "padaria":
            for grupo_saco in grupos_sacos_esl:
                if "padaria" in grupo_saco["titulo"].lower() and _passa_pesquisa_saco(grupo_saco):
                    itens_unificados.append({"tipo": "saco", "dados": grupo_saco})

    por_pagina = 18
    total_paginas = max(1, (len(itens_unificados) + por_pagina - 1) // por_pagina)
    if "esl_pagina" not in st.session_state or st.session_state.esl_pagina > total_paginas:
        st.session_state.esl_pagina = 1

    with col_f2:
        pagina_atual = st.number_input(
            f"Página (1 a {total_paginas}):",
            min_value=1,
            max_value=total_paginas,
            key="esl_pagina",
        )

    if not itens_unificados:
        st.info("ℹ️ Nenhuma etiqueta encontrada para o filtro ou pesquisa selecionada.")
    else:
        inicio = (pagina_atual - 1) * por_pagina
        fim = inicio + por_pagina
        pagina_items = itens_unificados[inicio:fim]

        cols = st.columns(3, gap="medium")

        for idx, item_esl in enumerate(pagina_items):
            if item_esl["tipo"] == "saco":
                grupo = item_esl["dados"]
                qtd_disp = len(grupo["sacos_instancias"])
                qr_saco = f"https://api.qrserver.com/v1/create-qr-code/?size=80x80&data={quote(grupo['titulo'] + '|' + str(grupo['preco_final']))}"

                esl_html = (
                    f'<div class="esl-bezel">'
                    f'<div class="esl-screen">'
                    f'<div>'
                    f'<div class="esl-header">'
                    f'<div class="esl-prod-name">{grupo["titulo"]}</div>'
                    f'</div>'
                    f'<div class="esl-middle">'
                    f'<div>'
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
                    btn_saco_key = f"sell_saco_grp_{filtro_atual}_{pagina_atual}_{idx}"
                    if st.button(f"🛍️ Vender 1 {grupo['titulo']}", key=btn_saco_key, width="stretch"):
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
                                        row["Stock"] = formatar_stock(lote_ref['quantidade_disponivel'], un_row)
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
                    btn_key = f"sell_{filtro_atual}_{prod_id}_{lote_prioritario['lote_id']}_{pagina_atual}_{idx}"
                    if st.button(f"🛒 Vender {lote_prioritario['lote_id']}", key=btn_key, width="stretch"):
                        lote_prioritario["quantidade_disponivel"] = 0.0
                        lote_prioritario["estado"] = "esgotado"
                        for row in st.session_state.resultados_simulacao:
                            if row["Lote"] == lote_prioritario["lote_id"]:
                                row["Stock"] = formatar_stock(0.0, unidade)
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