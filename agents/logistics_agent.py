def agente_logistica_doacao(state: dict) -> dict:
    """
    Agente de Logística e Doação. Determina o destino operacional ideal.
    """
    produto = state.get("produto_atual", {})
    dias = produto.get("dias_para_validade", 3)
    categoria = produto.get("categoria", "geral")

    if categoria == "padaria":
        destino = "sacos_surpresa"
        razao = "Pão avulso direcionado para sacos surpresa (sem aderência a desconto linear)."
    elif categoria in ["pescado", "frescos"] and dias <= 1:
        destino = "cozinha_interna"
        razao = "Segurança alimentar estrita: carne/pescado fresco a <= 24h desviado para cozinha interna."
    elif dias >= 2:
        destino = "doacao_externa"
        razao = "Prazo temporal seguro (>48h): elegível para doação externa a instituição parceira."
    else:
        destino = "prateleira_desconto"
        razao = "Manutenção em prateleira com etiqueta ESL dinâmica."

    return {
        "destino_proposto": destino,
        "razao_logistica": razao
    }