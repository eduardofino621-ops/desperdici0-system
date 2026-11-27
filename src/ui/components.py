import html

import altair as alt
import pandas as pd
import streamlit as st

from src.ui.styles import CORES_DECISAO


def formatar_meteo_rotulo(meteo: dict | None) -> tuple[str, str]:
    """Devolve (tipo_label, descricao_pt) para exibir no Bloco Azul e na Sidebar."""
    if not meteo:
        return "Real", "N/A"
    fonte = str(meteo.get("fonte", ""))
    desc = str(meteo.get("descricao", "N/A")).replace(".", ",")
    tipo = "Simulada" if "Simula" in fonte else "Real"
    return tipo, desc


def obter_dado_pagina(chave: str):
    """Devolve o dado da perturbação que está a ser vista no histórico."""
    historico = st.session_state.get("historico_sessao") or []
    if historico:
        idx = st.session_state.get("pagina_decisoes", len(historico) - 1)
        idx = max(0, min(idx, len(historico) - 1))
        if chave in historico[idx]:
            return historico[idx][chave]
    return st.session_state.get(chave)


def _formatar_valor_eur(valor) -> str | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return f"{float(valor):.2f}€".replace(".", ",")
    texto = str(valor).strip()
    if not texto or texto.upper() == "N/D":
        return None
    limpo = texto.replace("€", "").replace("EUR", "").strip().replace(",", ".")
    try:
        num = float(limpo)
        return f"{num:.2f}€".replace(".", ",")
    except ValueError:
        return texto if "€" in texto else f"{texto}€"


def _obter_pvp_lote(lote_id: str, item: dict) -> str | None:
    chaves_pvp = ("pvp", "PVP", "PVP (€)", "preco_base", "Preço Base", "preco_original", "preco_unitario")
    for k in chaves_pvp:
        if k in item and item[k] not in (None, ""):
            fmt = _formatar_valor_eur(item[k])
            if fmt:
                return fmt

    for fonte_chave in ("resultados_simulacao", "lotes_simulados"):
        registos = obter_dado_pagina(fonte_chave) or st.session_state.get(fonte_chave) or []
        for reg in registos:
            if not isinstance(reg, dict):
                continue
            reg_lote = str(reg.get("Lote") or reg.get("lote_id") or reg.get("id") or "")
            if reg_lote == str(lote_id):
                for k in chaves_pvp:
                    if k in reg and reg[k] not in (None, ""):
                        fmt = _formatar_valor_eur(reg[k])
                        if fmt:
                            return fmt

    prod_id = str(item.get("produto_id") or "")
    if prod_id:
        catalogo = st.session_state.get("catalogo_simulado") or []
        for prod in catalogo:
            if isinstance(prod, dict) and str(prod.get("produto_id") or prod.get("id") or "") == prod_id:
                for k in chaves_pvp:
                    if k in prod and prod[k] not in (None, ""):
                        fmt = _formatar_valor_eur(prod[k])
                        if fmt:
                            return fmt

    return None


