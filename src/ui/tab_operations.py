import pandas as pd
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder, JsCode
import streamlit as st
import altair as alt

from src.rag.retriever import RecuperadorRAG
from src.simulation.orchestrator import formatar_eur, formatar_numero_pt, _formatar_delta_pt, simular_horizonte_temporal
from src.ui.components import (
    mostrar_popup_agentes,
    renderizar_analise_decisoes,
    renderizar_cartoes_kpi,
)
from src.ui.styles import CATEGORIAS_UI


def _alternar_cat_tab1(cat_key: str) -> None:
    atual = st.session_state.get("filtro_cat_tab1")
    st.session_state.filtro_cat_tab1 = None if atual == cat_key else cat_key


@st.fragment
def _renderizar_tabela_operacoes() -> None:
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

    st.session_state.setdefault("filtro_cat_tab1", None)

    for linha_cats in (CATEGORIAS_UI[:4], CATEGORIAS_UI[4:]):
        cols_cat = st.columns(4)
        for col_c, (cat_key, cat_label) in zip(cols_cat, linha_cats):
            with col_c:
                ativa = st.session_state.filtro_cat_tab1 == cat_key
                st.button(
                    cat_label,
                    key=f"btn_tab1_cat_{cat_key}",
                    type="primary" if ativa else "secondary",
                    width="stretch",
                    on_click=_alternar_cat_tab1,
                    args=(cat_key,),
                )

    df_res = pd.DataFrame(st.session_state.resultados_simulacao)
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

    if df_res.empty:
        st.info("ℹ️ Nenhum lote encontrado para os filtros selecionados.")
        return

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
    clicar_csp = JsCode("function(params) { params.node.setSelected(true, true); }")

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

    for col_nome in df_grid.columns:
        if col_nome == "Consultar Validação CSP":
            continue
        max_chars = int(df_grid[col_nome].astype(str).str.len().max())
        if col_nome == "Validade":
            gb.configure_column(col_nome, width=110, minWidth=110, valueFormatter=fmt_data_pt)
        elif col_nome == "Dias":
            gb.configure_column(col_nome, width=70, minWidth=70, valueFormatter=fmt_dias)
        else:
            larg = int(max(85, min(360, max_chars * 8.2 + 26)))
            gb.configure_column(col_nome, width=larg, minWidth=larg)

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
        ".ag-row-hover": {"background-color": "rgba(255, 75, 75, 0.14) !important"},
        ".ag-row-selected": {"background-color": "rgba(128, 128, 128, 0.22) !important"},
        ".ag-cell": {"color": "var(--text-color) !important"},
        ".ag-paging-panel": {
            "background-color": "var(--secondary-background-color) !important",
            "color": "var(--text-color) !important",
            "border-top": "1px solid rgba(128, 128, 128, 0.3) !important",
        },
        ".ag-icon": {"color": "var(--text-color) !important"},
    }

    st.session_state.setdefault("aggrid_key_v", 0)
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
        st.session_state["aggrid_key_v"] += 1
        mostrar_popup_agentes(lote_clicado)


def renderizar_aba_operacoes() -> None:
    historico = st.session_state.get("historico_sessao", [])
    if historico:
        snap_inicial = historico[0]
        st.markdown(
            f"📌 **Início de Sessão:** `{snap_inicial['cenario']}` às **{snap_inicial['hora']}** do dia **{snap_inicial['data_str']}**"
        )
        renderizar_cartoes_kpi(snap_inicial["kpis"])

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
    _renderizar_tabela_operacoes()


