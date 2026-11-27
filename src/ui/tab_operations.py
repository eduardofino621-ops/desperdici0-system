import html
import re

import altair as alt
import pandas as pd
from st_aggrid import AgGrid, ColumnsAutoSizeMode, GridOptionsBuilder, JsCode
import streamlit as st

from src.rag.retriever import RecuperadorRAG
from src.simulation.orchestrator import (
    DESTINOS_NAO_DESPERDICIO,
    _formatar_delta_pt,
    formatar_numero_pt,
    simular_horizonte_temporal,
)
from src.ui.components import (
    exibir_tabela_alinhada,
    mostrar_popup_agentes,
    obter_dado_pagina,
    renderizar_analise_decisoes,
    renderizar_cartoes_kpi,
)
from src.ui.styles import CATEGORIAS_UI

COLUNA_DECISAO_AGENTES = "Decisão dos agentes"
COLUNA_LEGADA_CSP = "Consultar Validação CSP"

COLUNAS_NUMERICAS_AGGRID = {
    "Stock",
    "Dias",
    "PVP",
    "PUM",
    "Campanha",
    "Desc. Validade",
    "Preço Ativo",
}

_REGEX_VALOR_NUMERICO = re.compile(
    r"^[+\-−]?\s*\d[\d\s.,]*\s*(€|%|kg|g|un|l|ml|d)?$",
    re.IGNORECASE,
)


def _eh_coluna_numerica_aggrid(nome_coluna: str, serie: pd.Series) -> bool:
    if nome_coluna in COLUNAS_NUMERICAS_AGGRID:
        return True
    if pd.api.types.is_numeric_dtype(serie):
        return True
    valores = [
        str(v).strip()
        for v in serie.dropna()
        if str(v).strip() not in ("", "—", "-", "N/D")
    ]
    if not valores:
        return False
    correspondencias = sum(1 for v in valores if _REGEX_VALOR_NUMERICO.match(v))
    return (correspondencias / len(valores)) >= 0.5


def _alternar_cat_tab1(cat_key: str) -> None:
    atual = st.session_state.get("filtro_cat_tab1")
    st.session_state.filtro_cat_tab1 = None if atual == cat_key else cat_key


def _chave_cenario_atual() -> tuple:
    pert_lista = list(st.session_state.get("perturbacoes_ativas", []) or [])
    pert = tuple(sorted(pert_lista))
    fecho = "A menos de 2 horas de fechar a loja." in pert_lista
    meteo = str(
        st.session_state.get("modo_meteo_ativo")
        or st.session_state.get("modo_meteo")
        or "Automático (Tempo Real - Coimbra)"
    )
    return (pert, fecho, meteo)


def _normalizar_linhas_operacoes(resultados: list | None) -> list[dict]:
    linhas = []
    for r in resultados or []:
        item = dict(r)
        if COLUNA_DECISAO_AGENTES not in item:
            item[COLUNA_DECISAO_AGENTES] = item.get(COLUNA_LEGADA_CSP, "— (Validade > 5d)")
        linhas.append(item)
    return linhas


def _assinatura_resultados(resultados: list | None) -> tuple:
    if not resultados:
        return ()
    try:
        return tuple(
            (
                r.get("Lote"),
                r.get("Destino Operacional"),
                r.get(COLUNA_DECISAO_AGENTES),
                r.get("Dias"),
                r.get("Validade"),
            )
            for r in resultados
        )
    except Exception:
        return (len(resultados),)


def limpar_estado_cenario_atual() -> None:
    st.session_state["resultados_simulacao"] = []
    st.session_state["logs_por_lote"] = {}
    st.session_state["historico_sessao"] = []
    st.session_state["pagina_decisoes"] = 0
    st.session_state["sacos_surpresa_lista"] = []
    st.session_state["lotes_simulados"] = []
    st.session_state["resultado_acelerada"] = None
    st.session_state["resultado_multidia"] = None
    st.session_state["_ultimo_token_clique_agentes"] = None
    st.session_state["aggrid_key_v"] = st.session_state.get("aggrid_key_v", 0) + 1


def guardar_snapshot_cenario(chave: tuple | None = None) -> None:
    st.session_state.setdefault("snapshots_perturbacao", {})
    chave_alvo = chave if chave is not None else _chave_cenario_atual()
    st.session_state["snapshots_perturbacao"][chave_alvo] = {
        "resultados_simulacao": _normalizar_linhas_operacoes(
            st.session_state.get("resultados_simulacao")
        ),
        "logs_por_lote": dict(st.session_state.get("logs_por_lote") or {}),
        "historico_sessao": list(st.session_state.get("historico_sessao") or []),
        "sacos_surpresa_lista": list(st.session_state.get("sacos_surpresa_lista") or []),
        "lotes_simulados": list(st.session_state.get("lotes_simulados") or []),
        "resultado_acelerada": st.session_state.get("resultado_acelerada"),
        "resultado_multidia": st.session_state.get("resultado_multidia"),
    }