@st.dialog("🧠 Cadeia de Decisão dos Agentes", width="large")
def mostrar_popup_agentes(lote_id: str) -> None:
    logs_map = obter_dado_pagina("logs_por_lote") or {}
    item = logs_map.get(lote_id)

    if not item:
        for snap in reversed(st.session_state.get("historico_sessao") or []):
            if isinstance(snap, dict) and isinstance(snap.get("logs_por_lote"), dict):
                if lote_id in snap["logs_por_lote"]:
                    item = snap["logs_por_lote"][lote_id]
                    break

    if not item:
        st.info(
            f"O lote **{lote_id}** tem validade superior a 5 dias ou não possui registo de cadeia "
            "para a perturbação ativa."
        )
        return

    badge_risco = "🔴 Risco Crítico" if item.get("risco_critico") else "🟢 Controlado"
    badge_csp = "✅ CSP Aprovado" if item.get("csp_valido") else "🛡️ Ajustado pelo CSP"
    st.markdown(f"### {item.get('produto_id', '')} ({item.get('lote_id', lote_id)}) — {item.get('nome', 'Lote')}")
    st.caption(
        f"Validade: {item.get('dias', '?')}d | {badge_risco} | "
        f"Resultado: {item.get('preco_final', 'N/D')} [{badge_csp}]"
    )

    evidencias_rag = item.get("contexto_rag", [])
    with st.expander(f"📖 Contexto Recuperado via RAG ({len(evidencias_rag)} evidências)", expanded=True):
        if evidencias_rag:
            for ev in evidencias_rag:
                score_pct = int(round(ev.get("score", 0.0) * 100))
                st.markdown(f"**`{ev['id']}`** — Relevância TF-IDF: `{score_pct}%`")
                st.caption(ev["texto"])
        else:
            st.caption("Nenhuma regra sazonal ou histórica ultrapassou o limiar mínimo de similaridade para este lote.")

    st.markdown(
        f"**1️⃣ Agente de Controlo de Inventário** "
        f"*(Stock: {item.get('quantidade', 'N/D')} | Excesso previsto: {item.get('excesso', 'N/D')})*"
    )
    pvp_fmt = _obter_pvp_lote(lote_id, item) or "N/D"
    parecer_inv = item.get("parecer_inventario", "Sem parecer registado.")
    if "PVP" not in parecer_inv:
        if "PUM " in parecer_inv:
            parecer_inv = parecer_inv.replace("PUM ", f"PVP: {pvp_fmt}, PUM ", 1)
        elif ")." in parecer_inv:
            parecer_inv = parecer_inv.replace(").", f", PVP: {pvp_fmt}).", 1)
        else:
            parecer_inv = f"{parecer_inv} (PVP: {pvp_fmt})"
    st.info(parecer_inv)

    st.markdown(f"**2️⃣ Agente de Logística e Destino Operacional** → Proposta: `{item.get('destino_proposto', 'N/D')}`")
    st.write(item.get("razao_logistica", "Sem justificação registada."))

    st.markdown(f"**3️⃣ Agente de Dynamic Pricing** → Desconto Proposto: `{item.get('desconto_proposto', 'N/D')}`")
    st.write(item.get("raciocinio_pricing", "Sem raciocínio registado."))

    st.markdown("**4️⃣ Auditoria do Módulo Regulador (CSP)**")
    if item.get("csp_valido"):
        st.success(
            f"Conformidade legal e financeira validada. Preço final: **{item.get('preco_final', 'N/D')}** | "
            f"Destino: **{item.get('destino_final', 'N/D')}**."
        )
    else:
        for erro in item.get("csp_erros") or []:
            st.warning(f"Intervenção CSP: {erro}")
        st.markdown(
            f"**Resultado Corrigido:** Desconto **{item.get('desconto_final', 'N/D')}** "
            f"({item.get('preco_final', 'N/D')}) | Destino: **{item.get('destino_final', 'N/D')}**."
        )


def renderizar_cartoes_kpi(kpis: dict) -> None:
    pct_val_str = f"{kpis['pct_validade_curta']:.1f}%".replace(".", ",")
    pct_camp_str = f"{kpis['pct_campanha']:.1f}%".replace(".", ",")
    total_lotes_str = f"{kpis['total_lotes']:,}".replace(",", ".")

    c1, c2, c3 = st.columns(3)
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
            f'<div class="kpi-sub">{kpis["prods_validade_curta"]} produtos</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">Em Campanha Semanal</div>'
            f'<div class="kpi-value" style="color:#0369a1;">{pct_camp_str}</div>'
            f'<div class="kpi-sub">{kpis["prods_campanha"]} produtos</div></div>',
            unsafe_allow_html=True,
        )


def _ir_pagina_decisoes(novo_idx: int) -> None:
    st.session_state["pagina_decisoes"] = novo_idx
    st.session_state["aggrid_key_v"] = st.session_state.get("aggrid_key_v", 0) + 1


def _renderizar_tabela_resumo_html(colunas: list[str], linhas: list[list[str]]) -> None:
    ths = "".join(
        f'<th class="{"col-left" if i == 0 else "col-right"}">{html.escape(col)}</th>'
        for i, col in enumerate(colunas)
    )
    trs = []
    for linha in linhas:
        celulas = []
        for i, val in enumerate(linha):
            classe = "col-left" if i == 0 else "col-right"
            estilo = "" if i == 0 else ' style="white-space:nowrap;"'
            celulas.append(f'<td class="{classe}"{estilo}>{html.escape(str(val))}</td>')
        trs.append(f'<tr>{"".join(celulas)}</tr>')

    tabela_html = (
        f'<div class="resumo-quant-wrap"><table class="resumo-quant-table">'
        f'<thead><tr>{ths}</tr></thead>'
        f'<tbody>{"".join(trs)}</tbody>'
        f'</table></div>'
    )
    st.markdown(tabela_html, unsafe_allow_html=True)


