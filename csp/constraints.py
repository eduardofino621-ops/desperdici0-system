def validar_regras_csp(produto: dict, desconto_proposto: float, destino: str) -> dict:
    """
    Valida um conjunto alargado de restrições CSP (Constraint Satisfaction Problems)
    para o produto, preço e destino propostos, garantindo conformidade legal e operacional.
    """
    dias = produto["dias_para_validade"]
    categoria = produto["categoria"]
    quantidade = produto.get("quantidade_kg", 0.0)
    preco_base = produto.get("preco_base", 0.0)

    erros = []

    # ----------------------------------------------------
    # REGRAS CSP ORIGINAIS DA PROPOSTA
    # ----------------------------------------------------

    # Regra 1: Produtos a menos de 48h (2 dias) da validade estão bloqueados para doação externa
    if destino == "doacao_externa" and dias < 2:
        erros.append(
            "Bloqueio CSP: Produtos a menos de 48h da validade não podem ser doados (restrição logística da instituição).")
        destino = "prateleira_desconto"

    # Regra 2: Descontos em frescos não podem exceder 70% (evitar dumping / práticas predatórias)
    if categoria in ["frescos", "pescado", "laticinios", "fruta"] and desconto_proposto > 0.70:
        erros.append("Bloqueio CSP: Desconto excede o limite máximo legal de 70% para frescos.")
        desconto_proposto = 0.70  # Correção automática

    # Regra 3: Pão avulso não sofre descontos lineares (deve ir para sacos surpresa)
    if categoria == "padaria" and desconto_proposto > 0 and destino == "prateleira_desconto":
        erros.append(
            "Restrição CSP: Pão avulso não deve sofrer descontos lineares na prateleira; deve ser alocado a sacos surpresa.")
        destino = "sacos_surpresa"

    # ----------------------------------------------------
    # NOVAS REGRAS CSP AVANÇADAS
    # ----------------------------------------------------

    # Regra 4: Segurança Alimentar Estrita (Carne ou Pescado fresco a <= 1 dia nunca vão para doação)
    if categoria in ["pescado", "frescos"] and dias <= 1 and destino == "doacao_externa":
        erros.append(
            "Bloqueio CSP de Segurança: Carne ou pescado com 24h ou menos não pode ser doado, exigindo redirecionamento interno.")
        destino = "cozinha_interna"

    # Regra 5: Margem Mínima Operacional (O preço final não pode ser inferior a 15% do preço base)
    preco_final = preco_base * (1 - desconto_proposto)
    if preco_final < (preco_base * 0.15) and destino == "prateleira_desconto":
        erros.append(
            "Restrição CSP Financeira: O preço com desconto viola o limiar de sustentabilidade operacional (mínimo de 15% do valor base).")
        desconto_proposto = 0.85  # Limitar o desconto máximo a 85% (deixando 15% de preço base)

    # Regra 6: Alocação de Sacos Surpresa por Quantidade Mínima
    if destino == "sacos_surpresa" and quantidade < 5.0:
        erros.append(
            "Restrição CSP Logística: Quantidade insuficiente (< 5kg) para criar saco surpresa dedicado; redirecionado para prateleira.")
        destino = "prateleira_desconto"

    # Regra 7: Lacticínios com menos de 24h têm teto de desconto de 50%
    if categoria == "laticinios" and dias <= 1 and desconto_proposto > 0.50:
        erros.append(
            "Restrição CSP Lacticínios: Lacticínios no último dia de validade têm limite máximo de desconto de 50%.")
        desconto_proposto = 0.50

    valido = len(erros) == 0

    return {
        "valido": valido,
        "erros": erros,
        "desconto_ajustado": desconto_proposto,
        "destino_ajustado": destino
    }