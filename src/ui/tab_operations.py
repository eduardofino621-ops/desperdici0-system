import pandas as pd
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder, JsCode
import streamlit as st

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

        for idx_h, snap in enumerate(historico[1:], start=1):
            st.markdown("<hr style='margin:14px 0;border-color:#2c2c2c;'>", unsafe_allow_html=True)
            st.markdown(
                f"⚡ **Perturbação #{idx_h}:** \"{snap['cenario']}\" às **{snap['hora']}** do dia **{snap['data_str']}**"
            )
            renderizar_cartoes_kpi(snap["kpis"], kpis_base=snap_inicial["kpis"])

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