def restaurar_snapshot_cenario(chave: tuple | None = None) -> bool:
    snapshots = st.session_state.get("snapshots_perturbacao") or {}
    chave_alvo = chave if chave is not None else _chave_cenario_atual()
    snap = snapshots.get(chave_alvo)
    if not snap:
        return False

    st.session_state["resultados_simulacao"] = _normalizar_linhas_operacoes(
        snap.get("resultados_simulacao")
    )
    st.session_state["logs_por_lote"] = dict(snap.get("logs_por_lote") or {})
    historico = list(snap.get("historico_sessao") or [])
    st.session_state["historico_sessao"] = historico
    st.session_state["pagina_decisoes"] = max(0, len(historico) - 1)
    st.session_state["sacos_surpresa_lista"] = list(snap.get("sacos_surpresa_lista") or [])
    st.session_state["lotes_simulados"] = list(snap.get("lotes_simulados") or [])
    st.session_state["resultado_acelerada"] = snap.get("resultado_acelerada")
    st.session_state["resultado_multidia"] = snap.get("resultado_multidia")
    st.session_state["_ultimo_token_clique_agentes"] = None
    st.session_state["aggrid_key_v"] = st.session_state.get("aggrid_key_v", 0) + 1
    return True


def _sincronizar_estado_por_perturbacao() -> None:
    chave_atual = _chave_cenario_atual()
    chave_anterior = st.session_state.get("ultima_chave_cenario")
    ass_resultados = _assinatura_resultados(st.session_state.get("resultados_simulacao"))
    ass_anterior = st.session_state.get("_ass_resultados_ultimo_sync", ())

    tem_estado = any(
        st.session_state.get(k)
        for k in (
            "resultados_simulacao",
            "historico_sessao",
            "logs_por_lote",
            "resultado_acelerada",
            "resultado_multidia",
        )
    )
    resultados_novos = bool(ass_resultados) and ass_resultados != ass_anterior

    if chave_anterior is not None and chave_atual != chave_anterior and not resultados_novos:
        if tem_estado:
            guardar_snapshot_cenario(chave_anterior)
        if not restaurar_snapshot_cenario(chave_atual):
            limpar_estado_cenario_atual()
    elif tem_estado:
        guardar_snapshot_cenario(chave_atual)

    st.session_state["ultima_chave_cenario"] = chave_atual
    st.session_state["_ass_resultados_ultimo_sync"] = _assinatura_resultados(
        st.session_state.get("resultados_simulacao")
    )


def _extrair_clique_lote(grid_resp: dict) -> tuple[str, int] | None:
    sel = grid_resp.get("selected_rows")
    if isinstance(sel, pd.DataFrame) and not sel.empty and "Lote" in sel.columns:
        row = sel.iloc[0]
        lote = str(row["Lote"] or "")
        seq = int(row["_click_seq"]) if "_click_seq" in sel.columns and pd.notna(row["_click_seq"]) else 0
        return (lote, seq) if lote else None
    if isinstance(sel, list) and len(sel) > 0 and isinstance(sel[0], dict):
        lote = str(sel[0].get("Lote") or "")
        seq = int(sel[0].get("_click_seq") or 0)
        return (lote, seq) if lote else None
    return None


