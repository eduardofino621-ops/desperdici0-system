def _calcular_pum(preco: float, produto: dict) -> str:
    conteudo = produto.get("conteudo_liquido", 1.0)
    un_ref = produto.get("unidade_referencia", produto.get("unidade_medida", "un"))
    pum = preco / max(0.0001, conteudo)
    return f"{pum:.2f} €/{un_ref}"


def validar_regras_csp(
    lote: dict,
    desconto_proposto: float,
    destino: str,
    produto_catalogo: dict,
    stock_total_sacos: float | None = None,
    fecho_loja_2h: bool = False,
) -> dict:
    """
    Valida e corrige restrições CSP cruzando INVENTARIO_LOTES com CATALOGO_PRODUTOS.
    """
    produto = produto_catalogo or lote

    dias = lote.get("dias_para_expirar", lote.get("dias_para_validade", 3))
    quantidade = lote.get("quantidade_disponivel", lote.get("quantidade_kg", 0.0))
    estado_lote = lote.get("estado", "ativo")

    categoria = produto.get("categoria", "geral")
    unidade = produto.get("unidade_medida", "un")
    pvp = produto.get("pvp", produto.get("preco_venda", 0.0))
    desconto_campanha = produto.get("desconto_campanha", 0.0)
    custo = produto.get("custo_aquisicao", produto.get("preco_base", 0.0))
    margem_minima = produto.get("margem_minima_pct", 0.05)
    custo_descarte = produto.get("custo_descarte", 0.0)

    erros = []
    desconto_ajustado = max(0.0, float(desconto_proposto))
    destino_ajustado = destino

    if estado_lote == "expirado" or dias <= 0:
        erros.append("Bloqueio CSP Crítico: Lote expirado (0 dias restantes); venda e doação proibidas (envio obrigatório para descarte).")
        return {
            "valido": False,
            "válido": False,
            "erros": erros,
            "desconto_ajustado": 0.0,
            "preco_final_ajustado": 0.0,
            "pum_final_ajustado": _calcular_pum(0.0, produto),
            "destino_ajustado": "descarte_obrigatorio",
        }

    # Regra 1: Segurança Alimentar Estrita
    if categoria in ["pescado", "carne"] and dias <= 1 and destino_ajustado == "doacao_externa":
        erros.append(
            "Bloqueio CSP de Segurança: Carne ou pescado com 24h ou menos não pode ser doado externamente; redirecionado para cozinha interna."
        )
        destino_ajustado = "cozinha_interna"

    # Regra 2: Prazo mínimo de 48h para doação externa
    elif destino_ajustado == "doacao_externa" and dias < 2:
        erros.append(
            "Bloqueio CSP Logístico: Produtos a menos de 48h da validade não podem ser doados (restrição logística das IPSS); redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3A: Pão NUNCA pode ir para cozinha interna (higiene e segurança alimentar)
    if categoria == "padaria" and destino_ajustado == "cozinha_interna":
        erros.append(
            "Bloqueio CSP Higiene: Pão exposto ao público não pode entrar na cozinha interna; redirecionado para farinha de ração animal."
        )
        destino_ajustado = "racao_animal"

    # Regra 3B: Apenas padaria pode ser doada para transformação em farinha para ração animal
    if categoria != "padaria" and destino_ajustado == "racao_animal":
        erros.append(
            "Restrição CSP Logística: Apenas excedentes de padaria podem ser encaminhados para farinha de ração animal."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3C: Descontos/Sacos Surpresa em pão de 1 dia só aplicam a <= 2h do fecho de loja
    if categoria == "padaria":
        if dias == 1 and fecho_loja_2h:
            if desconto_ajustado > 0 and destino_ajustado == "prateleira_desconto":
                erros.append(
                    "Restrição CSP Comercial: A <= 2h do fecho, pão com 1 dia de validade é alocado a sacos surpresa."
                )
                destino_ajustado = "sacos_surpresa"
        elif destino_ajustado in ["prateleira_desconto", "sacos_surpresa"] and desconto_ajustado > desconto_campanha:
            erros.append(
                "Restrição CSP Anti-Canibalismo: Descontos de validade/sacos surpresa em padaria só ativam no próprio dia a <= 2h do fecho."
            )
            destino_ajustado = "prateleira_desconto"
            desconto_ajustado = desconto_campanha

    # Regra 4: Peso mínimo agregado para sacos surpresa (mínimo 500g / 0.50 kg de padaria no total)
    peso_sacos = stock_total_sacos if stock_total_sacos is not None else (quantidade * produto.get("conteudo_liquido", 0.10))
    if destino_ajustado == "sacos_surpresa" and peso_sacos < 0.50:
        erros.append(
            f"Restrição CSP Logística: Peso agregado insuficiente ({peso_sacos:.2f} kg < 0.50 kg) para criar sacos surpresa; redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"

    # Coerência de destino sem ESL
    if destino_ajustado in ["doacao_externa", "cozinha_interna", "racao_animal"] and desconto_ajustado > 0:
        erros.append(
            f"Restrição CSP de Coerência: Destino '{destino_ajustado}' não aplica etiqueta ESL ao público; desconto ajustado para 0%."
        )
        desconto_ajustado = 0.0

    # Regra 5: Respeito por campanha ativa
    if destino_ajustado == "prateleira_desconto" and desconto_campanha > 0 and desconto_ajustado < desconto_campanha:
        erros.append(
            f"Restrição CSP Comercial: Desconto proposto ({int(desconto_ajustado * 100)}%) inferior à campanha ativa "
            f"({int(desconto_campanha * 100)}%); ajustado ao mínimo de campanha."
        )
        desconto_ajustado = desconto_campanha

    # Regra 6: Teto máximo legal de 70% em perecíveis
    if categoria in ["carne", "pescado", "laticinios", "fruta", "charcurtaria"] and desconto_ajustado > 0.70:
        erros.append("Bloqueio CSP Legal: Desconto excede o limite máximo de 70% para perecíveis; ajustado para 70%.")
        desconto_ajustado = 0.70

    # Regra 7: Laticínios a <= 24h têm teto de 50%
    if categoria == "laticinios" and dias <= 1 and desconto_ajustado > 0.50:
        erros.append("Restrição CSP Laticínios: Laticínios a <= 24h têm limite máximo de desconto de 50%.")
        desconto_ajustado = 0.50

    # Regra 8: Proteção de Margem vs. Custo de Descarte
    if pvp > 0 and custo > 0 and desconto_ajustado > 0 and destino_ajustado in ["prateleira_desconto", "sacos_surpresa"]:
        preco_final = pvp * (1 - desconto_ajustado)

        if dias > 1:
            preco_piso_normal = custo * (1 + margem_minima)
            if preco_final < preco_piso_normal and desconto_ajustado > desconto_campanha:
                desconto_max_permitido = max(desconto_campanha, round(1 - (preco_piso_normal / pvp), 2))
                erros.append(
                    f"Restrição CSP Financeira (Operação Normal): Preço {preco_final:.2f}€ viola a margem mínima de "
                    f"{int(margem_minima * 100)}% (piso {preco_piso_normal:.2f}€); desconto limitado a {int(desconto_max_permitido * 100)}%."
                )
                desconto_ajustado = desconto_max_permitido
        else:
            preco_piso_critico = max(custo_descarte, pvp * 0.15)
            if preco_final < preco_piso_critico:
                desconto_max_critico = max(0.0, round(1 - (preco_piso_critico / pvp), 2))
                erros.append(
                    f"Restrição CSP Financeira (Modo Crítico): Preço {preco_final:.2f}€ abaixo do piso mínimo de recuperação "
                    f"({preco_piso_critico:.2f}€); desconto limitado a {int(desconto_max_critico * 100)}%."
                )
                desconto_ajustado = desconto_max_critico

    desconto_ajustado = round(desconto_ajustado, 2)
    preco_final_ajustado = round(pvp * (1 - desconto_ajustado), 2)
    pum_final_ajustado = _calcular_pum(preco_final_ajustado, produto)
    valido = len(erros) == 0

    return {
        "valido": valido,
        "válido": valido,
        "erros": erros,
        "desconto_ajustado": desconto_ajustado,
        "preco_final_ajustado": preco_final_ajustado,
        "pum_final_ajustado": pum_final_ajustado,
        "destino_ajustado": destino_ajustado,
    }