def renderizar_historico_perturbacoes_sidebar() -> None:
    historico = st.session_state.get("historico_sessao", [])
    if len(historico) <= 1:
        return

    snap_inicial = historico[0]
    perturbs = [s for s in historico[1:] if s["cenario"] != "Nenhuma (Operação Normal)"]
    if not perturbs:
        return

    k_base = snap_inicial["kpis"]
    linhas_hist = []
    for idx_h, snap in enumerate(perturbs, start=1):
        k = snap["kpis"]
        diff_lotes = k["lotes_desc_val"] - k_base["lotes_desc_val"]
        diff_csp = k["ajustes_csp"] - k_base["ajustes_csp"]
        linhas_hist.append({
            "#": f"#{idx_h}",
            "Hora": snap["hora"],
            "Perturbação": snap["cenario"],
            "Lotes Desc.": f"{k['lotes_desc_val']} ({diff_lotes:+d})" if diff_lotes != 0 else f"{k['lotes_desc_val']} (=)",
            "CSP": f"{k['ajustes_csp']} ({diff_csp:+d})" if diff_csp != 0 else f"{k['ajustes_csp']} (=)",
        })

    with st.sidebar.expander(f"⚡ Histórico de Perturbações ({len(linhas_hist)})", expanded=False):
        st.dataframe(
            pd.DataFrame(linhas_hist),
            hide_index=True,
            width="stretch",
        )


def renderizar_explorador_rag() -> None:
    with st.sidebar.expander("📚 Base de Conhecimento & Motor RAG", expanded=False):
        rag = RecuperadorRAG()
        total_regras = sum(1 for d in rag.documentos if not d["id"].startswith("Histórico "))
        total_hist = len(rag.documentos) - total_regras

        c1, c2 = st.columns(2)
        c1.metric("Regras Fixas", total_regras)
        c2.metric("Registos SQLite", total_hist)

        filtro_origem = st.selectbox(
            "Origem do Conhecimento:",
            ["Todas", "Regras de Negócio Indexadas", "Registos Históricos (SQLite)"],
            key="rag_filtro_origem",
        )
        categorias_disponiveis = ["Todas"] + sorted({
            d.get("categoria", "geral").capitalize() for d in rag.documentos
        })
        filtro_cat = st.selectbox(
            "Categoria:",
            categorias_disponiveis,
            key="rag_filtro_cat",
        )

        docs_filtrados = []
        for d in rag.documentos:
            eh_sql = d["id"].startswith("Histórico ")
            if filtro_origem == "Regras de Negócio Indexadas" and eh_sql:
                continue
            if filtro_origem == "Registos Históricos (SQLite)" and not eh_sql:
                continue
            if filtro_cat != "Todas" and d.get("categoria", "geral").lower() != filtro_cat.lower():
                continue
            docs_filtrados.append(d)

        st.caption(f"A apresentar **{len(docs_filtrados)}** de **{len(rag.documentos)}** documentos.")
        if docs_filtrados:
            for d in docs_filtrados:
                badge_origem = "🗄️ SQLite" if d["id"].startswith("Histórico ") else "📘 Regra"
                cat_label = d.get("categoria", "geral").capitalize()
                st.markdown(f"- {badge_origem} | **`{d['id']}`** *({cat_label})*: {d['texto']}")
        else:
            st.info("Nenhum documento encontrado.")


