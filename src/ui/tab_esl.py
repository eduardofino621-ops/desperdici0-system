import streamlit as st

from src.simulation.mock_db import calcular_preco_efetivo_lote, calcular_pum
from src.simulation.orchestrator import (
    consolidar_sacos_para_esl,
    formatar_eur,
    formatar_stock,
    obter_lotes_ativos_fefo,
)
from src.ui.styles import CATEGORIAS_UI, formatar_data_pt, gerar_qr_src


def _definir_filtro_esl(novo_filtro: str) -> None:
    st.session_state.filtro_esl_ativo = novo_filtro
    st.session_state.esl_pagina = 1


@st.fragment
def renderizar_aba_esl(data_ativa) -> None:
    st.subheader("🏷️ Etiquetas Eletrónicas de Prateleira (ESL)")

    lotes_esl = st.session_state.lotes_simulados
    catalogo_esl = st.session_state.catalogo_simulado
    sacos_ativos = [s for s in st.session_state.get("sacos_surpresa_lista", []) if not s.get("vendido")]
    grupos_sacos_esl = consolidar_sacos_para_esl(sacos_ativos)

    lotes_por_prod: dict[str, list[dict]] = {}
    for l in lotes_esl:
        lotes_por_prod.setdefault(l["produto_id"], []).append(l)

    prods_alterados_agentes: set[str] = set()
    for p in catalogo_esl:
        p_id = p["produto_id"]
        desc_camp = p.get("desconto_campanha", 0.0)
        lotes_ativos_p = obter_lotes_ativos_fefo(p_id, lotes_por_prod)
        if any(l.get("desconto_validade", 0.0) > desc_camp for l in lotes_ativos_p):
            prods_alterados_agentes.add(p_id)

    st.session_state.setdefault("filtro_esl_ativo", "todos")

    b_top1, b_top2, b_top3 = st.columns(3)
    with b_top1:
        st.button(
            "⭐ Todos (4 Casos Demo no Topo)",
            key="btn_esl_todos",
            type="primary" if st.session_state.filtro_esl_ativo == "todos" else "secondary",
            width="stretch",
            on_click=_definir_filtro_esl,
            args=("todos",),
        )
    with b_top2:
        st.button(
            f"⚠️ Alterados pelos Agentes ({len(prods_alterados_agentes)} art. + {len(grupos_sacos_esl)} sacos surpresa)",
            key="btn_esl_risco",
            type="primary" if st.session_state.filtro_esl_ativo == "risco" else "secondary",
            width="stretch",
            on_click=_definir_filtro_esl,
            args=("risco",),
        )
    with b_top3:
        st.button(
            f"🛍️ Sacos Surpresa ({len(grupos_sacos_esl)})",
            key="btn_esl_sacos",
            type="primary" if st.session_state.filtro_esl_ativo == "sacos" else "secondary",
            width="stretch",
            on_click=_definir_filtro_esl,
            args=("sacos",),
        )

    for linha_cats in (CATEGORIAS_UI[:4], CATEGORIAS_UI[4:]):
        cols_cat = st.columns(4)
        for col_c, (cat_key, cat_label) in zip(cols_cat, linha_cats):
            with col_c:
                st.button(
                    cat_label,
                    key=f"btn_esl_cat_{cat_key}",
                    type="primary" if st.session_state.filtro_esl_ativo == cat_key else "secondary",
                    width="stretch",
                    on_click=_definir_filtro_esl,
                    args=(cat_key,),
                )

    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        pesquisa_esl = st.text_input(
            "🔎 Pesquisar artigo na ESL:",
            placeholder="Ex: Saco Surpresa, Salmão, Bife, Pão, Iogurte...",
        )

    filtro_atual = st.session_state.filtro_esl_ativo
    ids_demo = ["PROD-0001", "PROD-0002", "PROD-0003", "PROD-0004"]
    termo = pesquisa_esl.lower().strip()

    def _passa_pesquisa_prod(prod: dict) -> bool:
        return not termo or termo in prod["nome"].lower() or termo in prod["produto_id"].lower()

    def _passa_pesquisa_saco(grupo: dict) -> bool:
        return not termo or termo in grupo["titulo"].lower()

    itens_unificados = []
    if filtro_atual == "todos":
        prods_por_id = {p["produto_id"]: p for p in catalogo_esl}
        for pid_demo in ids_demo:
            prod_demo = prods_por_id.get(pid_demo)
            if prod_demo and _passa_pesquisa_prod(prod_demo):
                itens_unificados.append({"tipo": "produto", "dados": prod_demo})
        for grupo_saco in grupos_sacos_esl:
            if _passa_pesquisa_saco(grupo_saco):
                itens_unificados.append({"tipo": "saco", "dados": grupo_saco})
        for prod in catalogo_esl:
            if prod["produto_id"] not in ids_demo and _passa_pesquisa_prod(prod):
                itens_unificados.append({"tipo": "produto", "dados": prod})

    elif filtro_atual == "risco":
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
        prods_cat = [p for p in catalogo_esl if p.get("categoria") == filtro_atual and _passa_pesquisa_prod(p)]
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
        return

    inicio = (pagina_atual - 1) * por_pagina
    pagina_items = itens_unificados[inicio : inicio + por_pagina]
    cols = st.columns(3, gap="medium")

    for idx, item_esl in enumerate(pagina_items):
        if item_esl["tipo"] == "saco":
            grupo = item_esl["dados"]
            qtd_disp = len(grupo["sacos_instancias"])
            qr_saco = gerar_qr_src(f"{grupo['titulo']}|{grupo['preco_final']}")

            esl_html = (
                f'<div class="esl-bezel"><div class="esl-screen">'
                f'<div><div class="esl-header"><div class="esl-prod-name">{grupo["titulo"]}</div></div>'
                f'<div class="esl-middle"><div><div class="esl-strike-wrap">PVP {formatar_eur(grupo["preco_base"])} <span class="esl-unit-tag">SACO</span></div></div>'
                f'<div class="esl-saco-stock">{qtd_disp} {"saco disp." if qtd_disp == 1 else "sacos disp."}</div></div></div>'
                f'<div><div class="esl-footer"><img src="{qr_saco}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group"><div class="esl-discount-badge">-{grupo["desconto_pct"]}%</div>'
                f'<div class="esl-price-right"><div class="esl-pum">DESC. VALIDADE</div>'
                f'<div class="esl-big-price">{formatar_eur(grupo["preco_final"])} <span class="esl-unit-tag">SACO</span></div></div></div></div>'
                f'<div class="esl-validade-bar">Desconto a produtos com Data de Validade: &nbsp; {formatar_data_pt(data_ativa.isoformat())}</div></div>'
                f'</div></div>'
            )

            with cols[idx % 3]:
                st.markdown(esl_html, unsafe_allow_html=True)
                if st.button(f"🛍️ Vender 1 {grupo['titulo']}", key=f"sell_saco_grp_{filtro_atual}_{pagina_atual}_{idx}", width="stretch"):
                    saco_vender = grupo["sacos_instancias"][0]
                    saco_vender["vendido"] = True
                    lotes_map_sim = {l["lote_id"]: l for l in st.session_state.lotes_simulados}
                    rows_map = {r["Lote"]: r for r in st.session_state.resultados_simulacao}
                    for l_id, qtd_abater in saco_vender["lotes_consumo"].items():
                        lote_ref = lotes_map_sim.get(l_id)
                        if lote_ref:
                            lote_ref["quantidade_disponivel"] = max(0.0, round(lote_ref["quantidade_disponivel"] - qtd_abater, 1))
                            if lote_ref["quantidade_disponivel"] <= 0:
                                lote_ref["estado"] = "esgotado"
                            row = rows_map.get(l_id)
                            if row:
                                un_row = row["Stock"].split(" ")[-1]
                                row["Stock"] = formatar_stock(lote_ref["quantidade_disponivel"], un_row)
                                if lote_ref["quantidade_disponivel"] <= 0:
                                    row["Destino Operacional"] = "Vendido em Saco Surpresa"
                    st.rerun(scope="fragment")
            continue

        prod = item_esl["dados"]
        prod_id = prod["produto_id"]
        gtin = prod.get("gtin", "")
        nome = prod.get("nome", "Produto")
        unidade = prod.get("unidade_medida", "un")
        pvp = prod.get("pvp", 0.0)
        desc_campanha = prod.get("desconto_campanha", 0.0)
        periodo_campanha = prod.get("periodo_campanha", "")

        lotes_ativos_prod = obter_lotes_ativos_fefo(prod_id, lotes_por_prod)
        lotes_com_validade = [l for l in lotes_ativos_prod if l.get("desconto_validade", 0.0) > desc_campanha]

        pum_base = calcular_pum(pvp, prod).replace(".", ",")
        qr_url = gerar_qr_src(f"01|{gtin}|SKU|{prod_id}")

        tem_desconto_validade = len(lotes_com_validade) > 0
        tem_folheto = desc_campanha > 0

        if tem_folheto:
            bloco_pvp_html = (
                f'<div><div class="esl-pum">{pum_base}</div>'
                f'<div class="esl-strike-wrap">PVP {formatar_eur(pvp)} <span class="esl-unit-tag">{unidade}</span></div></div>'
            )
        else:
            bloco_pvp_html = (
                f'<div><div class="esl-pum">{pum_base}</div>'
                f'<div class="esl-pvp-clean">PVP {formatar_eur(pvp)} <span class="esl-unit-tag">{unidade}</span></div></div>'
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
                    f'<div class="esl-folheto-box"><div class="esl-pum">{pum_folheto}</div>'
                    f'<div><span class="esl-folheto-pct">-{int(desc_campanha * 100)}%</span> '
                    f'<span class="esl-folheto-price">{formatar_eur(preco_folheto)}</span> <span class="esl-unit-tag">{unidade}</span></div>'
                    f'<div class="esl-folheto-dates">Válido de {periodo_campanha}</div></div>'
                )
            else:
                topo_dir = ""

            extras_html = ""
            if lotes_seguintes:
                linhas_extras = [
                    f'<div class="esl-extra-lote-row">'
                    f'<span>-{int(d_ef * 100)}% ({formatar_eur(p_ef)} {unidade})</span>'
                    f'<span>Val. {formatar_data_pt(l_seg.get("data_validade", ""))}</span></div>'
                    for l_seg in lotes_seguintes
                    for d_ef, p_ef in [calcular_preco_efetivo_lote(l_seg, prod)]
                ]
                extras_html = (
                    f'<div class="esl-extra-lotes">'
                    f'<div style="font-size:9.5px;font-weight:700;color:#334155;">Outros Descontos com Aproximação de Prazo de Validade:</div>'
                    f'{"".join(linhas_extras)}</div>'
                )

            footer_html = (
                f'<div class="esl-footer"><img src="{qr_url}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group"><div class="esl-discount-badge">-{int(desc_principal * 100)}%</div>'
                f'<div class="esl-price-right"><div class="esl-pum">{pum_principal}</div>'
                f'<div class="esl-big-price">{formatar_eur(preco_principal)} <span class="esl-unit-tag">{unidade}</span></div></div></div></div>'
                f'<div class="esl-validade-bar">Desconto a produtos com Data de Validade: &nbsp; {data_val_principal}</div>'
                f'{extras_html}'
            )

        elif tem_folheto:
            preco_folheto = round(pvp * (1 - desc_campanha), 2)
            pum_folheto = calcular_pum(preco_folheto, prod).replace(".", ",")
            topo_esq, topo_dir = bloco_pvp_html, ""
            footer_html = (
                f'<div class="esl-footer"><img src="{qr_url}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group"><div class="esl-discount-badge" style="color:#0f172a;font-size:25px;">-{int(desc_campanha * 100)}%</div>'
                f'<div class="esl-price-right"><div class="esl-pum">{pum_folheto}</div>'
                f'<div class="esl-folheto-main-price">{formatar_eur(preco_folheto)} <span class="esl-unit-tag">{unidade}</span></div></div></div></div>'
                f'<div class="esl-validade-bar" style="color:#334155;">Campanha válida de {periodo_campanha}</div>'
            )

        else:
            topo_esq, topo_dir = "", ""
            footer_html = (
                f'<div class="esl-footer"><img src="{qr_url}" class="esl-qr" alt="QR" />'
                f'<div class="esl-promo-group"><div class="esl-price-right"><div class="esl-pum">{pum_base}</div>'
                f'<div class="esl-big-price">{formatar_eur(pvp)} <span class="esl-unit-tag">{unidade}</span></div></div></div></div>'
            )

        esl_html = (
            f'<div class="esl-bezel"><div class="esl-screen">'
            f'<div><div class="esl-header"><div class="esl-prod-name">{nome}</div><div class="esl-gtin">{gtin}</div></div>'
            f'<div class="esl-middle">{topo_esq}{topo_dir}</div></div>'
            f'<div>{footer_html}</div></div></div>'
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
                    st.rerun(scope="fragment")