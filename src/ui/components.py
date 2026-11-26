import altair as alt
import pandas as pd
import streamlit as st

from src.ui.styles import CORES_DECISAO


@st.dialog("🧠 Cadeia de Decisão dos Agentes", width="large")
def mostrar_popup_agentes(lote_id: str) -> None:
    item = st.session_state.get("logs_por_lote", {}).get(lote_id)
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

    # ==========================================================================
    # BLOCO VISUAL DO RAG (EVIDÊNCIAS RECUPERADAS)
    # ==========================================================================
    evidencias_rag = item.get("contexto_rag", [])
    with st.expander(f"📚 Contexto Recuperado via RAG ({len(evidencias_rag)} evidências)", expanded=True):
        if evidencias_rag:
            for ev in evidencias_rag:
                score_pct = int(round(ev.get("score", 0.0) * 100))
                st.markdown(f"**`{ev['id']}`** — Relevância TF-IDF: `{score_pct}%`")
                st.caption(ev["texto"])
        else:
            st.caption("Nenhuma regra sazonal ou histórica ultrapassou o limiar mínimo de similaridade para este lote.")

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

def _formatar_delta(atual: float, base: float, sufixo: str = "", casas: int = 0) -> str:
    diff = atual - base
    if abs(diff) < 1e-6:
        return '<span style="color:#64748b;font-weight:600;">(= igual ao início)</span>'
    sinal = "+" if diff > 0 else ""
    cor = "#059669" if diff > 0 else "#dc2626"
    val_fmt = f"{diff:.{casas}f}".replace(".", ",") if casas > 0 else f"{int(round(diff))}"
    return f'<span style="color:{cor};font-weight:700;">({sinal}{val_fmt}{sufixo} vs. início)</span>'


def renderizar_cartoes_kpi(kpis: dict, kpis_base: dict | None = None) -> None:
    d_val = " " + _formatar_delta(kpis["pct_validade_curta"], kpis_base["pct_validade_curta"], " pp", casas=1) if kpis_base else ""
    d_desc = " " + _formatar_delta(kpis["lotes_desc_val"], kpis_base["lotes_desc_val"]) if kpis_base else ""

    pct_val_str = f"{kpis['pct_validade_curta']:.1f}%".replace(".", ",")
    pct_camp_str = f"{kpis['pct_campanha']:.1f}%".replace(".", ",")
    total_lotes_str = f"{kpis['total_lotes']:,}".replace(",", ".")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Lotes Ativos em Catálogo</div>'
            f'<div class="kpi-value">{total_lotes_str}</div>'
            f'<div class="kpi-sub">{kpis["total_prods"]} produtos</div></div>',
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
    df_filt = df_dec[df_dec["Dias"] <= 5]
    if df_filt.empty:
        st.info("Sem lotes para apresentar neste filtro.")
        return

    contagem = df_filt["Decisão"].value_counts().reset_index()
    contagem.columns = ["Decisão", "Lotes"]
    total_lotes_filt = int(contagem["Lotes"].sum())
    contagem["Percentagem"] = contagem["Lotes"].apply(
        lambda x: f"{(x / max(1, total_lotes_filt)) * 100:.1f}%".replace(".", ",")
    )

    col_bar, col_tab = st.columns([3, 2], gap="large")
    with col_bar:
        st.markdown("**📊 Quantificação das Decisões dos Agentes por Destino (n.º de lotes)**")
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
        rotulos = base_bar.mark_text(align="left", dx=6, fontWeight="bold").encode(text=alt.Text("Lotes:Q"))
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
            df_b = df_b[df_b["Dias"] <= 5]
            mapa_base = df_b["Decisão"].value_counts().to_dict()
            df_resumo["Início"] = df_resumo["Decisão"].map(lambda d: int(mapa_base.get(d, 0)))
            df_resumo["Δ"] = (df_resumo["Lotes"] - df_resumo["Início"]).apply(
                lambda v: f"+{v}" if v > 0 else str(v)
            )
            df_resumo = df_resumo[["Decisão", "Início", "Lotes", "Δ", "Percentagem"]]
        st.dataframe(df_resumo, hide_index=True, width="stretch")

    st.markdown("**📊 Distribuição das Decisões por Categoria (%)**")
    decisoes_presentes = set(df_filt["Decisão"])
    legenda_html = " &nbsp;&nbsp; ".join(
        f'<span style="font-size:12px;color:inherit;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{cor};margin-right:5px;"></span>'
        f"{nome}</span>"
        for nome, cor in CORES_DECISAO.items()
        if nome in decisoes_presentes
    )
    st.markdown(f'<div style="margin-bottom:10px;">{legenda_html}</div>', unsafe_allow_html=True)

    ordem_decisoes = list(CORES_DECISAO.keys())
    mapa_ordem = {d: i for i, d in enumerate(ordem_decisoes)}

    df_stack = df_filt.groupby(["Categoria", "Decisão"]).size().reset_index(name="Lotes")
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

    selecao_cat = alt.selection_point(name="selecao_categoria", fields=["Categoria"])

    barras_stack = (
        alt.Chart(df_stack)
        .mark_bar(cornerRadius=5, width={"band": 0.62}, stroke="rgba(128,128,128,0.25)", strokeWidth=1)
        .encode(
            x=alt.X("Categoria:N", title=None, axis=alt.Axis(labelAngle=0, labelFontSize=12, labelFontWeight="bold")),
            y=alt.Y("y_start:Q", title="% de Lotes", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(labelExpr="datum.value + '%'")),
            y2="y_end:Q",
            color=alt.Color("Decisão:N", scale=alt.Scale(domain=ordem_decisoes, range=list(CORES_DECISAO.values())), legend=None),
            opacity=alt.condition(selecao_cat, alt.value(1.0), alt.value(0.45)),
            tooltip=[
                alt.Tooltip("Categoria:N", title="Categoria"),
                alt.Tooltip("Decisão:N", title="Decisão"),
                alt.Tooltip("Lotes:Q", title="Nº de Lotes"),
                alt.Tooltip("Pct_Fmt:N", title="Percentagem"),
            ],
        )
        .add_params(selecao_cat)
    )
    rotulos_stack = (
        alt.Chart(df_stack)
        .mark_text(color="#ffffff", fontSize=11, fontWeight="bold", lineBreak="\n")
        .encode(x=alt.X("Categoria:N"), y=alt.Y("y_mid:Q"), text=alt.Text("Rotulo:N"))
    )

    evento_stack = st.altair_chart(
        (barras_stack + rotulos_stack).properties(height=400).configure_view(stroke=None),
        theme="streamlit",
        width="stretch",
        on_select="rerun",
        selection_mode="selecao_categoria",
        key=f"chart_stack_{chave_prefixo}",
    )

    selecao = evento_stack.get("selection", {}).get("selecao_categoria", []) if evento_stack else []
    cat_clicada = selecao[0]["Categoria"].lower() if selecao else None
    chave_ultimo = f"ultimo_click_stack_{chave_prefixo}"

    if st.session_state.get(chave_ultimo) != cat_clicada:
        st.session_state[chave_ultimo] = cat_clicada
        if cat_clicada:
            st.session_state["filtro_cat_tab1"] = cat_clicada
            st.session_state["filtro_validade_tab1"] = "1 a 5 dias"
        else:
            st.session_state["filtro_cat_tab1"] = None