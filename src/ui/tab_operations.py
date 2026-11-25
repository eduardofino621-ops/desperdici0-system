import pandas as pd
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder, JsCode
import streamlit as st

from src.rag.retriever import RecuperadorRAG
from src.simulation.orchestrator import formatar_eur, simular_horizonte_temporal, formatar_numero_pt
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

        perturbs = [s for s in historico[1:] if s["cenario"] != "Nenhuma (Operação Normal)"]
        if perturbs:
            k_base = snap_inicial["kpis"]
            linhas_hist = []
            for idx_h, snap in enumerate(perturbs, start=1):
                k = snap["kpis"]
                diff_lotes = k["lotes_desc_val"] - k_base["lotes_desc_val"]
                diff_csp = k["ajustes_csp"] - k_base["ajustes_csp"]
                linhas_hist.append({
                    "#": f"#{idx_h}",
                    "Hora": snap["hora"],
                    "Perturbação Injetada": snap["cenario"],
                    "Lotes c/ Desc. Validade": f"{k['lotes_desc_val']} ({diff_lotes:+d})" if diff_lotes != 0 else f"{k['lotes_desc_val']} (=)",
                    "Ajustes CSP": f"{k['ajustes_csp']} ({diff_csp:+d})" if diff_csp != 0 else f"{k['ajustes_csp']} (=)",
                })

            st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
            with st.expander(f"⚡ Histórico de Perturbações na Sessão ({len(linhas_hist)})", expanded=True):
                st.dataframe(
                    pd.DataFrame(linhas_hist),
                    hide_index=True,
                    width="stretch",
                )

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

def renderizar_explorador_rag() -> None:
    with st.expander("📚 Base de Conhecimento & Motor RAG", expanded=False):
        rag = RecuperadorRAG()
        total_regras = sum(1 for d in rag.documentos if not d["id"].startswith("Histórico "))
        total_hist = len(rag.documentos) - total_regras

        c1, c2, c3 = st.columns(3)
        c1.metric("Regras de Negócio Indexadas", total_regras)
        c2.metric("Registos Históricos (SQLite)", total_hist)
        c3.metric("Total de Documentos Vetorizados", len(rag.documentos))

        col_origem, col_cat = st.columns(2)
        with col_origem:
            filtro_origem = st.selectbox(
                "Origem do Conhecimento:",
                ["Todas", "Regras de Negócio Indexadas", "Registos Históricos (SQLite)"],
                key="rag_filtro_origem",
            )
        with col_cat:
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

        st.caption(f"A apresentar **{len(docs_filtrados)}** de **{len(rag.documentos)}** documentos indexados.")
        if docs_filtrados:
            for d in docs_filtrados:
                badge_origem = "🗄️ SQLite" if d["id"].startswith("Histórico ") else "📘 Regra Fixa"
                cat_label = d.get("categoria", "geral").capitalize()
                st.markdown(f"- {badge_origem} | **`{d['id']}`** *({cat_label})*: {d['texto']}")
        else:
            st.info("Nenhum documento encontrado para a combinação de filtros selecionada.")

def renderizar_simulador_multidia() -> None:
    with st.expander("⏩ Simulação Acelerada Multi-Dia (Teste de Validades & Desperdício)", expanded=False):
        c_dias, c_pert, c_btn = st.columns([1, 2, 1])
        with c_dias:
            n_dias = st.selectbox("Horizonte (dias):", [5, 7, 10, 14], index=1, key="multidia_n_dias")
        with c_pert:
            misturar_pert = st.checkbox(
                "Injetar combinações variadas de perturbações e clima ao longo dos dias",
                value=True,
                key="multidia_pert",
            )
        with c_btn:
            st.markdown("<div style='margin-top: 26px;'></div>", unsafe_allow_html=True)
            correr_btn = st.button("🚀 Correr Simulação Multi-Dia", type="primary", width="stretch")

        if correr_btn:
            with st.spinner(f"A simular {n_dias} dias de operação, vendas FEFO e expirações..."):
                modo_meteo = st.session_state.get("modo_meteo_ativo", "Automático (Tempo Real - Coimbra)")
                st.session_state["resultado_multidia"] = simular_horizonte_temporal(
                    dias_simulacao=n_dias,
                    modo_meteo=modo_meteo,
                    combinar_perturbacoes_aleatorias=misturar_pert,
                )

        res = st.session_state.get("resultado_multidia")
        if res:
            # 1. Passo a passo cronológico da simulação antes das métricas
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

            # 2. Métricas consolidadas incluindo Taxa de Salvamento (TS)
            st.markdown("### 📊 Resultados Consolidados do Horizonte")
            ts_val = res.get("ts_pct", 0.0)
            atingiu_meta = ts_val > 90.0
            estado_meta = "✅ Meta atingida (> 90%)" if atingiu_meta else "⚠️ Abaixo da meta (≤ 90%)"

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric(
                "Taxa de Salvamento (TS)",
                f"{formatar_numero_pt(ts_val, 1)}%",
                estado_meta,
                delta_color="normal" if atingiu_meta else "inverse",
            )
            m2.metric(
                "Unidades / Kg Vendidos",
                formatar_numero_pt(res["total_vendidas"], 0),
                f"Receita: {formatar_numero_pt(res['receita_total'], 2)}€",
                delta_color="off",
            )
            m3.metric(
                "Doação / Cozinha Interna",
                formatar_numero_pt(res["total_doadas_cozinha"], 0),
                f"QD: {formatar_numero_pt(res.get('qd_kg', 0.0), 1)} kg | QR: {formatar_numero_pt(res.get('qr_kg', 0.0), 1)} kg",
                delta_color="off",
            )
            m4.metric(
                "Desperdiçado (Expirado)",
                formatar_numero_pt(res["total_desperdicadas"], 0),
                f"Custo: {formatar_numero_pt(res['custo_desperdicio'], 2)}€",
                delta_color="off",
            )
            m5.metric(
                "Taxa de Desperdício",
                f"{formatar_numero_pt(res['taxa_desperdicio_pct'], 1)}%",
                f"Em {res['dias_simulados']} dias",
                delta_color="off",
            )

            st.caption(
                f"📐 **Decomposição TS (em massa):** "
                f"QVD = `{formatar_numero_pt(res.get('qvd_kg', 0.0), 1)} kg` · "
                f"QD = `{formatar_numero_pt(res.get('qd_kg', 0.0), 1)} kg` · "
                f"QR = `{formatar_numero_pt(res.get('qr_kg', 0.0), 1)} kg` · "
                f"QTAR = `{formatar_numero_pt(res.get('qtar_kg', 0.0), 1)} kg`"
            )

            # 3. Tabela diária com números formatados no padrão PT
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

            # 4. Gráfico de desperdício por categoria
            if res["desperdicio_por_categoria"]:
                st.markdown("**Desperdício acumulado por categoria (unidades/kg expirados):**")
                df_cat_desp = pd.DataFrame(
                    [
                        {"Categoria": k, "Desperdiçado": v}
                        for k, v in sorted(res["desperdicio_por_categoria"].items(), key=lambda x: -x[1])
                    ]
                )
                st.bar_chart(df_cat_desp.set_index("Categoria"))