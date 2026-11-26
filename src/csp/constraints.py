import math


def _calcular_pum(preco: float, produto: dict) -> str:
    conteudo = produto.get("conteudo_liquido", 1.0)
    un_ref = produto.get("unidade_referencia", produto.get("unidade_medida", "un"))
    pum = preco / max(0.0001, conteudo)
    return f"{pum:.2f} €/{un_ref}"


def _eh_elegivel_saco_padaria(lote_id: str, quota_fracao: float = 0.50) -> bool:
    """Seleciona de forma determinística a fração alvo dos lotes com base no número do lote."""
    digitos = "".join(c for c in str(lote_id) if c.isdigit())
    if not digitos:
        return False
    valor = (int(digitos) % 100) / 100.0
    return valor < max(0.0, min(1.0, quota_fracao))


def validar_regras_csp(
    lote: dict,
    desconto_proposto: float,
    destino: str,
    produto_catalogo: dict,
    stock_total_sacos: float | None = None,
    fecho_loja_2h: bool = False,
    quebra_clientes: bool = False,
) -> dict:
    """
    Valida e corrige restrições CSP cruzando INVENTARIO_LOTES com CATALOGO_PRODUTOS.
    """
    produto = produto_catalogo or lote

    lote_id = lote.get("lote_id", "")
    dias = lote.get("dias_para_expirar", lote.get("dias_para_validade", 3))
    quantidade = lote.get("quantidade_disponivel", lote.get("quantidade_kg", 0.0))
    estado_lote = lote.get("estado", "ativo")

    categoria = produto.get("categoria", "geral")
    pvp = produto.get("pvp", produto.get("preco_venda", 0.0))
    desconto_campanha = produto.get("desconto_campanha", 0.0)
    custo = produto.get("custo_aquisicao", produto.get("preco_base", 0.0))
    margem_minima = produto.get("margem_minima_pct", 0.05)
    custo_descarte = produto.get("custo_descarte", 0.0)

    erros = []
    desconto_ajustado = max(0.0, float(desconto_proposto))
    destino_ajustado = destino

    if estado_lote == "expirado" or dias <= 0:
        if categoria == "padaria":
            erros.append(
                "Bloqueio CSP Padaria: Pão em fim de vida útil (0 dias); encaminhado para farinha de ração animal."
            )
            return {
                "valido": False,
                "válido": False,
                "erros": erros,
                "desconto_ajustado": 0.0,
                "preco_final_ajustado": 0.0,
                "pum_final_ajustado": _calcular_pum(0.0, produto),
                "destino_ajustado": "racao_animal",
            }
        erros.append(
            "Bloqueio CSP Crítico: Lote expirado (0 dias restantes); venda e doação proibidas "
            "(envio obrigatório para descarte)."
        )
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
            "Bloqueio CSP de Segurança: Carne ou pescado com 24h ou menos não pode ser doado externamente; "
            "redirecionado para cozinha interna."
        )
        destino_ajustado = "cozinha_interna"

    # Regra 2: Prazo mínimo de 48h para doação externa
    elif destino_ajustado == "doacao_externa" and dias < 2:
        erros.append(
            "Bloqueio CSP Logístico: Produtos a menos de 48h da validade não podem ser doados "
            "(restrição logística das IPSS); redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3A: Pão NUNCA pode ir para cozinha interna (higiene e segurança alimentar)
    if categoria == "padaria" and destino_ajustado == "cozinha_interna":
        erros.append(
            "Bloqueio CSP Higiene: Pão exposto ao público não pode entrar na cozinha interna; "
            "redirecionado para farinha de ração animal."
        )
        destino_ajustado = "racao_animal"

    # Regra 3B: Apenas padaria pode ser doada para transformação em farinha para ração animal
    if categoria != "padaria" and destino_ajustado == "racao_animal":
        erros.append(
            "Restrição CSP Logística: Apenas excedentes de padaria podem ser encaminhados para farinha "
            "de ração animal."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3C: Política Dinâmica de Padaria (Quota de Sacos Surpresa + Desconto ESL + Ração Animal)
    quota_sacos = 0.65 if (fecho_loja_2h or quebra_clientes) else 0.50
    eh_elegivel_saco = _eh_elegivel_saco_padaria(lote_id, quota_fracao=quota_sacos)
    eh_lote_saco_padaria = (
        categoria == "padaria"
        and eh_elegivel_saco
        and ((dias == 1 and not fecho_loja_2h) or (dias == 2 and fecho_loja_2h))
    )

    if categoria == "padaria":
        if dias == 1 and fecho_loja_2h:
            if destino_ajustado == "sacos_surpresa" and not eh_elegivel_saco:
                destino_ajustado = "prateleira_desconto"
            if destino_ajustado == "prateleira_desconto":
                desconto_ajustado = max(desconto_ajustado, 0.50)
        elif eh_lote_saco_padaria:
            if destino_ajustado == "prateleira_desconto" and desconto_ajustado > desconto_campanha:
                erros.append(
                    f"Restrição CSP Comercial: Fração de {int(quota_sacos * 100)}% da padaria elegível "
                    "é alocada a Sacos Surpresa."
                )
                destino_ajustado = "sacos_surpresa"
        elif dias == 1 and destino_ajustado == "prateleira_desconto":
            desconto_ajustado = max(desconto_ajustado, 0.35)
        elif destino_ajustado == "sacos_surpresa" and not eh_elegivel_saco:
            erros.append(
                f"Restrição CSP Quota Sacos: Limite de {int(quota_sacos * 100)}% para Sacos Surpresa "
                "atingido; lote mantido em prateleira com etiqueta ESL."
            )
            destino_ajustado = "prateleira_desconto"

    # Regra 4: Peso mínimo agregado para sacos surpresa (mínimo 500g / 0.50 kg de padaria no total)
    peso_sacos = (
        stock_total_sacos
        if stock_total_sacos is not None
        else (quantidade * produto.get("conteudo_liquido", 0.10))
    )
    if destino_ajustado == "sacos_surpresa" and peso_sacos < 0.50:
        erros.append(
            f"Restrição CSP Logística: Peso agregado insuficiente ({peso_sacos:.2f} kg < 0.50 kg) "
            "para criar sacos surpresa; redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"

    # Coerência de destino sem ESL
    if destino_ajustado in ["doacao_externa", "cozinha_interna", "racao_animal"] and desconto_ajustado > 0:
        erros.append(
            f"Restrição CSP de Coerência: Destino '{destino_ajustado}' não aplica etiqueta ESL ao público; "
            "desconto ajustado para 0%."
        )
        desconto_ajustado = 0.0

    # Regra 5: Desconto de validade tem de ser SEMPRE superior à campanha ativa (+5% mínimo)
    if (
        destino_ajustado in ["prateleira_desconto", "sacos_surpresa"]
        and desconto_campanha > 0
        and desconto_ajustado > 0
        and desconto_ajustado <= desconto_campanha
    ):
        novo_desc = min(0.70, round(desconto_campanha + 0.05, 2))
        erros.append(
            f"Restrição CSP Comercial: Desconto de validade ({int(desconto_ajustado * 100)}%) tem de superar "
            f"a campanha ativa ({int(desconto_campanha * 100)}%); ajustado para {int(novo_desc * 100)}%."
        )
        desconto_ajustado = novo_desc

    # Regra 6: Teto máximo legal de 70% em perecíveis e sacos surpresa
    if (
        categoria in ["carne", "pescado", "laticinios", "fruta", "charcutaria", "padaria"]
        and desconto_ajustado > 0.70
    ):
        erros.append("Bloqueio CSP Legal: Desconto excede o limite máximo de 70%; ajustado para 70%.")
        desconto_ajustado = 0.70

    # Regra 7: Laticínios a <= 24h têm teto de 50%
    if categoria == "laticinios" and dias <= 1 and desconto_ajustado > 0.50:
        erros.append("Restrição CSP Laticínios: Laticínios a <= 24h têm limite máximo de desconto de 50%.")
        desconto_ajustado = 0.50

    # Regra 8: Proteção de Margem vs. Custo de Descarte (com math.floor para nunca violar o piso por cêntimos)
    if pvp > 0 and custo > 0 and desconto_ajustado > 0 and destino_ajustado in ["prateleira_desconto", "sacos_surpresa"]:
        preco_final = pvp * (1 - desconto_ajustado)

        if dias > 1:
            preco_piso_normal = custo * (1 + margem_minima)
            if preco_final + 1e-9 < preco_piso_normal and desconto_ajustado > desconto_campanha:
                desconto_max_permitido = max(
                    desconto_campanha,
                    math.floor((1 - (preco_piso_normal / pvp)) * 100) / 100,
                )
                erros.append(
                    f"Restrição CSP Financeira (Operação Normal): Preço {preco_final:.2f}€ viola a margem mínima de "
                    f"{int(margem_minima * 100)}% (piso {preco_piso_normal:.2f}€); desconto limitado a "
                    f"{int(desconto_max_permitido * 100)}%."
                )
                desconto_ajustado = desconto_max_permitido
        else:
            preco_piso_critico = max(custo_descarte, pvp * 0.15)
            if preco_final + 1e-9 < preco_piso_critico:
                desconto_max_critico = max(
                    0.0,
                    math.floor((1 - (preco_piso_critico / pvp)) * 100) / 100,
                )
                erros.append(
                    f"Restrição CSP Financeira (Modo Crítico): Preço {preco_final:.2f}€ abaixo do piso mínimo "
                    f"de recuperação ({preco_piso_critico:.2f}€); desconto limitado a "
                    f"{int(desconto_max_critico * 100)}%."
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