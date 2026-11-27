import math

CATEGORIAS_PADARIA_PASTELARIA = frozenset({"padaria", "pastelaria"})


def _normalizar_categoria(categoria: str | None, default: str = "geral") -> str:
    cat = (categoria or default).strip().lower()
    if cat in ["peixe", "pescado"]:
        return "pescado"
    if cat in ["horticolas", "hortícolas", "legumes"]:
        return "legumes"
    if cat in ["laticínios", "laticinios"]:
        return "laticinios"
    return cat


def _calcular_pum(preco: float, produto: dict) -> str:
    conteudo = produto.get("conteudo_liquido", 1.0)
    un_ref = produto.get("unidade_referencia", produto.get("unidade_medida", "un"))
    pum = preco / max(0.0001, conteudo)
    return f"{pum:.2f} €/{un_ref}"


def eh_elegivel_saco_padaria(lote_id: str, quota_fracao: float = 0.35) -> bool:
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
    chuva_temporal: bool = False,
) -> dict:
    """
    Valida e corrige restrições CSP cruzando INVENTARIO_LOTES com CATALOGO_PRODUTOS.
    """
    produto = produto_catalogo or lote

    lote_id = lote.get("lote_id", "")
    dias = int(lote.get("dias_para_expirar", lote.get("dias_para_validade", 3)))
    quantidade = float(lote.get("quantidade_disponivel", lote.get("quantidade_kg", 0.0)))
    estado_lote = lote.get("estado", "ativo")

    categoria = _normalizar_categoria(produto.get("categoria", "geral"))
    tipo_validade = (produto.get("tipo_validade") or "consumir_ate").lower()
    pvp = float(produto.get("pvp", produto.get("preco_venda", 0.0)))
    desconto_campanha = float(produto.get("desconto_campanha", 0.0))
    custo = float(produto.get("custo_aquisicao", produto.get("preco_base", 0.0)))
    margem_minima = float(produto.get("margem_minima_pct", 0.05))
    custo_descarte = float(produto.get("custo_descarte", 0.0))

    erros = []
    desconto_ajustado = max(0.0, float(desconto_proposto))
    destino_ajustado = destino
    desc_padaria_prateleira = 0.45 if fecho_loja_2h else 0.25
    desc_saco_alvo = 0.45

    if estado_lote == "expirado" or dias <= 0:
        if categoria in CATEGORIAS_PADARIA_PASTELARIA:
            erros.append(
                "Bloqueio CSP Padaria/Pastelaria: Artigo em fim de vida útil (0 dias); "
                "encaminhado para farinha de ração animal."
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
        if tipo_validade == "preferencia_antes" and estado_lote != "expirado":
            if destino_ajustado != "doacao_externa" or desconto_ajustado > 0:
                erros.append(
                    "Restrição CSP Durabilidade Mínima: Artigo 'Consumir de preferência antes de' a 0 dias "
                    "retirado de venda direta e encaminhado para doação externa."
                )
            return {
                "valido": len(erros) == 0,
                "válido": len(erros) == 0,
                "erros": erros,
                "desconto_ajustado": 0.0,
                "preco_final_ajustado": 0.0,
                "pum_final_ajustado": _calcular_pum(0.0, produto),
                "destino_ajustado": "doacao_externa",
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

    # Regra 2: Prazo mínimo de 48h para doação externa de perecíveis ("consumir_ate")
    elif destino_ajustado == "doacao_externa" and dias < 2 and tipo_validade == "consumir_ate":
        erros.append(
            "Bloqueio CSP Logístico: Produtos 'Consumir até' a menos de 48h da validade não podem ser doados "
            "(restrição logística das IPSS); redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3A: Padaria/Pastelaria NUNCA vai para cozinha interna (higiene e segurança alimentar)
    if categoria in CATEGORIAS_PADARIA_PASTELARIA and destino_ajustado == "cozinha_interna":
        erros.append(
            "Bloqueio CSP Higiene: Padaria/pastelaria exposta ao público não pode entrar na cozinha interna; "
            "redirecionada para farinha de ração animal."
        )
        destino_ajustado = "racao_animal"

    # Regra 3B: Apenas padaria/pastelaria pode ser encaminhada para farinha para ração animal
    if categoria not in CATEGORIAS_PADARIA_PASTELARIA and destino_ajustado == "racao_animal":
        erros.append(
            "Restrição CSP Logística: Apenas excedentes de padaria e pastelaria podem ser encaminhados "
            "para farinha de ração animal."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3C: Apenas padaria/pastelaria pode ser alocada a Sacos Surpresa
    if categoria not in CATEGORIAS_PADARIA_PASTELARIA and destino_ajustado == "sacos_surpresa":
        erros.append(
            "Restrição CSP Logística: Apenas excedentes de padaria e pastelaria podem ser alocados a "
            "Sacos Surpresa; redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"

    # Regra 3D: Política Dinâmica de Padaria/Pastelaria alinhada com Logística (35% normal / 50% perturbação)
    quota_sacos = 0.50 if (fecho_loja_2h or quebra_clientes) else 0.35
    eh_elegivel_saco = eh_elegivel_saco_padaria(lote_id, quota_fracao=quota_sacos)
    eh_lote_saco_padaria = (
        categoria in CATEGORIAS_PADARIA_PASTELARIA
        and eh_elegivel_saco
        and (dias == 1 or (dias == 2 and fecho_loja_2h))
    )

    if categoria in CATEGORIAS_PADARIA_PASTELARIA:
        if destino_ajustado == "sacos_surpresa":
            if not eh_elegivel_saco or not (dias == 1 or (dias == 2 and fecho_loja_2h)):
                erros.append(
                    f"Restrição CSP Quota Sacos: Lote fora da quota elegível ({int(quota_sacos * 100)}%) "
                    "para Sacos Surpresa; mantido em prateleira com etiqueta ESL."
                )
                destino_ajustado = "prateleira_desconto"
                if dias == 1:
                    desconto_ajustado = max(desconto_ajustado, desc_padaria_prateleira)
            else:
                desconto_ajustado = max(desconto_ajustado, desc_saco_alvo)
        elif eh_lote_saco_padaria and destino_ajustado == "prateleira_desconto":
            erros.append(
                f"Restrição CSP Comercial: Fração elegível ({int(quota_sacos * 100)}%) da padaria/pastelaria "
                "alocada a Sacos Surpresa."
            )
            destino_ajustado = "sacos_surpresa"
            desconto_ajustado = max(desconto_ajustado, desc_saco_alvo)
        elif dias == 1 and destino_ajustado == "prateleira_desconto":
            desconto_ajustado = max(desconto_ajustado, desc_padaria_prateleira)

    # Regra 4: Peso mínimo agregado para sacos surpresa (mínimo 500g / 0.50 kg elegível)
    peso_sacos = (
        stock_total_sacos
        if stock_total_sacos is not None
        else (quantidade * float(produto.get("conteudo_liquido", 0.10)))
    )
    if destino_ajustado == "sacos_surpresa" and peso_sacos < 0.50:
        erros.append(
            f"Restrição CSP Logística: Peso agregado insuficiente ({peso_sacos:.2f} kg < 0.50 kg) "
            "para criar sacos surpresa; redirecionado para prateleira."
        )
        destino_ajustado = "prateleira_desconto"
        if categoria in CATEGORIAS_PADARIA_PASTELARIA and dias == 1:
            desconto_ajustado = max(desconto_ajustado, desc_padaria_prateleira)

    # Coerência de destino sem ESL
    if destino_ajustado in ["doacao_externa", "cozinha_interna", "racao_animal"] and desconto_ajustado > 0:
        erros.append(
            f"Restrição CSP de Coerência: Destino '{destino_ajustado}' não aplica etiqueta ESL ao público; "
            "desconto ajustado para 0%."
        )
        desconto_ajustado = 0.0

    # Regra 6: Teto máximo legal de 70% em perecíveis, padaria/pastelaria e sacos surpresa
    teto_max_permitido = 0.70
    if (
        categoria in ["carne", "pescado", "laticinios", "fruta", "legumes", "charcutaria", "padaria", "pastelaria"]
        and desconto_ajustado > 0.70
    ):
        erros.append("Bloqueio CSP Legal: Desconto excede o limite máximo de 70%; ajustado para 70%.")
        desconto_ajustado = 0.70

    # Regra 7: Laticínios a <= 24h têm teto de 50%
    if categoria == "laticinios" and dias <= 1:
        teto_max_permitido = min(teto_max_permitido, 0.50)
        if desconto_ajustado > 0.50:
            erros.append("Restrição CSP Laticínios: Laticínios a <= 24h têm limite máximo de desconto de 50%.")
            desconto_ajustado = 0.50

    # Regra 7B: Faixa gradual em dia de chuva/temporal (15%-30% a 2d; 35%-45% a <=1d)
    if (
        chuva_temporal
        and not fecho_loja_2h
        and not quebra_clientes
        and destino_ajustado in ["prateleira_desconto", "sacos_surpresa"]
    ):
        if dias == 2:
            teto_max_permitido = min(teto_max_permitido, 0.30)
            if desconto_ajustado > 0.30:
                erros.append(
                    "Restrição CSP Meteorologia (Chuva/Temporal): Desconto a 2 dias limitado a 30%."
                )
                desconto_ajustado = 0.30
        elif dias <= 1:
            teto_max_permitido = min(teto_max_permitido, 0.45)
            if desconto_ajustado > 0.45:
                erros.append(
                    "Restrição CSP Meteorologia (Chuva/Temporal): Desconto no último dia limitado a 45%."
                )
                desconto_ajustado = 0.45

    # Regra 8: Proteção de Margem vs. Custo de Descarte
    if pvp > 0 and custo > 0 and destino_ajustado in ["prateleira_desconto", "sacos_surpresa"]:
        if dias > 1:
            preco_piso_normal = custo * (1 + margem_minima)
            desconto_max_permitido = max(
                0.0,
                math.floor((1 - (preco_piso_normal / pvp)) * 100) / 100,
            )
            teto_max_permitido = min(teto_max_permitido, desconto_max_permitido)
            if desconto_ajustado > 0:
                preco_final = pvp * (1 - desconto_ajustado)
                if preco_final + 1e-9 < preco_piso_normal and desconto_ajustado > desconto_campanha:
                    novo_teto = max(desconto_campanha, desconto_max_permitido)
                    erros.append(
                        f"Restrição CSP Financeira (Operação Normal): Preço {preco_final:.2f}€ viola a margem mínima de "
                        f"{int(margem_minima * 100)}% (piso {preco_piso_normal:.2f}€); desconto limitado a "
                        f"{int(novo_teto * 100)}%."
                    )
                    desconto_ajustado = novo_teto
        else:
            preco_piso_critico = max(custo_descarte, pvp * 0.15)
            desconto_max_critico = max(
                0.0,
                math.floor((1 - (preco_piso_critico / pvp)) * 100) / 100,
            )
            teto_max_permitido = min(teto_max_permitido, desconto_max_critico)
            if desconto_ajustado > 0:
                preco_final = pvp * (1 - desconto_ajustado)
                if preco_final + 1e-9 < preco_piso_critico:
                    erros.append(
                        f"Restrição CSP Financeira (Modo Crítico): Preço {preco_final:.2f}€ abaixo do piso mínimo "
                        f"de recuperação ({preco_piso_critico:.2f}€); desconto limitado a "
                        f"{int(desconto_max_critico * 100)}%."
                    )
                    desconto_ajustado = desconto_max_critico

    # Regra 5: Desconto de validade tem de ser SEMPRE superior à campanha ativa (+5% mínimo)
    if (
        destino_ajustado in ["prateleira_desconto", "sacos_surpresa"]
        and desconto_campanha > 0
        and desconto_ajustado > 0
        and desconto_ajustado <= desconto_campanha + 1e-9
    ):
        min_desc_validade = round(desconto_campanha + 0.05, 2)
        if min_desc_validade <= teto_max_permitido + 1e-9:
            erros.append(
                f"Restrição CSP Comercial: Desconto de validade ({int(desconto_ajustado * 100)}%) tem de superar "
                f"a campanha ativa ({int(desconto_campanha * 100)}%); ajustado para {int(min_desc_validade * 100)}%."
            )
            desconto_ajustado = min_desc_validade
        else:
            erros.append(
                f"Restrição CSP Comercial/Financeira: O teto permitido ({int(teto_max_permitido * 100)}%) não permite "
                f"superar a campanha ativa ({int(desconto_campanha * 100)}%) em +5%; mantido apenas desconto de campanha."
            )
            desconto_ajustado = 0.0

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