def validar_regras_csp(produto: dict, desconto_proposto: float, destino: str) -> dict:
    """
    Valida as restrições CSP (Constraint Satisfaction Problems) para o produto e ação proposta.
    Retorna um dicionário com o resultado da validação e eventuais correções.
    """
    dias = produto["dias_para_validade"]
    categoria = produto["categoria"]

    erros = []

    # Regra 1: Produtos a menos de 48h (2 dias) da validade estão bloqueados para doação externa
    if destino == "doacao_externa" and dias < 2:
        erros.append(
            "Bloqueio CSP: Produtos a menos de 48h da validade não podem ser doados (restrição logística da instituição).")

    # Regra 2: Descontos em frescos não podem exceder 70% (evitar dumping / práticas predatórias)
    if categoria in ["frescos", "pescado", "laticinios"] and desconto_proposto > 0.70:
        erros.append("Bloqueio CSP: Desconto excede o limite máximo legal de 70% para frescos.")
        desconto_proposto = 0.70  # Correção automática para o limite permitido

    # Regra 3: Pão avulso não sofre descontos lineares (deve ir para sacos surpresa)
    if categoria == "padaria" and desconto_proposto > 0 and destino == "prateleira_desconto":
        erros.append(
            "Restrição CSP: Pão avulso não deve sofrer descontos lineares na prateleira; deve ser alocado a sacos surpresa.")

    valido = len(erros) == 0

    return {
        "valido": valido,
        "erros": erros,
        "desconto_ajustado": desconto_proposto
    }