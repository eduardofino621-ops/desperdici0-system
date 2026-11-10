def agente_controlo_inventario(state: dict) -> dict:
    """
    Rastreia o inventário, identifica produtos em risco com base na validade
    e calcula a velocidade de escoamento.
    """
    print("[AGENTE INVENTÁRIO] A analisar o inventário e datas de validade...")

    # Simula a leitura do primeiro produto em risco da lista
    inventario = state.get("inventario", [])
    produtos_em_risco = [p for p in inventario if p["dias_para_validade"] <= 2]

    state["produtos_em_risco"] = produtos_em_risco
    if produtos_em_risco:
        state["produto_atual"] = produtos_em_risco[0]
        print(f"[AGENTE INVENTÁRIO] Produto selecionado para análise: {state['produto_atual']['nome']}")
    else:
        state["produto_atual"] = None
        print("[AGENTE INVENTÁRIO] Nenhum produto em risco crítico imediato.")

    return state