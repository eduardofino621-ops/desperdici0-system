def agente_logistica_doacao(state: dict) -> dict:
    """
    Avalia o risco logístico e decide se o produto vai para desconto,
    cozinha interna (ex: pescado para takeaway), sacos surpresa ou doação.
    """
    produto = state.get("produto_atual")
    if not produto:
        return state

    print(f"[AGENTE LOGÍSTICA] A avaliar o risco logístico para: {produto['nome']}...")

    categoria = produto["categoria"]
    dias = produto["dias_para_validade"]

    # Regras específicas de encaminhamento por categoria
    if categoria == "padaria":
        state["destino_proposto"] = "sacos_surpresa"
        print("[AGENTE LOGÍSTICA] Decisão: Encaminhar para 'sacos surpresa'.")
    elif categoria == "pescado" and dias <= 1:
        state["destino_proposto"] = "cozinha_interna"
        print("[AGENTE LOGÍSTICA] Decisão: Redirecionamento interno (pescado para take-away/cozinha).")
    elif dias >= 2:
        state["destino_proposto"] = "doacao_externa"
        print("[AGENTE LOGÍSTICA] Decisão: Encaminhar para doação a instituição parceira.")
    else:
        state["destino_proposto"] = "prateleira_desconto"
        print("[AGENTE LOGÍSTICA] Decisão: Manter na prateleira com desconto.")

    return state