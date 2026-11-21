import random
from datetime import date, timedelta

# Cada artigo define:
# - preco_ref: (min, max) em €/kg, €/L ou €/unidade (consoante tipo_medida)
# - formatos: lista de tuplos (etiqueta_formato, peso_ou_volume_kg_L)
CATALOGO_ESTRUTURADO = {
    "carne": {
        "variantes": ["Nacional", "Bio", "Seleção", "Embalado", "do Campo", "Reserva", "Sem Osso"],
        "artigos": [
            {"nome": "Bife de Vazia", "preco_ref": (16.50, 24.90), "formatos": [("250g", 0.25), ("400g", 0.40), ("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Peito de Frango", "preco_ref": (6.90, 9.50), "formatos": [("400g", 0.40), ("600g", 0.60), ("1kg", 1.00)]},
            {"nome": "Frango Inteiro", "preco_ref": (3.80, 5.20), "formatos": [("1.2kg", 1.20), ("1.5kg", 1.50), ("1.8kg", 1.80)]},
            {"nome": "Lombo de Porco", "preco_ref": (6.50, 8.90), "formatos": [("500g", 0.50), ("800g", 0.80), ("1kg", 1.00)]},
            {"nome": "Carne Picada de Novilho", "preco_ref": (8.50, 11.90), "formatos": [("400g", 0.40), ("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Costeletas de Porco", "preco_ref": (5.90, 7.90), "formatos": [("500g", 0.50), ("750g", 0.75), ("1kg", 1.00)]},
            {"nome": "Bifes de Peru", "preco_ref": (7.50, 10.20), "formatos": [("400g", 0.40), ("600g", 0.60), ("1kg", 1.00)]},
            {"nome": "Hambúrguer de Novilho", "preco_ref": (9.50, 13.50), "formatos": [("Pack 2 (240g)", 0.24), ("Pack 4 (480g)", 0.48)]},
            {"nome": "Alheira de Mirandela", "preco_ref": (7.00, 10.50), "formatos": [("Unidade (220g)", 0.22), ("Pack 2 (440g)", 0.44)]},
            {"nome": "Entrecosto de Porco", "preco_ref": (5.50, 7.80), "formatos": [("600g", 0.60), ("1kg", 1.00), ("1.5kg", 1.50)]},
        ]
    },
    "pescado": {
        "variantes": ["Atlântico", "Costa Portuguesa", "Aquacultura", "Sem Pele", "Limpo", "Seleção", "de Mar"],
        "artigos": [
            {"nome": "Salmão Fresco", "preco_ref": (16.90, 22.90), "formatos": [("Posta 200g", 0.20), ("Lombo 400g", 0.40), ("600g", 0.60), ("1kg", 1.00)]},
            {"nome": "Postas de Bacalhau Fresco", "preco_ref": (12.90, 17.50), "formatos": [("400g", 0.40), ("600g", 0.60), ("1kg", 1.00)]},
            {"nome": "Dourada", "preco_ref": (8.50, 12.90), "formatos": [("400g", 0.40), ("600g", 0.60), ("1kg", 1.00)]},
            {"nome": "Robalo Fresco", "preco_ref": (9.90, 15.90), "formatos": [("400g", 0.40), ("600g", 0.60), ("1kg", 1.00)]},
            {"nome": "Filetes de Pescada", "preco_ref": (9.50, 13.90), "formatos": [("300g", 0.30), ("500g", 0.50), ("800g", 0.80)]},
            {"nome": "Miolo de Camarão", "preco_ref": (13.90, 19.90), "formatos": [("250g", 0.25), ("400g", 0.40), ("800g", 0.80)]},
            {"nome": "Lulas", "preco_ref": (11.50, 15.90), "formatos": [("300g", 0.30), ("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Sardinha Fresca", "preco_ref": (4.50, 7.50), "formatos": [("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Polvo", "preco_ref": (14.50, 19.50), "formatos": [("500g", 0.50), ("1kg", 1.00), ("1.5kg", 1.50)]},
            {"nome": "Tranche de Corvina", "preco_ref": (11.90, 16.50), "formatos": [("300g", 0.30), ("500g", 0.50), ("800g", 0.80)]},
            {"nome": "Peixe-Espada Preto", "preco_ref": (10.50, 14.90), "formatos": [("300g", 0.30), ("500g", 0.50), ("800g", 0.80)]},
            {"nome": "Atum Fresco", "preco_ref": (15.90, 21.90), "formatos": [("250g", 0.25), ("400g", 0.40), ("800g", 0.80)]},
            {"nome": "Linguado Fresco", "preco_ref": (16.50, 22.50), "formatos": [("300g", 0.30), ("500g", 0.50)]},
            {"nome": "Truta", "preco_ref": (6.90, 9.90), "formatos": [("400g", 0.40), ("800g", 0.80)]},
        ]
    },
    "charcutaria": {
        "variantes": ["Fatiado", "Finíssimo", "Tradicional", "Fumado", "Seleção", "Sem Glúten", "Artesanal"],
        "artigos": [
            {"nome": "Fiambre de Frango", "preco_ref": (6.50, 9.20), "formatos": [("150g", 0.15), ("200g", 0.20), ("400g", 0.40)]},
            {"nome": "Fiambre da Perna Extra", "preco_ref": (8.50, 12.50), "formatos": [("150g", 0.15), ("200g", 0.20), ("400g", 0.40)]},
            {"nome": "Fiambre de Peru", "preco_ref": (7.50, 10.80), "formatos": [("150g", 0.15), ("200g", 0.20), ("400g", 0.40)]},
            {"nome": "Presunto Curado", "preco_ref": (18.00, 29.50), "formatos": [("100g", 0.10), ("150g", 0.15), ("250g", 0.25)]},
            {"nome": "Mortadela com Azeitonas", "preco_ref": (6.90, 9.90), "formatos": [("150g", 0.15), ("250g", 0.25)]},
            {"nome": "Chourição", "preco_ref": (9.50, 14.50), "formatos": [("100g", 0.10), ("200g", 0.20), ("Peça 350g", 0.35)]},
            {"nome": "Paio York", "preco_ref": (10.50, 15.50), "formatos": [("100g", 0.10), ("200g", 0.20), ("Peça 400g", 0.40)]},
            {"nome": "Salpicão", "preco_ref": (14.00, 21.00), "formatos": [("100g", 0.10), ("Peça 300g", 0.30)]},
            {"nome": "Bacon Fumado", "preco_ref": (8.90, 13.50), "formatos": [("200g", 0.20), ("Pack 2 (300g)", 0.30), ("500g", 0.50)]},
            {"nome": "Chouriço de Carne", "preco_ref": (8.50, 12.90), "formatos": [("Unidade (220g)", 0.22), ("Pack 2 (440g)", 0.44)]},
        ]
    },
    "laticinios": {
        "variantes": ["Magro", "Sem Lactose", "Bio", "Artesanal", "Tradicional", "Proteico", "Natural"],
        "artigos": [
            {"nome": "Iogurte Líquido", "preco_ref": (2.20, 3.60), "formatos": [("Pack 4 (640ml)", 0.64), ("Garrafa 1L", 1.00)]},
            {"nome": "Iogurte Aroma de Morango", "preco_ref": (2.50, 4.20), "formatos": [("Pack 4 (500g)", 0.50), ("Pack 8 (1kg)", 1.00)]},
            {"nome": "Iogurte Grego", "preco_ref": (3.80, 5.80), "formatos": [("Pack 4 (500g)", 0.50), ("Balde 1kg", 1.00)]},
            {"nome": "Queijo Gouda Fatiado", "preco_ref": (8.50, 12.50), "formatos": [("200g", 0.20), ("400g", 0.40)]},
            {"nome": "Queijo Flamengo Bola", "preco_ref": (7.90, 11.50), "formatos": [("250g", 0.25), ("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Leite Meio-Gordo", "preco_ref": (0.85, 1.35), "formatos": [("Pacote 1L", 1.00), ("Pack 6 (6L)", 6.00)]},
            {"nome": "Manteiga com Sal", "preco_ref": (8.00, 11.90), "formatos": [("250g", 0.25), ("500g", 0.50)]},
            {"nome": "Requeijão de Seia", "preco_ref": (7.50, 11.00), "formatos": [("200g", 0.20), ("400g", 0.40)]},
            {"nome": "Queijo Fresco", "preco_ref": (6.50, 9.90), "formatos": [("Pack 2 (160g)", 0.16), ("Pack 4 (320g)", 0.32)]},
            {"nome": "Nata Culinária", "preco_ref": (3.50, 5.50), "formatos": [("200ml", 0.20), ("Pack 3 (600ml)", 0.60)]},
        ]
    },
    "fruta": {
        "variantes": ["IGP", "Bio", "Categoria I", "Nacional", "Pronto a Comer", "Seleção", "do Pomar"],
        "artigos": [
            {"nome": "Morangos", "preco_ref": (5.50, 8.90), "formatos": [("Cuvete 250g", 0.25), ("Cuvete 500g", 0.50)]},
            {"nome": "Mirtilos", "preco_ref": (11.00, 16.50), "formatos": [("Cuvete 125g", 0.125), ("Cuvete 250g", 0.25)]},
            {"nome": "Framboesas", "preco_ref": (13.00, 18.90), "formatos": [("Cuvete 125g", 0.125), ("Cuvete 250g", 0.25)]},
            {"nome": "Maçã Gala", "preco_ref": (1.69, 2.79), "formatos": [("Saco 1kg", 1.00), ("Saco 1.5kg", 1.50), ("Avulso 1kg", 1.00)]},
            {"nome": "Banana da Madeira", "preco_ref": (1.59, 2.49), "formatos": [("Cacho 1kg", 1.00), ("Cacho 1.5kg", 1.50)]},
            {"nome": "Laranja do Algarve", "preco_ref": (1.39, 2.29), "formatos": [("Saco 1.5kg", 1.50), ("Saco 3kg", 3.00), ("Avulso 1kg", 1.00)]},
            {"nome": "Pêra Rocha", "preco_ref": (1.89, 2.99), "formatos": [("Saco 1kg", 1.00), ("Saco 1.5kg", 1.50), ("Avulso 1kg", 1.00)]},
            {"nome": "Kiwi Verde", "preco_ref": (2.99, 4.49), "formatos": [("Cuvete 500g", 0.50), ("Saco 1kg", 1.00)]},
            {"nome": "Manga Maturada", "preco_ref": (2.80, 4.50), "formatos": [("Unidade (450g)", 0.45), ("Pack 2 (900g)", 0.90)]},
            {"nome": "Uva Branca Sem Grainha", "preco_ref": (3.20, 4.99), "formatos": [("Cuvete 500g", 0.50), ("Cuvete 750g", 0.75)]},
            {"nome": "Pêssego Amarelo", "preco_ref": (2.49, 3.89), "formatos": [("Cuvete 500g", 0.50), ("Saco 1kg", 1.00)]},
            {"nome": "Nectarina", "preco_ref": (2.59, 3.99), "formatos": [("Cuvete 500g", 0.50), ("Saco 1kg", 1.00)]},
            {"nome": "Tangerina", "preco_ref": (1.79, 2.89), "formatos": [("Saco 1kg", 1.00), ("Saco 1.5kg", 1.50)]},
            {"nome": "Abacaxi dos Açores", "preco_ref": (2.20, 3.50), "formatos": [("Unidade (1.1kg)", 1.10), ("Unidade (1.4kg)", 1.40)]},
        ]
    },
    "padaria": {
        "variantes": ["Forno de Lenha", "Artesanal", "Integral", "Massa Mãe", "Tradicional", "Cereais", "Sem Glúten"],
        "artigos": [
            {"nome": "Pão de Centeio", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Bola Mistura", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Pão da Avó", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Pão de Beterraba", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Pão Bijou", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Carcaça Portuguesa", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Chapata de Cereais", "preco_ref": (3.20, 4.80), "formatos": [("Unidade (80g)", 0.08), ("400g", 0.40), ("600g", 0.60), ("800g", 0.80)]},
            {"nome": "Pão de Mafra", "preco_ref": (2.90, 4.20), "formatos": [("400g", 0.40), ("750g", 0.75)]},
            {"nome": "Broa de Milho", "preco_ref": (2.80, 4.10), "formatos": [("500g", 0.50), ("800g", 0.80)]},
            {"nome": "Papo-Seco", "preco_ref": (2.40, 3.30), "formatos": [("Unidade (60g)", 0.06), ("Pack 4 (240g)", 0.24), ("Pack 6 (360g)", 0.36)]},
            {"nome": "Croissant Brioche", "preco_ref": (8.50, 12.00), "formatos": [("Unidade (80g)", 0.08), ("Pack 4 (320g)", 0.32)]},
            {"nome": "Croissant Folhado", "preco_ref": (9.00, 12.50), "formatos": [("Unidade (75g)", 0.075), ("Pack 4 (300g)", 0.30)]},
            {"nome": "Croissant com Chocolate", "preco_ref": (10.50, 14.00), "formatos": [("Unidade (90g)", 0.09), ("Pack 4 (360g)", 0.36)]},
            {"nome": "Baguete Rústica", "preco_ref": (3.20, 4.50), "formatos": [("Unidade (250g)", 0.25), ("Pack 2 (500g)", 0.50)]},
            {"nome": "Pão com Chouriço", "preco_ref": (8.50, 11.50), "formatos": [("Unidade (160g)", 0.16), ("Pack 2 (320g)", 0.32)]},
            {"nome": "Regueifa", "preco_ref": (3.50, 4.90), "formatos": [("500g", 0.50), ("750g", 0.75)]},
        ]
    },
    "mercearia": {
        "variantes": ["DOP", "Bio", "Seleção", "Nacional"],
        "artigos": [
            {"nome": "Azeite Virgem Extra", "preco_ref": (8.50, 13.50), "formatos": [("Garrafa 500ml", 0.50), ("Garrafa 750ml", 0.75), ("Garrafão 3L", 3.00)]},
            {"nome": "Polpa de Tomate", "preco_ref": (1.80, 2.90), "formatos": [("Pacote 500ml", 0.50), ("Frasco 700ml", 0.70), ("Pack 3 (630ml)", 0.63)]},
            {"nome": "Arroz Carolino", "preco_ref": (1.39, 2.29), "formatos": [("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Massa Esparguete", "preco_ref": (1.49, 2.59), "formatos": [("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Grão-de-Bico Cozido", "preco_ref": (1.60, 2.60), "formatos": [("Frasco 540g", 0.54), ("Lata 800g", 0.80)]},
            {"nome": "Feijão Preto Cozido", "preco_ref": (1.60, 2.60), "formatos": [("Frasco 540g", 0.54), ("Lata 800g", 0.80)]},
            {"nome": "Atum em Posta", "preco_ref": (9.50, 14.50), "formatos": [("Lata 120g", 0.12), ("Pack 3 (360g)", 0.36)]},
            {"nome": "Bolacha Maria", "preco_ref": (2.20, 3.60), "formatos": [("200g", 0.20), ("400g", 0.40), ("800g", 0.80)]},
            {"nome": "Aveia em Flocos", "preco_ref": (2.40, 3.90), "formatos": [("500g", 0.50), ("1kg", 1.00)]},
            {"nome": "Café Torrado Moído", "preco_ref": (9.50, 15.50), "formatos": [("250g", 0.25), ("500g", 0.50)]},
            {"nome": "Batata Branca", "preco_ref": (0.99, 1.59), "formatos": [("Saco 1.5kg", 1.50), ("Saco 3kg", 3.00), ("Saco 5kg", 5.00)]},
            {"nome": "Batata Doce", "preco_ref": (1.49, 2.39), "formatos": [("Saco 1kg", 1.00), ("Saco 1.5kg", 1.50)]},
            {"nome": "Couve-Flor", "preco_ref": (1.69, 2.59), "formatos": [("Unidade (800g)", 0.80), ("Unidade (1.2kg)", 1.20)]},
        ]
    }
}


def gerar_inventario_dinamico(total_produtos: int = 1000, seed: int = 42) -> list[dict]:
    """
    Gera `total_produtos` únicos com coerência dimensional (peso/volume, preço unitário
    e stock total em kg/L) e datas de validade dinâmicas entre today()+1 e today()+60.
    """
    rng = random.Random(seed)
    hoje = date.today()
    inventario = []
    nomes_usados = set()

    # Pré-gerar todas as combinações válidas possíveis antes de amostrar
    combinacoes_validas = []
    for cat, dados_cat in CATALOGO_ESTRUTURADO.items():
        for artigo in dados_cat["artigos"]:
            for variante in dados_cat["variantes"]:
                for formato_label, peso_unid in artigo["formatos"]:
                    combinacoes_validas.append((cat, artigo, variante, formato_label, peso_unid))

    rng.shuffle(combinacoes_validas)

    idx = 0
    ciclo_lote = 1
    while len(inventario) < total_produtos:
        if idx >= len(combinacoes_validas):
            idx = 0
            ciclo_lote += 1
            rng.shuffle(combinacoes_validas)

        cat, artigo, variante, formato_label, peso_unid = combinacoes_validas[idx]
        idx += 1

        if ciclo_lote == 1:
            nome_completo = f"{artigo['nome']} {variante} ({formato_label})"
        else:
            nome_completo = f"{artigo['nome']} {variante} ({formato_label}) - Lote {ciclo_lote}"

        if nome_completo in nomes_usados:
            continue
        nomes_usados.add(nome_completo)

        # Preço proporcional ao peso/volume da embalagem (arredondado para psicologia de retalho .x9 / .x5 / .x0)
        preco_base_ref = rng.uniform(*artigo["preco_ref"])
        preco_calculado = preco_base_ref * peso_unid
        preco_venda = max(0.19, round(preco_calculado, 2))

        # Stock em unidades coerente com o tamanho da embalagem, convertido para kg/L totais
        unidades_stock = rng.randint(15, 120) if peso_unid < 0.5 else rng.randint(8, 50)
        quantidade_kg = round(unidades_stock * peso_unid, 2)

        # Velocidade diária de escoamento proporcional ao stock disponível
        unidades_vendidas_dia = max(1, int(unidades_stock * rng.uniform(0.15, 0.45)))
        vendas_diarias_kg = round(unidades_vendidas_dia * peso_unid, 2)

        # ~20% dos lotes em janela crítica (1 a 3 dias), ~80% distribuídos até 60 dias
        dias_validade = rng.randint(1, 3) if rng.random() < 0.20 else rng.randint(4, 60)
        data_validade = hoje + timedelta(days=dias_validade)
        data_gs1 = data_validade.strftime("%y%m%d")

        num_prod = len(inventario) + 1
        ean13 = f"560{rng.randint(1000000000, 9999999999)}"
        codigo_2d = f"01|{ean13}|17|{data_gs1}|10|LOTE{num_prod:04d}"

        inventario.append({
            "id": f"PROD-{num_prod:04d}",
            "nome": nome_completo,
            "categoria": cat,
            "formato": formato_label,
            "peso_unitario_kg": peso_unid,
            "unidades_stock": unidades_stock,
            "preco_venda": preco_venda,
            "data_validade": data_validade.strftime("%Y-%m-%d"),
            "dias_para_validade": dias_validade,
            "quantidade_kg": quantidade_kg,
            "historico_vendas_diarias": vendas_diarias_kg,
            "codigo_2d": codigo_2d
        })

    return inventario


INVENTARIO_MOCK = gerar_inventario_dinamico(1000)