def renderizar_analise_decisoes(historico: list[dict]) -> None:
    if not historico:
        return

    total_paginas = len(historico)
    idx_atual = st.session_state.get("pagina_decisoes", total_paginas - 1)
    idx_atual = max(0, min(idx_atual, total_paginas - 1))
    st.session_state["pagina_decisoes"] = idx_atual

    snapshot = historico[idx_atual]
    snap_anterior = historico[idx_atual - 1] if idx_atual > 0 else None
    chave_prefixo = f"pag_{idx_atual}_{total_paginas}"

    meteo_tipo, meteo_desc = formatar_meteo_rotulo(snapshot.get("meteorologia"))
    if idx_atual == 0:
        titulo_bloco = f"📌 **Início de Sessão:** `{snapshot.get('cenario', 'Nenhuma (Operação Normal)')}`"
    else:
        desc_pert = snapshot.get("descricao_perturbacao") or snapshot.get("cenario", "")
        titulo_bloco = f"⚡ **Perturbação #{idx_atual} – {desc_pert}**"

    st.info(
        f"{titulo_bloco} "
        f"&nbsp;|&nbsp; 📅 **Data Operacional:** `{snapshot['data_str']}` às `{snapshot['hora']}` "
        f"&nbsp;|&nbsp; 🌦️ **Meteorologia ({meteo_tipo}):** `{meteo_desc}`"
    )

    if total_paginas > 1:
        c_prev, c_mid, c_next = st.columns([2.2, 1.6, 2.2], vertical_alignment="center")
        with c_prev:
            st.button(
                "⬅️ Resultados da Perturbação Anterior",
                key="btn_dec_anterior",
                disabled=(idx_atual <= 0),
                width="stretch",
                on_click=_ir_pagina_decisoes,
                args=(max(0, idx_atual - 1),),
            )
        with c_mid:
            rotulo_pag = "Início de Sessão" if idx_atual == 0 else f"Perturbação #{idx_atual}"
            st.markdown(
                f'<div style="text-align:center;font-weight:700;font-size:13px;opacity:0.85;">'
                f'{rotulo_pag} ({idx_atual + 1}/{total_paginas})</div>',
                unsafe_allow_html=True,
            )
        with c_next:
            st.button(
                "Resultados da Perturbação Seguinte ➡️",
                key="btn_dec_seguinte",
                disabled=(idx_atual >= total_paginas - 1),
                width="stretch",
                on_click=_ir_pagina_decisoes,
                args=(min(total_paginas - 1, idx_atual + 1),),
            )

    df_dec = pd.DataFrame(snapshot["registos_decisao"])
    df_filt = df_dec[df_dec["Dias"] <= 5]
    if df_filt.empty:
        st.info("Sem lotes para apresentar neste filtro.")
        return

    contagem = df_filt["Decisão"].value_counts().reset_index()
    contagem.columns = ["Decisão", "Lotes"]
    total_lotes_filt = int(contagem["Lotes"].sum())
    contagem["%"] = contagem["Lotes"].apply(
        lambda x: f"{(x / max(1, total_lotes_filt)) * 100:.1f}%".replace(".", ",")
    )

    col_bar, col_tab = st.columns([2.6, 2.4], gap="large")
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
            tooltip=["Decisão:N", "Lotes:Q", "%:N"],
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
        mapa_atual = dict(zip(contagem["Decisão"], contagem["Lotes"]))

        if snap_anterior is None:
            colunas_tab = ["Decisão", "%", "Lotes (Início Sessão)"]
            linhas_tab = [
                [row["Decisão"], row["%"], str(int(row["Lotes"]))]
                for _, row in contagem.iterrows()
            ]
        else:
            df_prev = pd.DataFrame(snap_anterior["registos_decisao"])
            df_prev = df_prev[df_prev["Dias"] <= 5]
            mapa_prev = df_prev["Decisão"].value_counts().to_dict()
            total_lotes_prev = int(df_prev.shape[0])

            todas_dec = sorted(
                set(mapa_atual.keys()) | set(mapa_prev.keys()),
                key=lambda d: (mapa_atual.get(d, 0), mapa_prev.get(d, 0)),
                reverse=True,
            )

            col_prev = "Lotes (Início Sessão)" if idx_atual == 1 else f"Perturbação #{idx_atual - 1}"
            col_atual = f"Perturbação #{idx_atual}"
            colunas_tab = ["Decisão", "%", col_prev, col_atual, "Delta (p.p. %)"]

            linhas_tab = []
            for dec in todas_dec:
                v_atual = int(mapa_atual.get(dec, 0))
                v_prev = int(mapa_prev.get(dec, 0))
                pct_atual = (v_atual / max(1, total_lotes_filt)) * 100.0
                pct_prev = (v_prev / max(1, total_lotes_prev)) * 100.0
                diff_pp = pct_atual - pct_prev

                pct_str = f"{pct_atual:.1f}%".replace(".", ",")
                if abs(diff_pp) < 0.05:
                    diff_str = "0,0 p.p."
                elif diff_pp > 0:
                    diff_str = f"+{diff_pp:.1f} p.p.".replace(".", ",")
                else:
                    diff_str = f"{diff_pp:.1f} p.p.".replace(".", ",")

                linhas_tab.append([dec, pct_str, str(v_prev), str(v_atual), diff_str])

        _renderizar_tabela_resumo_html(colunas_tab, linhas_tab)

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