@st.fragment
def _renderizar_tabela_operacoes() -> None:
    st.session_state.setdefault("filtro_validade_tab1", "Todos os Lotes")

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
            key="filtro_validade_tab1",
        )

    st.session_state.setdefault("filtro_cat_tab1", None)

    cats_visiveis = [(cat_key, cat_label) for cat_key, cat_label in CATEGORIAS_UI]

    for i in range(0, len(cats_visiveis), 4):
        linha_cats = cats_visiveis[i : i + 4]
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

    resultados_atuais = _normalizar_linhas_operacoes(
        obter_dado_pagina("resultados_simulacao")
    )
    ass_atual = _assinatura_resultados(resultados_atuais)
    if ass_atual != st.session_state.get("ultima_ass_tabela_operacoes"):
        st.session_state["ultima_ass_tabela_operacoes"] = ass_atual
        st.session_state["_ultimo_token_clique_agentes"] = None
        st.session_state["aggrid_key_v"] = st.session_state.get("aggrid_key_v", 0) + 1

    df_res = pd.DataFrame(resultados_atuais)
    if df_res.empty:
        st.info("ℹ️ Nenhum lote disponível para a simulação atual.")
        return

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
        sacos_lista = obter_dado_pagina("sacos_surpresa_lista") or []
        lotes_nos_sacos = {
            lid
            for saco in sacos_lista
            for lid in (saco.get("lotes_consumo") or {}).keys()
        }
        if lotes_nos_sacos:
            df_res = df_res[
                df_res["Destino Operacional"].str.contains("Sacos Surpresa", na=False)
                & df_res["Lote"].isin(lotes_nos_sacos)
            ]
        else:
            df_res = df_res[df_res["Destino Operacional"].str.contains("Sacos Surpresa", na=False)]
    elif filtro_validade_tab == "Superior a 5 dias":
        df_res = df_res[df_res["Dias"] > 5]

    if df_res.empty:
        st.info("ℹ️ Nenhum lote encontrado para os filtros selecionados.")
        return

    df_grid = df_res.copy()
    df_grid["Validade"] = df_grid["Validade"].astype(str)
    df_grid["_click_seq"] = 0

    fmt_data_pt = JsCode("""
        function(params) {
            if (!params.value) return '';
            var p = String(params.value).split('-');
            return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : params.value;
        }
    """)
    fmt_dias = JsCode("function(params) { return params.value != null ? params.value + 'd' : ''; }")
    selecionar_linha_agentes = JsCode("""
        function(params) {
            var ativo = params.data && Number(params.data.Dias) <= 5 && params.value && !String(params.value).startsWith('—');
            if (ativo) {
                params.data._click_seq = (params.data._click_seq || 0) + 1;
                params.api.deselectAll();
                params.node.setSelected(true, true);
            }
        }
    """)
    estilo_celula_agentes = JsCode("""
        function(params) {
            var ativo = params.data && Number(params.data.Dias) <= 5 && params.value && !String(params.value).startsWith('—');
            if (ativo) {
                return {
                    color: '#0ea5e9',
                    textDecoration: 'underline',
                    cursor: 'pointer',
                    fontWeight: '600'
                };
            }
            return {
                color: 'var(--text-color)',
                opacity: '0.65',
                cursor: 'default'
            };
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

    for col_nome in df_grid.columns:
        if col_nome in (COLUNA_DECISAO_AGENTES, "_click_seq"):
            continue
        max_chars = int(df_grid[col_nome].astype(str).str.len().max())
        eh_numerica = _eh_coluna_numerica_aggrid(col_nome, df_grid[col_nome])
        kwargs_numericos = (
            {
                "type": ["numericColumn", "rightAligned"],
                "cellClass": "ag-right-aligned-cell",
                "cellStyle": {
                    "textAlign": "right",
                    "justifyContent": "flex-end",
                    "fontVariantNumeric": "tabular-nums",
                },
                "headerClass": "ag-right-aligned-header",
            }
            if eh_numerica
            else {}
        )
        if col_nome == "Validade":
            gb.configure_column(col_nome, width=110, minWidth=110, valueFormatter=fmt_data_pt)
        elif col_nome == "Dias":
            gb.configure_column(col_nome, width=75, minWidth=75, valueFormatter=fmt_dias, **kwargs_numericos)
        else:
            larg = int(max(85, min(360, max_chars * 8.2 + 26)))
            gb.configure_column(col_nome, width=larg, minWidth=larg, **kwargs_numericos)

    gb.configure_column("_click_seq", hide=True)
    gb.configure_column(
        COLUNA_DECISAO_AGENTES,
        width=165,
        minWidth=165,
        pinned="right",
        cellStyle=estilo_celula_agentes,
        onCellClicked=selecionar_linha_agentes,
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
        ".ag-right-aligned-header .ag-header-cell-label": {
            "justify-content": "flex-end !important",
            "text-align": "right !important",
        },
        ".ag-right-aligned-cell": {
            "text-align": "right !important",
            "justify-content": "flex-end !important",
            "font-variant-numeric": "tabular-nums !important",
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
    id_cenario = abs(hash(_chave_cenario_atual())) % 100000
    pag_atual = st.session_state.get("pagina_decisoes", 0)
    grid_resp = AgGrid(
        df_grid,
        key=f"tabela_operacoes_{id_cenario}_{pag_atual}_{st.session_state['aggrid_key_v']}",
        gridOptions=gb.build(),
        update_on=["selectionChanged"],
        columns_auto_size_mode=ColumnsAutoSizeMode.NO_AUTOSIZE,
        allow_unsafe_jscode=True,
        custom_css=custom_css,
        theme="streamlit",
        height=540,
        fit_columns_on_grid_load=False,
    )

    clique_lote = _extrair_clique_lote(grid_resp)
    logs_disponiveis = obter_dado_pagina("logs_por_lote") or {}
    if clique_lote and clique_lote[1] > 0:
        lote_clicado, _ = clique_lote
        if (
            lote_clicado in logs_disponiveis
            and clique_lote != st.session_state.get("_ultimo_token_clique_agentes")
        ):
            st.session_state["_ultimo_token_clique_agentes"] = clique_lote
            mostrar_popup_agentes(lote_clicado)


def renderizar_aba_operacoes() -> None:
    _sincronizar_estado_por_perturbacao()

    historico = st.session_state.get("historico_sessao", [])
    if historico:
        renderizar_cartoes_kpi(historico[0]["kpis"])

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander(
            "📊 Quantificação das Decisões dos Agentes (Lotes com Validade ≤ 5 dias) & Gráficos por Categoria",
            expanded=True,
        ):
            renderizar_analise_decisoes(historico)

    st.markdown("<br>", unsafe_allow_html=True)
    _renderizar_tabela_operacoes()


_NOMES_CAT_RAG = {
    "geral": "Geral (Todas as Categorias)",
    "laticinios": "Laticínios",
}


def _rotulo_categoria_rag(cat: str | None) -> str:
    chave = (cat or "geral").strip().lower()
    return _NOMES_CAT_RAG.get(chave, chave.capitalize())


def _obter_rag_em_cache() -> RecuperadorRAG:
    rag = st.session_state.get("_rag_retriever_cache")
    if rag is None:
        rag = RecuperadorRAG()
        st.session_state["_rag_retriever_cache"] = rag
    return rag


def _renderizar_secao_caderno_rag(titulo: str, classe_banner: str, docs: list[dict]) -> None:
    if not docs:
        return

    st.markdown(
        f'<div class="rag-origem-banner {classe_banner}">'
        f"<span>{html.escape(titulo)}</span>"
        f'<span class="rag-origem-count">{len(docs)}'
        f' {"documento" if len(docs) == 1 else "documentos"}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    por_categoria: dict[str, list[dict]] = {}
    for d in docs:
        cat_key = (d.get("categoria") or "geral").strip().lower()
        por_categoria.setdefault(cat_key, []).append(d)

    cats_ordenadas = sorted(por_categoria.keys(), key=lambda c: (0 if c == "geral" else 1, c))

    blocos_html = []
    for cat_key in cats_ordenadas:
        cat_label = _rotulo_categoria_rag(cat_key)
        blocos_html.append(f'<div class="rag-cat-header">{html.escape(cat_label)}</div>')
        for doc in por_categoria[cat_key]:
            blocos_html.append(
                f'<div class="rag-card">'
                f'<div class="rag-card-title">{html.escape(doc["id"])}</div>'
                f'<div class="rag-card-body">{html.escape(doc["texto"])}</div>'
                f"</div>"
            )

    st.markdown(f'<div class="rag-notebook">{"".join(blocos_html)}</div>', unsafe_allow_html=True)


@st.dialog("📖 Base de Conhecimento & Motor RAG", width="large")
def _mostrar_popup_rag() -> None:
    rag = _obter_rag_em_cache()
    docs_ativos = list(rag.documentos)
    total_regras = sum(1 for d in docs_ativos if not d["id"].startswith("Histórico "))
    total_hist = len(docs_ativos) - total_regras

    f1, f2, f3 = st.columns([1.4, 1.1, 1.3])
    with f1:
        filtro_origem = st.selectbox(
            "Origem do Conhecimento:",
            [
                f"Todas ({len(docs_ativos)})",
                f"📘 Regras de Negócio Indexadas ({total_regras})",
                f"🗄️ Registos Históricos (SQLite) ({total_hist})",
            ],
            key="rag_popup_origem",
        )
    with f2:
        cats_unicas = sorted(
            {(d.get("categoria") or "geral").strip().lower() for d in docs_ativos},
            key=lambda c: (0 if c == "geral" else 1, c),
        )
        mapa_cat_label = {"Todas": None, **{_rotulo_categoria_rag(c): c for c in cats_unicas}}
        filtro_cat_label = st.selectbox(
            "Categoria:",
            list(mapa_cat_label.keys()),
            key="rag_popup_cat",
        )
        filtro_cat = mapa_cat_label[filtro_cat_label]
    with f3:
        pesquisa_rag = st.text_input(
            "🔎 Pesquisar termo:",
            placeholder="Ex: chuva, padaria, salmão...",
            key="rag_popup_search",
        ).strip().lower()

    regras_filtradas = []
    hist_filtrados = []

    for d in docs_ativos:
        eh_sql = d["id"].startswith("Histórico ")
        if filtro_origem.startswith("📘") and eh_sql:
            continue
        if filtro_origem.startswith("🗄️") and not eh_sql:
            continue
        if filtro_cat is not None and (d.get("categoria") or "geral").strip().lower() != filtro_cat:
            continue
        if pesquisa_rag and (
            pesquisa_rag not in d["id"].lower() and pesquisa_rag not in d["texto"].lower()
        ):
            continue

        if eh_sql:
            hist_filtrados.append(d)
        else:
            regras_filtradas.append(d)

    total_visivel = len(regras_filtradas) + len(hist_filtrados)
    st.caption(
        f"A apresentar **{total_visivel}** de **{len(docs_ativos)}** documentos indexados no motor TF-IDF."
    )

    if total_visivel == 0:
        st.info("Nenhum documento encontrado para os filtros selecionados.")
        return

    _renderizar_secao_caderno_rag("📘 Regras de Negócio Indexadas", "rag-origem-regra", regras_filtradas)
    _renderizar_secao_caderno_rag("🗄️ Registos Históricos (SQLite)", "rag-origem-sql", hist_filtrados)


def renderizar_explorador_rag() -> None:
    if st.sidebar.button("📖 Base de Conhecimento & Motor RAG", key="btn_abrir_rag", width="stretch"):
        st.session_state.pop("_rag_retriever_cache", None)
        _mostrar_popup_rag()


def renderizar_resultados_acelerada() -> None:
    _sincronizar_estado_por_perturbacao()

    res = st.session_state.get("resultado_acelerada") or st.session_state.get("resultado_multidia")
    if not res:
        return

    enc_nosso = res.get(
        "total_encaminhadas_total",
        res.get("total_doadas_cozinha", 0.0) + res.get("total_racao_valorizacao", 0.0),
    )

    with st.expander(
        f"⏩ Resultados da Simulação Acelerada ({res['dias_simulados']} dias)",
        expanded=True,
    ):
        st.markdown("### 📊 Desempenho Global (Desperdíci0%)")
        ts_val = res.get("ts_pct", 0.0)
        atingiu_meta = ts_val > 90.0

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric(label="Taxa de Salvamento (TS)", value=f"{formatar_numero_pt(ts_val, 1)}%")
            if atingiu_meta:
                st.markdown(
                    '<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;'
                    'border-radius:999px;font-size:12px;font-weight:700;'
                    'background:rgba(16,185,129,0.16);color:#10b981;border:1px solid rgba(16,185,129,0.45);">'
                    '✅ Meta atingida (&gt; 90%)</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;'
                    'border-radius:999px;font-size:12px;font-weight:700;'
                    'background:rgba(239,68,68,0.16);color:#ef4444;border:1px solid rgba(239,68,68,0.45);">'
                    '⚠️ Abaixo da meta (≤ 90%)</span>',
                    unsafe_allow_html=True,
                )
        with m2:
            st.metric(
                label="Total Vendido",
                value=f"{formatar_numero_pt(res['total_vendidas'], 0)} kg",
            )
            st.caption(f"Receita: {formatar_numero_pt(res['receita_total'], 2)}€")
        with m3:
            st.metric(
                label="Doação / Reaproveit.",
                value=f"{formatar_numero_pt(enc_nosso, 0)} kg",
            )
        with m4:
            st.metric(
                label="Desperdício (Lixo)",
                value=f"{formatar_numero_pt(res['total_desperdicadas'], 0)} kg",
            )
            st.caption(f"Perda: {formatar_numero_pt(res['custo_desperdicio'], 2)}€")
        with m5:
            st.metric(
                label="Taxa de Desperdício",
                value=f"{formatar_numero_pt(res['taxa_desperdicio_pct'], 1)}%",
            )

        qvd_val = float(res.get("qvd_kg", 0.0))
        qd_val = float(res.get("qd_kg", 0.0))
        qci_val = float(res.get("qci_kg", 0.0))
        qtar_val = float(res.get("qtar_kg", 0.0))

        denom_qtar = qtar_val if qtar_val > 0 else 1.0
        qvd_pct = formatar_numero_pt((qvd_val / denom_qtar) * 100.0, 1)
        qd_pct = formatar_numero_pt((qd_val / denom_qtar) * 100.0, 1)
        qci_pct = formatar_numero_pt((qci_val / denom_qtar) * 100.0, 1)

        qvd_str = f"{formatar_numero_pt(qvd_val, 1)} kg ({qvd_pct}%)"
        qd_str = f"{formatar_numero_pt(qd_val, 1)} kg ({qd_pct}%)"
        qci_str = f"{formatar_numero_pt(qci_val, 1)} kg ({qci_pct}%)"
        qtar_str = f"{formatar_numero_pt(qtar_val, 1)} kg"

        st.markdown(
            f"""
            <div class="ts-info-wrapper" tabindex="0">
                <div class="ts-info-box">
                    <span>
                        <strong>QVD:</strong> {qvd_str} &nbsp;·&nbsp;
                        <strong>QD:</strong> {qd_str} &nbsp;·&nbsp;
                        <strong>QCI:</strong> {qci_str} &nbsp;·&nbsp;
                        <strong>QTAR:</strong> {qtar_str}
                    </span>
                    <span class="ts-info-hint">ℹ️ Passe o cursor para ver a fórmula</span>
                </div>
                <div class="ts-tooltip-card">
                    <div class="ts-formula-box">
                        <span>TS</span>
                        <span>=</span>
                        <span class="ts-frac">
                            <span class="ts-frac-num">QVD + QD + QCI</span>
                            <span class="ts-frac-den">QTAR</span>
                        </span>
                        <span>&times; 100</span>
                    </div>
                    <ul class="ts-var-list">
                        <li><strong>TS (Taxa de Salvamento):</strong> Percentagem de stock em risco de expirar que foi aproveitado e evitado de ir para o lixo.</li>
                        <li><strong>QVD (Quantidade Vendida com Desconto):</strong> Massa (kg) escoada através de descontos dinâmicos de validade (ESL) e <em>Sacos Surpresa</em>.</li>
                        <li><strong>QD (Quantidade Doada):</strong> Massa (kg) encaminhada para doação externa (IPSS) e valorização/transformação em ração animal.</li>
                        <li><strong>QCI (Quantidade Cozinha Interna):</strong> Massa (kg) encaminhada para preparação/consumo na cozinha interna da loja.</li>
                        <li><strong>QTAR (Quantidade Total em Risco):</strong> Total de stock crítico que atingiu o fim de vida útil no horizonte simulado (QVD + QD + QCI + Desperdício).</li>
                    </ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        df_evo = pd.DataFrame(res["evolucao_diaria"]).copy()
        for col_num, casas in [
            ("Vendidas", 1),
            ("Doação / Cozinha", 1),
            ("Desperdício (Lixo)", 1),
            ("Receita (€)", 2),
        ]:
            if col_num in df_evo.columns:
                df_evo[col_num] = df_evo[col_num].apply(lambda v: formatar_numero_pt(float(v), casas))

        exibir_tabela_alinhada(
            df_evo,
            colunas_direita=["Vendidas", "Doação / Cozinha", "Desperdício (Lixo)", "Receita (€)"],
            hide_index=True,
            width="stretch",
        )

        base = res.get("comparacao_baseline")
        if base:
            st.divider()
            st.markdown("### ⚖️ Comparação Direta: Desperdíci0% vs. Lidl")
            n_prods = res.get("total_produtos") or len(st.session_state.get("catalogo_simulado") or [])
            n_lotes = res.get("total_lotes_iniciais") or len(st.session_state.get("lotes_simulados") or [])
            n_prods_sim = res.get("total_produtos_simulados")
            n_lotes_sim = res.get("total_lotes_simulados")
            if n_prods and n_lotes and n_prods_sim is not None and n_lotes_sim is not None:
                st.caption(
                    f"Catálogo base com {n_prods} produtos e {n_lotes} lotes iniciais "
                    f"(contabilizados na simulação: {n_prods_sim} produtos e {n_lotes_sim} lotes) "
                    "e mesmas perturbações diárias."
                )
            elif n_prods and n_lotes:
                st.caption(
                    f"Catálogo base com {n_prods} produtos, {n_lotes} lotes iniciais e mesmas perturbações diárias."
                )
            else:
                st.caption(
                    "Mesmo catálogo base, mesmos lotes iniciais e mesmas perturbações diárias."
                )

            ganho_ts = res["ts_pct"] - base["ts_pct"]
            reducao_desp_kg = base["total_desperdicadas"] - res["total_desperdicadas"]
            reducao_desp_pct = (reducao_desp_kg / max(1.0, base["total_desperdicadas"])) * 100
            poupanca_custo = base["custo_desperdicio"] - res["custo_desperdicio"]
            dif_receita = res["receita_total"] - base["receita_total"]
            lucro_lidl = base["receita_total"] - base["custo_desperdicio"]
            lucro_nosso = res["receita_total"] - res["custo_desperdicio"]
            ganho_lucro = dif_receita + poupanca_custo
            enc_lidl = base.get(
                "total_encaminhadas_total",
                base.get("total_doadas_cozinha", 0.0) + base.get("total_racao_valorizacao", 0.0),
            )
            dif_enc = enc_nosso - enc_lidl

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.metric(
                    label="Ganho Taxa de Salvamento (TS)",
                    value=_formatar_delta_pt(ganho_ts, " p.p.", 1),
                    delta_color="normal",
                )
            with c2:
                st.metric(
                    label="Desperdício Evitado",
                    value=_formatar_delta_pt(reducao_desp_kg, " kg", 0),
                    delta_color="inverse",
                )
            with c3:
                st.metric(
                    label="Custo de Perdas Evitado",
                    value=_formatar_delta_pt(poupanca_custo, "€", 2),
                    delta_color="inverse",
                )
            with c4:
                st.metric(
                    label="Variação de Receita",
                    value=_formatar_delta_pt(dif_receita, "€", 2),
                    delta_color="normal",
                )
            with c5:
                st.metric(
                    label="Ganho de Lucro Final",
                    value=_formatar_delta_pt(ganho_lucro, "€", 2),
                    delta_color="normal",
                )

            df_comp = pd.DataFrame([
                {
                    "Indicador": "Taxa de Salvamento (TS)",
                    "Lidl": f"{formatar_numero_pt(base['ts_pct'], 1)}%",
                    "Desperdíci0%": f"{formatar_numero_pt(res['ts_pct'], 1)}%",
                    "Diferença (Desperdíci0% vs. Lidl)": _formatar_delta_pt(ganho_ts, " p.p.", 1),
                },
                {
                    "Indicador": "Taxa de Desperdício Global",
                    "Lidl": f"{formatar_numero_pt(base['taxa_desperdicio_pct'], 1)}%",
                    "Desperdíci0%": f"{formatar_numero_pt(res['taxa_desperdicio_pct'], 1)}%",
                    "Diferença (Desperdíci0% vs. Lidl)": _formatar_delta_pt(
                        res["taxa_desperdicio_pct"] - base["taxa_desperdicio_pct"], " p.p.", 1
                    ),
                },
                {
                    "Indicador": "Alimentos Desperdiçados (Lixo)",
                    "Lidl": f"{formatar_numero_pt(base['total_desperdicadas'], 0)} kg",
                    "Desperdíci0%": f"{formatar_numero_pt(res['total_desperdicadas'], 0)} kg",
                    "Diferença (Desperdíci0% vs. Lidl)": (
                        f"{_formatar_delta_pt(-reducao_desp_kg, ' kg', 0)} "
                        f"({_formatar_delta_pt(-reducao_desp_pct, '%', 1)})"
                    ),
                },
                {
                    "Indicador": "Encaminhado (Doação / Cozinha / Ração)",
                    "Lidl": f"{formatar_numero_pt(enc_lidl, 0)} kg",
                    "Desperdíci0%": f"{formatar_numero_pt(enc_nosso, 0)} kg",
                    "Diferença (Desperdíci0% vs. Lidl)": _formatar_delta_pt(dif_enc, " kg", 0),
                },
                {
                    "Indicador": "Custo Direto de Desperdício (Aquisição + Descarte)",
                    "Lidl": f"{formatar_numero_pt(base['custo_desperdicio'], 2)}€",
                    "Desperdíci0%": f"{formatar_numero_pt(res['custo_desperdicio'], 2)}€",
                    "Diferença (Desperdíci0% vs. Lidl)": _formatar_delta_pt(-poupanca_custo, "€", 2),
                },
                {
                    "Indicador": "Receita Total de Vendas",
                    "Lidl": f"{formatar_numero_pt(base['receita_total'], 2)}€",
                    "Desperdíci0%": f"{formatar_numero_pt(res['receita_total'], 2)}€",
                    "Diferença (Desperdíci0% vs. Lidl)": _formatar_delta_pt(dif_receita, "€", 2),
                },
                {
                    "Indicador": "Lucro Final (Receita − Custo Desperdício)",
                    "Lidl": f"{formatar_numero_pt(lucro_lidl, 2)}€",
                    "Desperdíci0%": f"{formatar_numero_pt(lucro_nosso, 2)}€",
                    "Diferença (Desperdíci0% vs. Lidl)": _formatar_delta_pt(ganho_lucro, "€", 2),
                },
            ])
            exibir_tabela_alinhada(
                df_comp,
                colunas_direita=["Lidl", "Desperdíci0%", "Diferença (Desperdíci0% vs. Lidl)"],
                hide_index=True,
                width="stretch",
            )

            desp_nosso = res.get("desperdicio_por_categoria") or {}
            desp_trad = (res.get("comparacao_baseline") or {}).get("desperdicio_por_categoria") or {}
            salv_nosso = res.get("salvamento_por_categoria") or {}
            salv_lidl = (res.get("comparacao_baseline") or {}).get("salvamento_por_categoria") or {}

            todas_cats = sorted(
                set(desp_nosso.keys())
                | set(desp_trad.keys())
                | set(salv_nosso.keys())
                | set(salv_lidl.keys())
            )

            if todas_cats:
                st.divider()
                st.markdown("### 📈 Análise por Categoria — Lidl vs. Desperdíci0%")

                ordem_cats = sorted(
                    todas_cats,
                    key=lambda c: max(
                        float(desp_trad.get(c, 0.0)),
                        float(desp_nosso.get(c, 0.0)),
                        sum(float(v) for v in (salv_lidl.get(c) or {}).values()),
                        sum(float(v) for v in (salv_nosso.get(c) or {}).values()),
                    ),
                    reverse=True,
                )

                st.markdown("**1. Desperdício acumulado por categoria (kg expirados):**")
                dados_desp = []
                for cat in ordem_cats:
                    dados_desp.append({
                        "Categoria": cat,
                        "Modelo": "Lidl",
                        "Desperdício": float(desp_trad.get(cat, 0.0)),
                    })
                    dados_desp.append({
                        "Categoria": cat,
                        "Modelo": "Desperdíci0%",
                        "Desperdício": float(desp_nosso.get(cat, 0.0)),
                    })

                df_graf_desp = pd.DataFrame(dados_desp)
                grafico_desp = (
                    alt.Chart(df_graf_desp)
                    .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X(
                            "Categoria:N",
                            sort=ordem_cats,
                            axis=alt.Axis(labelAngle=-25, labelLimit=120, title=None),
                        ),
                        xOffset=alt.XOffset("Modelo:N"),
                        y=alt.Y("Desperdício:Q", axis=alt.Axis(title="Kg")),
                        color=alt.Color(
                            "Modelo:N",
                            scale=alt.Scale(domain=["Lidl", "Desperdíci0%"], range=["#64748b", "#0ea5e9"]),
                            legend=None,
                        ),
                        tooltip=[
                            alt.Tooltip("Categoria:N", title="Categoria"),
                            alt.Tooltip("Modelo:N", title="Modelo"),
                            alt.Tooltip("Desperdício:Q", title="Expirado (kg)", format=".1f"),
                        ],
                    )
                    .properties(height=310)
                )
                st.altair_chart(grafico_desp, width="stretch")

                st.markdown("**2. Destino do que não é desperdiçado por categoria (kg salvos):**")
                cols_dest = st.columns(3)
                for col_ui, dest_col in zip(cols_dest, DESTINOS_NAO_DESPERDICIO):
                    linhas_dest = []
                    for cat in ordem_cats:
                        linhas_dest.append({
                            "Categoria": cat,
                            "Modelo": "Lidl",
                            "Quantidade": float((salv_lidl.get(cat) or {}).get(dest_col, 0.0)),
                        })
                        linhas_dest.append({
                            "Categoria": cat,
                            "Modelo": "Desperdíci0%",
                            "Quantidade": float((salv_nosso.get(cat) or {}).get(dest_col, 0.0)),
                        })

                    df_dest = pd.DataFrame(linhas_dest)
                    with col_ui:
                        st.caption(f"**{dest_col}**")
                        graf_dest = (
                            alt.Chart(df_dest)
                            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                            .encode(
                                x=alt.X(
                                    "Categoria:N",
                                    sort=ordem_cats,
                                    axis=alt.Axis(labelAngle=-35, labelLimit=100, title=None),
                                ),
                                xOffset=alt.XOffset("Modelo:N"),
                                y=alt.Y(
                                    "Quantidade:Q",
                                    axis=alt.Axis(
                                        title="Kg" if dest_col == DESTINOS_NAO_DESPERDICIO[0] else None
                                    ),
                                ),
                                color=alt.Color(
                                    "Modelo:N",
                                    scale=alt.Scale(domain=["Lidl", "Desperdíci0%"], range=["#64748b", "#0ea5e9"]),
                                    legend=None,
                                ),
                                tooltip=[
                                    alt.Tooltip("Categoria:N", title="Categoria"),
                                    alt.Tooltip("Modelo:N", title="Modelo"),
                                    alt.Tooltip("Quantidade:Q", title=f"{dest_col} (kg)", format=".1f"),
                                ],
                            )
                            .properties(height=280)
                        )
                        st.altair_chart(graf_dest, width="stretch")

                st.markdown(
                    """
                    <div style="display: flex; justify-content: center; align-items: center; gap: 28px; margin-top: 8px; margin-bottom: 12px; font-size: 16px;">
                        <span style="font-weight: 600; color: var(--text-color);">Modelo de Gestão:</span>
                        <span style="display: inline-flex; align-items: center; gap: 8px; color: var(--text-color);">
                            <span style="width: 15px; height: 15px; background-color: #64748b; border-radius: 3px; display: inline-block;"></span>
                            <span>Lidl</span>
                        </span>
                        <span style="display: inline-flex; align-items: center; gap: 8px; color: var(--text-color);">
                            <span style="width: 15px; height: 15px; background-color: #0ea5e9; border-radius: 3px; display: inline-block;"></span>
                            <span>Desperdíci0%</span>
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def renderizar_simulador_acelerada_sidebar() -> None:
    with st.sidebar.expander("⏩ Simulação Acelerada", expanded=False):
        n_dias = st.selectbox("Dias:", [2, 5, 7], index=1, key="acelerada_n_dias")
        misturar_pert = st.checkbox(
            "Injetar perturbações e clima variados",
            value=True,
            key="acelerada_pert",
        )
        correr_btn = st.button("🚀 Correr Simulação Acelerada", type="primary", width="stretch")

        if correr_btn:
            dias_escolhidos = int(n_dias)
            with st.spinner(f"A simular {dias_escolhidos} dias..."):
                modo_meteo = (
                    st.session_state.get("modo_meteo_ativo")
                    or st.session_state.get("modo_meteo")
                    or "Automático (Tempo Real - Coimbra)"
                )
                resultado = simular_horizonte_temporal(
                    dias_simulacao=dias_escolhidos,
                    modo_meteo=modo_meteo,
                    combinar_perturbacoes_aleatorias=misturar_pert,
                )
                st.session_state["resultado_acelerada"] = resultado
                st.session_state["resultado_multidia"] = resultado
                guardar_snapshot_cenario(_chave_cenario_atual())
                st.session_state["ultima_chave_cenario"] = _chave_cenario_atual()

        if st.session_state.get("resultado_acelerada") or st.session_state.get("resultado_multidia"):
            if st.button("🗑️ Limpar Resultado", width="stretch"):
                st.session_state.pop("resultado_acelerada", None)
                st.session_state.pop("resultado_multidia", None)
                guardar_snapshot_cenario(_chave_cenario_atual())
                st.rerun()