def renderizar_resultados_multidia() -> None:
    res = st.session_state.get("resultado_multidia")
    if not res:
        return

    with st.expander(
        f"⏩ Resultados da Simulação Acelerada Multi-Dia ({res['dias_simulados']} dias)",
        expanded=True,
    ):
        if res.get("passos_execucao"):
            st.markdown("### 🧭 Passo a Passo da Execução Multi-Dia")
            for p in res.get("passos_execucao", []):
                exp_txt = (
                    f" — *Expirados:* {', '.join(p['exemplos_expirados'])}"
                    if p["exemplos_expirados"]
                    else " — *Zero desperdício neste dia*"
                )
                st.markdown(
                    f"**Passo {p['dia_num']} (`{p['data_str']}`)** | 🌦️ `{p['clima']}` | ⚡ `{p['cenario']}` *(Procura: {int(p['fator_procura'] * 100)}%)*\n"
                    f"1. **Agentes + CSP:** Avaliaram **{formatar_numero_pt(p['lotes_analisados_agentes'], 0)}** lotes críticos (≤ 5 dias) e montaram **{p['sacos_criados']}** Sacos Surpresa.\n"
                    f"2. **Vendas FEFO & Logística:** Escoadas **{formatar_numero_pt(p['vendidas'], 0)}** un/kg em loja (`{formatar_numero_pt(p['receita'], 2)}€`) e **{formatar_numero_pt(p['doadas'], 0)}** un/kg encaminhadas para Doação/Cozinha.\n"
                    f"3. **Fecho de Validades:** **{formatar_numero_pt(p['desperdicadas'], 0)}** un/kg expiraram sem compra{exp_txt}."
                )
            st.divider()

        # 1. Métricas do horizonte SEM setas (apenas contexto descritivo)
        st.markdown("### 📊 Visualização do Horizonte")
        ts_val = res.get("ts_pct", 0.0)
        atingiu_meta = ts_val > 90.0
        estado_meta = "✅ Meta atingida (> 90%)" if atingiu_meta else "⚠️ Abaixo da meta (≤ 90%)"

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Taxa de Salvamento (TS)", f"{formatar_numero_pt(ts_val, 1)}%")
            st.caption(estado_meta)
        with m2:
            st.metric("Total Vendido (Unid. / Kg)", formatar_numero_pt(res["total_vendidas"], 0))
            st.caption(f"Faturação bruta: {formatar_numero_pt(res['receita_total'], 2)}€")
        with m3:
            st.metric("Escoado p/ Doação / Reaproveit.", formatar_numero_pt(res["total_doadas_cozinha"], 0))
            st.caption(
                f"Doado (QD): {formatar_numero_pt(res.get('qd_kg', 0.0), 1)} kg · "
                f"Cozinha/Ração (QR): {formatar_numero_pt(res.get('qr_kg', 0.0), 1)} kg"
            )
        with m4:
            st.metric("Desperdício Final (Expirados)", formatar_numero_pt(res["total_desperdicadas"], 0))
            st.caption(f"Custo perda (compra+lixo): {formatar_numero_pt(res['custo_desperdicio'], 2)}€")
        with m5:
            st.metric("Taxa de Desperdício", f"{formatar_numero_pt(res['taxa_desperdicio_pct'], 1)}%")
            st.caption(f"Expirado / total ({res['dias_simulados']} dias)")

        st.caption(
            f"📐 **Fórmula TS = ((QVD + QD + QR) / QTAR) × 100:** "
            f"**QVD** (Vendidos c/ desconto) = `{formatar_numero_pt(res.get('qvd_kg', 0.0), 1)} kg` · "
            f"**QD** (Doados a instituições) = `{formatar_numero_pt(res.get('qd_kg', 0.0), 1)} kg` · "
            f"**QR** (Reaproveitados em cozinha/ração) = `{formatar_numero_pt(res.get('qr_kg', 0.0), 1)} kg` · "
            f"**QTAR** (Total de alimentos em risco) = `{formatar_numero_pt(res.get('qtar_kg', 0.0), 1)} kg`"
        )

        df_evo = pd.DataFrame(res["evolucao_diaria"]).copy()
        for col_num, casas in [
            ("Vendidas", 1),
            ("Doação / Cozinha", 1),
            ("Desperdiçadas (Expiradas)", 1),
            ("Receita (€)", 2),
        ]:
            if col_num in df_evo.columns:
                df_evo[col_num] = df_evo[col_num].apply(lambda v: formatar_numero_pt(float(v), casas))

        st.dataframe(df_evo, hide_index=True, width="stretch")

        # 2. Comparação Direta: Desperdíci0% vs. Modelo Tradicional
        base = res.get("comparacao_baseline")
        if base:
            st.divider()
            st.markdown("### ⚖️ Impacto Real: Desperdíci0% vs. Modelo Tradicional (Descontos Fixos 30% / 50%)")
            st.caption(
                "Mesmos 200 produtos, 500 lotes iniciais e perturbações diárias. "
                "O modelo tradicional aplica apenas 30% a 2 dias e 50% a 1 dia, sem IA/CSP, Sacos Surpresa nem encaminhamento."
            )

            ganho_ts = res["ts_pct"] - base["ts_pct"]
            reducao_desp_un = base["total_desperdicadas"] - res["total_desperdicadas"]
            reducao_desp_pct = (reducao_desp_un / max(1.0, base["total_desperdicadas"])) * 100
            poupanca_custo = base["custo_desperdicio"] - res["custo_desperdicio"]
            dif_receita = res["receita_total"] - base["receita_total"]

            k1, k2, k3, k4 = st.columns(4)
            k1.metric(
                "Ganho Taxa de Salvamento (TS)",
                _formatar_delta_pt(ganho_ts, " p.p.", 1),
                delta=f"Tradicional: {formatar_numero_pt(base['ts_pct'], 1)}% → Desperdíci0%: {formatar_numero_pt(res['ts_pct'], 1)}%",
                delta_color="normal" if ganho_ts >= 0 else "inverse",
            )
            k2.metric(
                "Desperdício Evitado (vs. Tradicional)",
                f"{formatar_numero_pt(reducao_desp_un, 0)} un/kg",
                delta=f"+{formatar_numero_pt(reducao_desp_un, 0)} salvos (-{formatar_numero_pt(reducao_desp_pct, 1)}% vs. {formatar_numero_pt(base['total_desperdicadas'], 0)})",
                delta_color="normal",
            )
            k3.metric(
                "Custo de Perdas Evitado",
                f"{formatar_numero_pt(poupanca_custo, 2)}€",
                delta=f"-{formatar_numero_pt(poupanca_custo, 2)}€ de custo ({formatar_numero_pt(base['custo_desperdicio'], 2)}€ → {formatar_numero_pt(res['custo_desperdicio'], 2)}€)",
                delta_color="inverse",
            )
            k4.metric(
                "Variação de Receita (vs. Tradicional)",
                _formatar_delta_pt(dif_receita, "€", 2),
                delta=_formatar_delta_pt(dif_receita, "€ vs. Tradicional", 2),
                delta_color="normal",
            )

            df_comp = pd.DataFrame([
                {
                    "Indicador": "Taxa de Salvamento (TS)",
                    "Retalho Tradicional (Fixo 30%/50%)": f"{formatar_numero_pt(base['ts_pct'], 1)}%",
                    "Desperdíci0% (Multi-Agente + CSP)": f"{formatar_numero_pt(res['ts_pct'], 1)}%",
                    "Diferença Real": _formatar_delta_pt(ganho_ts, " p.p.", 1),
                },
                {
                    "Indicador": "Taxa de Desperdício Global",
                    "Retalho Tradicional (Fixo 30%/50%)": f"{formatar_numero_pt(base['taxa_desperdicio_pct'], 1)}%",
                    "Desperdíci0% (Multi-Agente + CSP)": f"{formatar_numero_pt(res['taxa_desperdicio_pct'], 1)}%",
                    "Diferença Real": _formatar_delta_pt(res["taxa_desperdicio_pct"] - base["taxa_desperdicio_pct"], " p.p.", 1),
                },
                {
                    "Indicador": "Alimentos Desperdiçados (Expirados)",
                    "Retalho Tradicional (Fixo 30%/50%)": f"{formatar_numero_pt(base['total_desperdicadas'], 0)} un/kg",
                    "Desperdíci0% (Multi-Agente + CSP)": f"{formatar_numero_pt(res['total_desperdicadas'], 0)} un/kg",
                    "Diferença Real": f"{_formatar_delta_pt(-reducao_desp_un, ' un/kg', 0)} (-{formatar_numero_pt(reducao_desp_pct, 1)}%)",
                },
                {
                    "Indicador": "Encaminhado (Doação / Cozinha / Ração)",
                    "Retalho Tradicional (Fixo 30%/50%)": "0 un/kg",
                    "Desperdíci0% (Multi-Agente + CSP)": f"{formatar_numero_pt(res['total_doadas_cozinha'], 0)} un/kg",
                    "Diferença Real": _formatar_delta_pt(res["total_doadas_cozinha"], " un/kg", 0),
                },
                {
                    "Indicador": "Custo Direto de Desperdício (Aquisição + Descarte)",
                    "Retalho Tradicional (Fixo 30%/50%)": f"{formatar_numero_pt(base['custo_desperdicio'], 2)}€",
                    "Desperdíci0% (Multi-Agente + CSP)": f"{formatar_numero_pt(res['custo_desperdicio'], 2)}€",
                    "Diferença Real": _formatar_delta_pt(-poupanca_custo, "€", 2),
                },
                {
                    "Indicador": "Receita Total de Vendas",
                    "Retalho Tradicional (Fixo 30%/50%)": f"{formatar_numero_pt(base['receita_total'], 2)}€",
                    "Desperdíci0% (Multi-Agente + CSP)": f"{formatar_numero_pt(res['receita_total'], 2)}€",
                    "Diferença Real": _formatar_delta_pt(dif_receita, "€", 2),
                },
            ])
            st.dataframe(df_comp, hide_index=True, width="stretch")

        # 3. Gráfico comparativo por categoria (duas barras lado a lado)
        desp_nosso = res.get("desperdicio_por_categoria") or {}
        desp_trad = (res.get("comparacao_baseline") or {}).get("desperdicio_por_categoria") or {}
        todas_cats = sorted(set(desp_nosso.keys()) | set(desp_trad.keys()))
        if todas_cats:
            st.markdown(
                "**Desperdício acumulado por categoria — Tradicional vs. Desperdíci0% (unidades/kg expirados):**")
            ordem_cats = sorted(
                todas_cats,
                key=lambda c: max(float(desp_trad.get(c, 0.0)), float(desp_nosso.get(c, 0.0))),
                reverse=True,
            )
            dados_grafico = []
            for cat in ordem_cats:
                dados_grafico.append({
                    "Categoria": cat,
                    "Modelo": "Retalho Tradicional (30%/50%)",
                    "Desperdício": float(desp_trad.get(cat, 0.0)),
                })
                dados_grafico.append({
                    "Categoria": cat,
                    "Modelo": "Desperdíci0% (Multi-Agente + CSP)",
                    "Desperdício": float(desp_nosso.get(cat, 0.0)),
                })

            df_graf = pd.DataFrame(dados_grafico)
            grafico = (
                alt.Chart(df_graf)
                .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X(
                        "Categoria:N",
                        sort=ordem_cats,
                        axis=alt.Axis(labelAngle=-25, labelLimit=120, title=None),
                    ),
                    xOffset=alt.XOffset("Modelo:N"),
                    y=alt.Y("Desperdício:Q", axis=alt.Axis(title="Unidades / Kg expirados")),
                    color=alt.Color(
                        "Modelo:N",
                        scale=alt.Scale(
                            domain=["Retalho Tradicional (30%/50%)", "Desperdíci0% (Multi-Agente + CSP)"],
                            range=["#64748b", "#0ea5e9"],
                        ),
                        legend=alt.Legend(title="Modelo de Gestão", orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("Categoria:N", title="Categoria"),
                        alt.Tooltip("Modelo:N", title="Modelo"),
                        alt.Tooltip("Desperdício:Q", title="Expirado (un/kg)", format=".1f"),
                    ],
                )
                .properties(height=340)
            )
            st.altair_chart(grafico, use_container_width=True)

def renderizar_simulador_multidia_sidebar() -> None:
    with st.sidebar.expander("⏩ Simulação Acelerada Multi-Dia", expanded=False):
        n_dias = st.selectbox(
            "Horizonte (dias):",
            [2, 5, 7, 10],
            index=1,
            key="multidia_n_dias",
        )
        misturar_pert = st.checkbox(
            "Injetar perturbações e clima variados",
            value=True,
            key="multidia_pert",
        )
        correr_btn = st.button("🚀 Correr Simulação Multi-Dia", type="primary", width="stretch")

        if correr_btn:
            dias_escolhidos = int(n_dias)
            with st.spinner(f"A simular {dias_escolhidos} dias..."):
                modo_meteo = st.session_state.get("modo_meteo_ativo", "Automático (Tempo Real - Coimbra)")
                st.session_state["resultado_multidia"] = simular_horizonte_temporal(
                    dias_simulacao=dias_escolhidos,
                    modo_meteo=modo_meteo,
                    combinar_perturbacoes_aleatorias=misturar_pert,
                )

        if st.session_state.get("resultado_multidia"):
            if st.button("🗑️ Limpar Resultado Multi-Dia", width="stretch"):
                st.session_state.pop("resultado_multidia", None)
                st.rerun()