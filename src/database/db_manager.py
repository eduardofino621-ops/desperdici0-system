from src.csp.constraints import eh_padaria_elegivel_racao
import re
import random
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta

SEED_FIXA = 43

# ==============================================================================
# CATÁLOGO CURADO DE ARTIGOS REAIS DE RETALHO (SEM COMBINAÇÕES ABSURDAS)
# Cada entrada define:
#   (nome_base, marca_real, [(rotulo_formato, unidade_medida, conteudo_liquido_kg_L, preco_embalagem_eur), ...])
# ==============================================================================
CATALOGO_CURADO = {
    "carne": {
        "un_ref": "kg", "margem": 0.05, "descarte": 0.75, "elasticidade": 1.55, "conservacao": "refrigerado_0_4C",
        "artigos": [
            ("Bife de Vazia Maturado", "Talho Seleção", [("Granel 1kg", "kg", 1.00, 18.99), ("Cuvete 400g", "un", 0.40, 7.89), ("Cuvete 800g", "un", 0.80, 15.29)]),
            ("Peito de Frango", "Lusiaves", [("Cuvete 450g", "un", 0.45, 3.69), ("Cuvete 900g", "un", 0.90, 6.99), ("Pack Familiar 1,5kg", "pack", 1.50, 11.29)]),
            ("Frango Inteiro do Campo", "Quinta da Torre", [("Unidade 1,3kg", "un", 1.30, 5.49), ("Unidade 1,6kg", "un", 1.60, 6.69)]),
            ("Lombo de Porco", "Monte Alentejano", [("Peça 600g", "un", 0.60, 4.79), ("Peça 1kg", "kg", 1.00, 7.69)]),
            ("Carne Picada de Novilho", "Talho Seleção", [("Cuvete 400g", "un", 0.40, 4.19), ("Cuvete 800g", "un", 0.80, 7.99)]),
            ("Costeletas de Borrego", "Origem Nacional", [("Cuvete 500g", "un", 0.50, 8.49), ("Cuvete 800g", "un", 0.80, 13.29)]),
            ("Bifes de Peru", "Valouro", [("Cuvete 400g", "un", 0.40, 3.49), ("Cuvete 800g", "un", 0.80, 6.69)]),
            ("Hambúrguer de Novilho Angus", "Talho Seleção", [("Pack 2x150g", "pack", 0.30, 3.99), ("Pack 4x150g", "pack", 0.60, 7.49)]),
            ("Entrecosto de Porco", "Beira Tradicional", [("Cuvete 700g", "un", 0.70, 4.89), ("Pack 1,2kg", "pack", 1.20, 7.99)]),
            ("Picanha Maturada", "Açores", [("Peça 900g", "un", 0.90, 16.99), ("Peça 1,3kg", "un", 1.30, 23.99)]),
            ("Pernas de Frango", "Lusiaves", [("Cuvete 600g", "un", 0.60, 2.79), ("Pack Familiar 1,2kg", "pack", 1.20, 5.19)]),
            ("Febras de Porco", "Monte Alentejano", [("Cuvete 500g", "un", 0.50, 3.29), ("Cuvete 1kg", "kg", 1.00, 6.19)]),
        ]
    },
    "charcutaria": {
        "un_ref": "kg", "margem": 0.08, "descarte": 0.40, "elasticidade": 1.35, "conservacao": "refrigerado_0_5C",
        "artigos": [
            ("Fiambre da Perna Extra Fatiado", "Nobre", [("Cuvete 150g", "un", 0.15, 1.89), ("Cuvete 300g", "un", 0.30, 3.49)]),
            ("Fiambre de Peru Finíssimo", "Campofrio", [("Cuvete 150g", "un", 0.15, 1.79), ("Cuvete 250g", "un", 0.25, 2.79)]),
            ("Fiambre de Frango", "Izidoro", [("Cuvete 150g", "un", 0.15, 1.49), ("Cuvete 300g", "un", 0.30, 2.79)]),
            ("Presunto Curado Fatiado", "Serrano Reserva", [("Cuvete 100g", "un", 0.10, 2.69), ("Cuvete 200g", "un", 0.20, 4.99)]),
            ("Mortadela com Azeitonas", "Nobre", [("Cuvete 150g", "un", 0.15, 1.39), ("Cuvete 250g", "un", 0.25, 2.19)]),
            ("Chourição Extra Fatiado", "Damatta", [("Cuvete 100g", "un", 0.10, 1.59), ("Peça 350g", "un", 0.35, 4.69)]),
            ("Paio York Fatiado", "Nobre", [("Cuvete 120g", "un", 0.12, 1.89), ("Peça 400g", "un", 0.40, 5.49)]),
            ("Alheira de Mirandela IGP", "Eurofumeiro", [("Unidade 220g", "un", 0.22, 2.19), ("Pack 2x220g", "pack", 0.44, 3.99)]),
            ("Bacon Fumado em Tiras", "Izidoro", [("Cuvete 200g", "un", 0.20, 2.39), ("Pack 2x150g", "pack", 0.30, 3.39)]),
            ("Salpicão Tradicional Fatiado", "Damatta", [("Cuvete 100g", "un", 0.10, 1.99), ("Peça 250g", "un", 0.25, 4.49)]),
            ("Chouriço Corrente", "Nobre", [("Unidade 200g", "un", 0.20, 1.79), ("Pack 2x200g", "pack", 0.40, 3.29)]),
            ("Salsichas Frescas de Porco", "Izidoro", [("Cuvete 400g", "un", 0.40, 2.49), ("Pack 800g", "pack", 0.80, 4.69)]),
        ]
    },
    "pescado": {
        "un_ref": "kg", "margem": 0.05, "descarte": 0.85, "elasticidade": 1.65, "conservacao": "refrigerado_0_2C",
        "artigos": [
            ("Salmão Fresco Atlântico", "Mar Atlântico", [("Posta 1kg", "kg", 1.00, 18.50), ("Lombo 400g", "un", 0.40, 7.99), ("Pack 2 Postas 500g", "pack", 0.50, 9.69)]),
            ("Dourada Fresca Eviscerada", "Costa Portuguesa", [("Granel 1kg", "kg", 1.00, 9.99), ("Cuvete 600g", "un", 0.60, 6.29)]),
            ("Robalo de Mar Fresco", "Pesca do Dia", [("Granel 1kg", "kg", 1.00, 12.49), ("Cuvete 600g", "un", 0.60, 7.79)]),
            ("Filetes de Pescada Frescos", "Pescanova", [("Cuvete 350g", "un", 0.35, 4.29), ("Cuvete 700g", "un", 0.70, 7.99)]),
            ("Miolo de Camarão Cozido", "Mar Atlântico", [("Cuvete 250g", "un", 0.25, 4.49), ("Cuvete 500g", "un", 0.50, 8.49)]),
            ("Polvo Limpo Fresco", "Norte Mar", [("Cuvete 600g", "un", 0.60, 9.99), ("Peça 1,2kg", "un", 1.20, 18.99)]),
            ("Sardinha Fresca", "Costa Portuguesa", [("Cuvete 500g", "un", 0.50, 2.99), ("Granel 1kg", "kg", 1.00, 5.49)]),
            ("Lulas Limpas Frescas", "Ria Fresca", [("Cuvete 400g", "un", 0.40, 5.29), ("Cuvete 800g", "un", 0.80, 9.99)]),
            ("Tranche de Corvina", "Mar Atlântico", [("Cuvete 350g", "un", 0.35, 5.19), ("Cuvete 700g", "un", 0.70, 9.89)]),
            ("Bacalhau Demolhado Postas", "Riberalves", [("Cuvete 600g", "un", 0.60, 8.99), ("Pack 1kg", "kg", 1.00, 14.49)]),
            ("Carapau Fresco Médio", "Costa Portuguesa", [("Cuvete 500g", "un", 0.50, 2.49), ("Granel 1kg", "kg", 1.00, 4.59)]),
            ("Lombos de Atum Fresco", "Mar Atlântico", [("Cuvete 300g", "un", 0.30, 5.99), ("Cuvete 600g", "un", 0.60, 11.49)]),
        ]
    },
    "laticinios": {
        "un_ref": "kg", "margem": 0.06, "descarte": 0.30, "elasticidade": 1.25, "conservacao": "refrigerado_2_6C",
        "artigos": [
            ("Iogurte Grego Natural", "Danone Oikos", [("Pack 4x115g", "pack", 0.46, 2.49), ("Balde 1kg", "un", 1.00, 4.39)]),
            ("Iogurte Líquido Morango", "Mimosa", [("Pack 4x160g", "pack", 0.64, 2.19), ("Pack 6x160g", "pack", 0.96, 3.09)]),
            ("Queijo Flamengo Bola", "Terra Nostra", [("Meia Bola 500g", "un", 0.50, 4.69), ("Bola 1kg", "un", 1.00, 8.79)]),
            ("Leite Meio-Gordo UHT", "Agros", [("Pacote 1L", "un", 1.00, 0.95), ("Pack 6x1L", "pack", 6.00, 5.39)]),
            ("Manteiga com Sal", "Mimosa", [("Embalagem 250g", "un", 0.25, 2.39), ("Embalagem 500g", "un", 0.50, 4.49)]),
            ("Requeijão de Ovelha", "Seia DOP", [("Unidade 200g", "un", 0.20, 1.99), ("Pack 2x200g", "pack", 0.40, 3.69)]),
            ("Nata para Culinária", "Parmalat", [("Pacote 200ml", "un", 0.20, 0.99), ("Pack 3x200ml", "pack", 0.60, 2.69)]),
            ("Queijo Fresco Tradicional", "Saloio", [("Pack 2x85g", "pack", 0.17, 1.49), ("Pack 4x85g", "pack", 0.34, 2.69)]),
            ("Kefir Natural", "Nestlé", [("Garrafa 500g", "un", 0.50, 1.79), ("Garrafa 1kg", "un", 1.00, 3.19)]),
            ("Queijo Mozzarella Ralado", "Galbani", [("Embalagem 200g", "un", 0.20, 2.19), ("Pack 2x200g", "pack", 0.40, 3.99)]),
            ("Queijo Curado Amanteigado", "Azeitão DOP", [("Unidade 250g", "un", 0.25, 4.79), ("Unidade 500g", "un", 0.50, 8.99)]),
            ("Iogurte Straciatella Proteína", "Lindahls", [("Pack 4x150g", "pack", 0.60, 3.49), ("Balde 500g", "un", 0.50, 2.49)]),
        ]
    },
    "padaria": {
        "un_ref": "kg", "margem": 0.10, "descarte": 0.15, "elasticidade": 1.80, "conservacao": "ambiente",
        "artigos": [
            ("Pão de Centeio", "Forno do Dia", [("Unidade Avulso (80g)", "un", 0.08, 0.32), ("Unidade 400g", "un", 0.40, 1.59), ("Unidade 600g", "un", 0.60, 2.29), ("Fatiado 800g", "un", 0.80, 2.89)]),
            ("Bola de Mistura", "Padaria Tradicional", [("Unidade Avulso (80g)", "un", 0.08, 0.28), ("Unidade 400g", "un", 0.40, 1.39), ("Unidade 600g", "un", 0.60, 1.99), ("Unidade 800g", "un", 0.80, 2.59)]),
            ("Pão da Avó", "Forno de Lenha", [("Unidade Avulso (80g)", "un", 0.08, 0.35), ("Unidade 400g", "un", 0.40, 1.69), ("Unidade 600g", "un", 0.60, 2.39), ("Unidade 800g", "un", 0.80, 2.99)]),
            ("Pão de Beterraba", "Artesanal", [("Unidade Avulso (80g)", "un", 0.08, 0.38), ("Unidade 400g", "un", 0.40, 1.79), ("Unidade 600g", "un", 0.60, 2.59), ("Unidade 800g", "un", 0.80, 3.29)]),
            ("Pão Bijou", "Padaria Tradicional", [("Unidade Avulso (80g)", "un", 0.08, 0.25), ("Pack 4 (320g)", "pack", 0.32, 0.95), ("Pack 6 (480g)", "pack", 0.48, 1.39)]),
            ("Carcaça Portuguesa", "Forno do Dia", [("Unidade Avulso (80g)", "un", 0.08, 0.24), ("Pack 4 (320g)", "pack", 0.32, 0.92), ("Pack 6 (480g)", "pack", 0.48, 1.35)]),
            ("Chapata de Cereais", "Massa Mãe", [("Unidade Avulso (80g)", "un", 0.08, 0.36), ("Unidade 400g", "un", 0.40, 1.69), ("Unidade 600g", "un", 0.60, 2.49)]),
            ("Pão de Mafra", "Padaria Tradicional", [("Unidade Avulso (90g)", "un", 0.09, 0.32), ("Unidade 400g", "un", 0.40, 1.49), ("Unidade 750g", "un", 0.75, 2.39)]),
            ("Broa de Milho", "Moinho Velho", [("Unidade 500g", "un", 0.50, 1.69), ("Unidade 800g", "un", 0.80, 2.49)]),
            ("Papo-Seco", "Forno do Dia", [("Unidade Avulso (60g)", "un", 0.06, 0.19), ("Pack 4 (240g)", "pack", 0.24, 0.72), ("Pack 6 (360g)", "pack", 0.36, 1.05)]),
            ("Croissant Brioche", "Arte do Pão", [("Unidade Avulso (80g)", "un", 0.08, 0.89), ("Pack 4 (320g)", "pack", 0.32, 3.19)]),
            ("Croissant Folhado", "Arte do Pão", [("Unidade Avulso (75g)", "un", 0.075, 0.95), ("Pack 4 (300g)", "pack", 0.30, 3.39)]),
            ("Croissant com Chocolate", "Arte do Pão", [("Unidade Avulso (90g)", "un", 0.09, 1.15), ("Pack 4 (360g)", "pack", 0.36, 3.99)]),
            ("Baguete Rústica", "Casa do Pão", [("Unidade Avulso (250g)", "un", 0.25, 0.99), ("Pack 2 (500g)", "pack", 0.50, 1.79)]),
            ("Pão com Chouriço", "Forno do Dia", [("Unidade Avulso (160g)", "un", 0.16, 1.69), ("Pack 2 (320g)", "pack", 0.32, 3.09)]),
            ("Regueifa", "Padaria Tradicional", [("Unidade 500g", "un", 0.50, 1.99), ("Unidade 750g", "un", 0.75, 2.89)]),
            ("Pão Alentejano", "Forno de Lenha", [("Unidade 500g", "un", 0.50, 1.89), ("Unidade 800g", "un", 0.80, 2.79)]),
            ("Pão de Água", "Padaria Tradicional", [("Unidade Avulso (90g)", "un", 0.09, 0.34), ("Unidade 400g", "un", 0.40, 1.49), ("Unidade 600g", "un", 0.60, 2.15)]),
            ("Broa de Avintes", "Moinho Velho", [("Unidade 500g", "un", 0.50, 2.19), ("Unidade 800g", "un", 0.80, 3.29)]),
            ("Pão de Sementes", "Massa Mãe", [("Unidade Avulso (80g)", "un", 0.08, 0.39), ("Unidade 400g", "un", 0.40, 1.89), ("Unidade 600g", "un", 0.60, 2.69)]),
            ("Bolo do Caco", "Artesanal", [("Unidade Avulso (160g)", "un", 0.16, 0.95), ("Pack 2 (320g)", "pack", 0.32, 1.79), ("Pack 4 (640g)", "pack", 0.64, 3.39)]),
            ("Pão Integral", "Forno do Dia", [("Unidade Avulso (80g)", "un", 0.08, 0.34), ("Unidade 400g", "un", 0.40, 1.65), ("Unidade 600g", "un", 0.60, 2.35)]),
            ("Pão de Centeio com Nozes", "Massa Mãe", [("Unidade Avulso (90g)", "un", 0.09, 0.45), ("Unidade 400g", "un", 0.40, 2.09), ("Unidade 600g", "un", 0.60, 2.99)]),
            ("Pão de Leite", "Arte do Pão", [("Unidade Avulso (65g)", "un", 0.065, 0.35), ("Pack 4 (260g)", "pack", 0.26, 1.29), ("Pack 6 (390g)", "pack", 0.39, 1.89)]),
            ("Pão de Deus", "Arte do Pão", [("Unidade Avulso (110g)", "un", 0.11, 1.09), ("Pack 2 (220g)", "pack", 0.22, 1.99), ("Pack 4 (440g)", "pack", 0.44, 3.79)]),
        ]
    },
    "fruta": {
        "un_ref": "kg", "margem": 0.05, "descarte": 0.30, "elasticidade": 1.85, "conservacao": "refrigerado_2_6C",
        "artigos": [
            ("Morangos Frescos", "Pomar Oeste", [("Cuvete 250g", "un", 0.25, 1.99), ("Cuvete 500g", "un", 0.50, 3.49)]),
            ("Maçã Gala de Alcobaça IGP", "Coop Alcobaça", [("Saco 1kg", "pack", 1.00, 1.99), ("Saco 1,5kg", "pack", 1.50, 2.79)]),
            ("Banana da Madeira", "Gesba", [("Cacho 1kg", "kg", 1.00, 1.89), ("Cacho 1,5kg", "kg", 1.50, 2.69)]),
            ("Pêra Rocha do Oeste DOP", "Pomar Oeste", [("Saco 1kg", "pack", 1.00, 2.19), ("Saco 1,5kg", "pack", 1.50, 3.09)]),
            ("Laranja do Algarve IGP", "Frutas do Sol", [("Saco 1,5kg", "pack", 1.50, 2.29), ("Saco 3kg", "pack", 3.00, 4.19)]),
            ("Mirtilos Frescos", "Quinta Bio", [("Cuvete 125g", "un", 0.125, 1.79), ("Cuvete 250g", "un", 0.25, 3.19)]),
            ("Kiwi Verde Nacional", "Vale Verde", [("Cuvete 500g", "un", 0.50, 1.89), ("Saco 1kg", "pack", 1.00, 3.39)]),
            ("Uva Branca sem Grainha", "Horta Fresca", [("Cuvete 500g", "un", 0.50, 2.19), ("Cuvete 750g", "un", 0.75, 2.99)]),
            ("Manga Maturada", "Frutas do Sol", [("Unidade 450g", "un", 0.45, 1.69), ("Pack 2x450g", "pack", 0.90, 3.19)]),
            ("Framboesas Frescas", "Quinta Bio", [("Cuvete 125g", "un", 0.125, 2.19), ("Cuvete 250g", "un", 0.25, 3.89)]),
            ("Abacate Hass Maturado", "Frutas do Sol", [("Pack 2 un (400g)", "pack", 0.40, 2.49), ("Pack 4 un (800g)", "pack", 0.80, 4.59)]),
            ("Tangerina do Algarve", "Frutas do Sol", [("Saco 1kg", "pack", 1.00, 1.99), ("Saco 2kg", "pack", 2.00, 3.69)]),
        ]
    },
    "mercearia": {
        "un_ref": "kg", "margem": 0.08, "descarte": 0.20, "elasticidade": 1.15, "conservacao": "ambiente",
        "artigos": [
            ("Azeite Virgem Extra", "Oliveira da Serra", [("Garrafa 0,75L", "un", 0.75, 7.49), ("Garrafa 500ml", "un", 0.50, 5.29)]),
            ("Azeite Clássico", "Gallo", [("Garrafa 750ml", "un", 0.75, 6.99), ("Garrafão 3L", "un", 3.00, 24.99)]),
            ("Arroz Carolino", "Cigala", [("Pacote 1kg", "un", 1.00, 1.59), ("Pack 2x1kg", "pack", 2.00, 2.99)]),
            ("Arroz Agulha", "Saludães", [("Pacote 1kg", "un", 1.00, 1.49), ("Pack 2x1kg", "pack", 2.00, 2.79)]),
            ("Massa Esparguete", "Nacional", [("Pacote 500g", "un", 0.50, 1.09), ("Pacote 1kg", "un", 1.00, 1.89)]),
            ("Bolacha Maria", "Triunfo", [("Pacote 200g", "un", 0.20, 0.99), ("Pack Familiar 800g", "pack", 0.80, 2.89)]),
            ("Bolacha Água e Sal", "Cuétara", [("Pacote 250g", "un", 0.25, 1.29), ("Pack 500g", "pack", 0.50, 2.29)]),
            ("Atum em Posta em Azeite", "Bom Petisco", [("Lata 120g", "un", 0.12, 1.69), ("Pack 3x120g", "pack", 0.36, 4.59)]),
            ("Café Torrado Moído", "Delta", [("Pacote 250g", "un", 0.25, 3.29), ("Pack 2x250g", "pack", 0.50, 6.19)]),
            ("Grão-de-Bico Cozido", "Compal", [("Frasco 540g", "un", 0.54, 1.39), ("Lata 840g", "un", 0.84, 1.79)]),
            ("Polpa de Tomate", "Guloso", [("Pacote 500ml", "un", 0.50, 1.09), ("Frasco 700ml", "un", 0.70, 1.49)]),
            ("Aveia Integral em Flocos", "Quaker", [("Pacote 500g", "un", 0.50, 1.79), ("Pacote 1kg", "un", 1.00, 3.19)]),
            ("Feijão Preto Cozido", "Compal", [("Frasco 540g", "un", 0.54, 1.39), ("Lata 840g", "un", 0.84, 1.79)]),
        ]
    },
    "bebidas": {
        "un_ref": "L", "margem": 0.08, "descarte": 0.15, "elasticidade": 1.20, "conservacao": "ambiente",
        "artigos": [
            ("Néctar Pêssego Clássico", "Compal", [("Pacote 1L", "un", 1.00, 1.49), ("Pack 4x200ml", "pack", 0.80, 1.79)]),
            ("Água Mineral Natural", "Luso", [("Garrafa 1,5L", "un", 1.50, 0.69), ("Pack 6x1,5L", "pack", 9.00, 3.79)]),
            ("Água Mineral Natural", "Vitalis", [("Garrafa 50cl", "un", 0.50, 0.45), ("Pack 6x1,5L", "pack", 9.00, 3.59)]),
            ("Bebida de Aveia Barista", "Alpro", [("Pacote 1L", "un", 1.00, 2.29), ("Pack 3x1L", "pack", 3.00, 6.39)]),
            ("Bebida de Amêndoa sem Açúcar", "Alpro", [("Pacote 1L", "un", 1.00, 2.19), ("Pack 3x1L", "pack", 3.00, 6.09)]),
            ("Água com Gás Limão", "Frize", [("Garrafa 25cl", "un", 0.25, 0.85), ("Pack 4x25cl", "pack", 1.00, 2.99)]),
            ("Sumo de Maçã 100%", "Compal", [("Pacote 1L", "un", 1.00, 1.69), ("Pack 3x200ml", "pack", 0.60, 1.49)]),
            ("Sumo de Laranja 100%", "Compal", [("Pacote 1L", "un", 1.00, 1.89), ("Pack 3x200ml", "pack", 0.60, 1.59)]),
            ("Chá Gelado Limão", "Lipton", [("Garrafa 1,5L", "un", 1.50, 1.59), ("Pack 4x1,5L", "pack", 6.00, 5.79)]),
            ("Água com Gás Natural", "Pedras Salgadas", [("Pack 4x25cl", "pack", 1.00, 2.89), ("Pack 6x25cl", "pack", 1.50, 4.19)]),
            ("Bebida de Soja Natural", "Alpro", [("Pacote 1L", "un", 1.00, 1.89), ("Pack 3x1L", "pack", 3.00, 5.29)]),
        ]
    },
}


def _calcular_digito_controlo_ean13(base_12: str) -> str:
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base_12))
    resto = soma % 10
    return "0" if resto == 0 else str(10 - resto)


def _gerar_gtin13(indice: int) -> str:
    base_12 = f"560{indice:09d}"
    return base_12 + _calcular_digito_controlo_ean13(base_12)


def _calcular_periodo_semana(data_ref: date) -> str:
    segunda = data_ref - timedelta(days=data_ref.weekday())
    domingo = segunda + timedelta(days=6)
    return f"{segunda.strftime('%d/%m/%Y')} a {domingo.strftime('%d/%m/%Y')}"

def _max_dias_validade_padaria(nome_produto: str) -> int:
    nome_l = nome_produto.lower()
    if "broa" in nome_l or "massa mãe" in nome_l or "chapata" in nome_l:
        return 4
    if any(k in nome_l for k in ["papo-seco", "carcaça", "bijou", "baguete", "croissant", "chouriço", "avulso"]):
        return 2
    return 3


class GestorBaseDadosTemporal:
    """
    Gere o catálogo de 200 artigos reais de supermercado e 1.000 lotes em SQLite,
    com datas de validade dinâmicas relativas à data de execução (date.today()).
    """

    def __init__(self, total_produtos: int = 200, seed: int = SEED_FIXA, db_path: str = "data/desperdicio.db"):
        self.total_produtos = total_produtos
        self.seed = seed
        self.db_path = Path(db_path)
        self._inicializar_sqlite()

    def _conectar(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar_sqlite(self) -> None:
        with self._conectar() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS catalogo_produtos (
                    produto_id TEXT PRIMARY KEY,
                    gtin TEXT UNIQUE NOT NULL,
                    nome TEXT UNIQUE NOT NULL,
                    categoria TEXT NOT NULL,
                    tipo_validade TEXT NOT NULL DEFAULT 'consumir_ate',
                    unidade_medida TEXT NOT NULL,
                    conteudo_liquido REAL NOT NULL,
                    unidade_referencia TEXT NOT NULL,
                    pvp REAL NOT NULL,
                    desconto_campanha REAL NOT NULL,
                    periodo_campanha TEXT,
                    custo_aquisicao REAL NOT NULL,
                    margem_minima_pct REAL NOT NULL,
                    custo_descarte REAL NOT NULL,
                    vendas_medias_diarias REAL NOT NULL,
                    elasticidade_preco REAL NOT NULL,
                    conservacao TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inventario_lotes (
                    lote_id TEXT PRIMARY KEY,
                    produto_id TEXT NOT NULL,
                    quantidade_disponivel REAL NOT NULL,
                    data_entrada TEXT NOT NULL,
                    data_validade TEXT NOT NULL,
                    dias_para_expirar INTEGER NOT NULL,
                    desconto_validade REAL NOT NULL,
                    preco_final_atual REAL NOT NULL,
                    codigo_gs1_raw TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    FOREIGN KEY (produto_id) REFERENCES catalogo_produtos(produto_id)
                );

                CREATE TABLE IF NOT EXISTS telemetria_execucoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    data_operacao TEXT NOT NULL,
                    cenario TEXT NOT NULL,
                    total_lotes INTEGER NOT NULL,
                    lotes_desconto_validade INTEGER NOT NULL,
                    desconto_medio_pct REAL NOT NULL
                );
            """)

            cols = {row["name"] for row in conn.execute("PRAGMA table_info(catalogo_produtos)")}
            if "tipo_validade" not in cols:
                conn.execute(
                    "ALTER TABLE catalogo_produtos ADD COLUMN tipo_validade TEXT NOT NULL DEFAULT 'consumir_ate'"
                )

    def obter_data_referencia(self, dias_avanco_simulado: int = 0) -> date:
        return date.today() + timedelta(days=dias_avanco_simulado)

    def _construir_pool_artigos_reais(self, rng: random.Random) -> list[dict]:
        """
        Constrói exclusivamente artigos com marcas e formatos reais do retalho português.
        Seleciona exatamente 25 produtos de padaria (1 formato por tipo de pão)
        e os formatos das restantes 7 categorias até atingir total_produtos.
        """
        nomes_reservados = {
            "Salmão Fresco Atlântico",
            "Bife de Vazia Maturado",
            "Iogurte Natural (Pack 4)",
            "Azeite Virgem Extra 0,75L",
        }

        pool_padaria = []
        pool_outras = []

        for cat_nome, cfg in CATALOGO_CURADO.items():
            for artigo_nome, marca, formatos in cfg["artigos"]:
                formatos_usar = [rng.choice(formatos)] if cat_nome == "padaria" else formatos
                for rotulo_fmt, unidade, conteudo, pvp in formatos_usar:
                    nome_completo = f"{artigo_nome} {marca} ({rotulo_fmt})"
                    if nome_completo in nomes_reservados:
                        continue
                    eh_volume = bool(re.search(r"\d\s*(?:ml|cl|L)\b", rotulo_fmt))
                    un_ref = "L" if eh_volume else cfg["un_ref"]
                    item = {
                        "nome": nome_completo,
                        "categoria": cat_nome,
                        "unidade_medida": unidade,
                        "conteudo_liquido": conteudo,
                        "unidade_referencia": un_ref,
                        "pvp": pvp,
                        "margem": cfg["margem"],
                        "descarte": cfg["descarte"],
                        "elasticidade": cfg["elasticidade"],
                        "conservacao": cfg["conservacao"],
                    }
                    if cat_nome == "padaria":
                        pool_padaria.append(item)
                    else:
                        pool_outras.append(item)

        rng.shuffle(pool_padaria)
        rng.shuffle(pool_outras)

        padaria_sel = pool_padaria[:25]
        max_outras = max(0, self.total_produtos - 4 - len(padaria_sel))
        pool = padaria_sel + pool_outras[:max_outras]
        rng.shuffle(pool)
        return pool

    def gerar_dataset_temporal(self, data_ref: date | None = None) -> tuple[list[dict], list[dict]]:
        """
        Gera o catálogo realista (200 produtos) e os respetivos 1.000 lotes (5 por produto)
        com datas relativas a `data_ref` (por omissão `date.today()`), persiste em SQLite e devolve (catalogo, lotes).
        """
        if data_ref is None:
            data_ref = date.today()

        rng = random.Random(self.seed)
        periodo_semana = _calcular_periodo_semana(data_ref)
        artigos_reais = self._construir_pool_artigos_reais(rng)

        total_efetivo = min(self.total_produtos, len(artigos_reais) + 4)
        indices_todos = list(range(1, total_efetivo + 1))

        indices_validade_curta = set(rng.sample(indices_todos, max(4, int(total_efetivo * 0.22))))
        indices_campanha = set(rng.sample(indices_todos, max(4, int(total_efetivo * 0.35))))

        # Garantir casos emblemáticos para demonstração
        indices_validade_curta.update({1, 2})
        indices_validade_curta.discard(3)
        indices_validade_curta.discard(4)

        indices_campanha.update({1, 3})
        indices_campanha.discard(2)
        indices_campanha.discard(4)

        catalogo: list[dict] = []
        lotes: list[dict] = []
        contador_lote = 1000
        
        lotes_padaria_dia0 = 0
        for idx in indices_todos:
            prod_id = f"PROD-{idx:04d}"
            gtin = _gerar_gtin13(idx)

            # 1.º BLOCO: Definição do produto no catálogo
            if idx == 1:
                cat_nome = "pescado"
                nome = "Salmão Fresco Atlântico"
                unidade_prod = "kg"
                conteudo_liq = 1.0
                un_ref = "kg"
                pvp = 18.50
                vendas_dia = 3.0
                cfg = CATALOGO_CURADO[cat_nome]
            elif idx == 2:
                cat_nome = "carne"
                nome = "Bife de Vazia Maturado"
                unidade_prod = "kg"
                conteudo_liq = 1.0
                un_ref = "kg"
                pvp = 12.99
                vendas_dia = 5.0
                cfg = CATALOGO_CURADO[cat_nome]
            elif idx == 3:
                cat_nome = "laticinios"
                nome = "Iogurte Natural (Pack 4)"
                unidade_prod = "pack"
                conteudo_liq = 0.50
                un_ref = "kg"
                pvp = 1.80
                vendas_dia = 10.0
                cfg = CATALOGO_CURADO[cat_nome]
            elif idx == 4:
                cat_nome = "mercearia"
                nome = "Azeite Virgem Extra 0,75L"
                unidade_prod = "un"
                conteudo_liq = 0.75
                un_ref = "L"
                pvp = 7.49
                vendas_dia = 4.0
                cfg = CATALOGO_CURADO[cat_nome]
            else:
                spec = artigos_reais[idx - 5]
                cat_nome = spec["categoria"]
                nome = spec["nome"]
                unidade_prod = spec["unidade_medida"]
                conteudo_liq = spec["conteudo_liquido"]
                un_ref = spec["unidade_referencia"]
                pvp = spec["pvp"]
                vendas_dia = round(rng.uniform(2.0, 12.0), 1)
                cfg = spec

            custo = round(pvp * rng.uniform(0.55, 0.68), 2)

            tem_campanha = idx in indices_campanha
            desc_campanha = rng.choice([0.15, 0.20, 0.25, 0.30]) if tem_campanha else 0.0
            if idx == 1:
                desc_campanha = 0.25
            elif idx == 3:
                desc_campanha = 0.20

            catalogo.append({
                "produto_id": prod_id,
                "gtin": gtin,
                "nome": nome,
                "categoria": cat_nome,
                "tipo_validade": "preferencia_antes" if cat_nome in ("mercearia", "bebidas") else "consumir_ate",
                "unidade_medida": unidade_prod,
                "conteudo_liquido": conteudo_liq,
                "unidade_referencia": un_ref,
                "pvp": pvp,
                "desconto_campanha": desc_campanha,
                "periodo_campanha": periodo_semana if tem_campanha else "",
                "custo_aquisicao": custo,
                "margem_minima_pct": cfg["margem"],
                "custo_descarte": cfg["descarte"],
                "vendas_medias_diarias": vendas_dia,
                "elasticidade_preco": cfg["elasticidade"],
                "conservacao": cfg["conservacao"],
            })

            tem_validade_curta = idx in indices_validade_curta

            # 2.º BLOCO: 6 lotes na padaria | 2 lotes nas restantes categorias
            if cat_nome == "padaria":
                max_d = _max_dias_validade_padaria(nome)
                dias_pao = sorted([rng.randint(1, max_d) for _ in range(6)])
                if lotes_padaria_dia0 < 2 and eh_padaria_elegivel_racao({"categoria": cat_nome, "nome": nome}):
                    dias_pao[0] = 0
                    lotes_padaria_dia0 += 1
                especificacoes_lotes = [
                    (
                        d_exp,
                        max(3, int(round(vendas_dia * rng.uniform(0.5, 1.4)))),
                        max(1, rng.randint(0, 1)) if d_exp == 0 else rng.randint(0, 1),
                    )
                    for d_exp in dias_pao
                ]
            elif idx == 1:
                especificacoes_lotes = [
                    (1, 7.0, 4),
                    (4, 10.0, 1),
                ]
            elif tem_validade_curta:
                dias_exp_1 = rng.randint(1, 5)
                qtd_1 = max(6.0, round(vendas_dia * dias_exp_1 * rng.uniform(1.35, 2.2), 1))
                especificacoes_lotes = [(dias_exp_1, qtd_1, rng.randint(2, 6))]

                if idx % 4 == 0 and dias_exp_1 < 5:
                    dias_exp_2 = min(5, dias_exp_1 + rng.randint(1, 2))
                    especificacoes_lotes.append((dias_exp_2, max(5.0, round(vendas_dia * 1.6, 1)), 1))
                else:
                    d_fut = rng.randint(7, 60)
                    qtd_fut = max(5.0, round(vendas_dia * rng.uniform(1.5, 4.0), 1))
                    especificacoes_lotes.append((d_fut, qtd_fut, rng.randint(0, 3)))
            else:
                dias_lotes = sorted(rng.sample(range(6, 61), 2))
                especificacoes_lotes = [
                    (d_exp, max(5.0, round(vendas_dia * rng.uniform(1.5, 4.0), 1)), rng.randint(0, 8))
                    for d_exp in dias_lotes
                ]

            for dias_exp, qtd, dias_desde_entrada in especificacoes_lotes:
                if unidade_prod != "kg":
                    qtd = int(round(qtd))
                contador_lote += 1
                lote_id = f"LOTE{contador_lote:04d}"
                data_val = data_ref + timedelta(days=dias_exp)
                data_ent = data_ref - timedelta(days=dias_desde_entrada)
                gs1_data = data_val.strftime("%y%m%d")
                preco_inicial = round(pvp * (1 - desc_campanha), 2)

                lotes.append({
                    "lote_id": lote_id,
                    "produto_id": prod_id,
                    "quantidade_disponivel": qtd,
                    "data_entrada": data_ent.isoformat(),
                    "data_validade": data_val.isoformat(),
                    "dias_para_expirar": dias_exp,
                    "desconto_validade": 0.0,
                    "preco_final_atual": preco_inicial,
                    "codigo_gs1_raw": f"01|{gtin}|17|{gs1_data}|10|{lote_id}",
                    "estado": "ativo",
                })

        self._persistir_no_sqlite(catalogo, lotes)
        return catalogo, lotes

    def _persistir_no_sqlite(self, catalogo: list[dict], lotes: list[dict]) -> None:
        with self._conectar() as conn:
            conn.execute("DELETE FROM inventario_lotes")
            conn.execute("DELETE FROM catalogo_produtos")

            conn.executemany("""
             INSERT INTO catalogo_produtos (
                 produto_id, gtin, nome, categoria, tipo_validade, unidade_medida, conteudo_liquido,
                 unidade_referencia, pvp, desconto_campanha, periodo_campanha,
                 custo_aquisicao, margem_minima_pct, custo_descarte,
                 vendas_medias_diarias, elasticidade_preco, conservacao
             ) VALUES (
                 :produto_id, :gtin, :nome, :categoria, :tipo_validade, :unidade_medida, :conteudo_liquido,
                 :unidade_referencia, :pvp, :desconto_campanha, :periodo_campanha,
                 :custo_aquisicao, :margem_minima_pct, :custo_descarte,
                 :vendas_medias_diarias, :elasticidade_preco, :conservacao
             )
         """, catalogo)

            conn.executemany("""
                INSERT INTO inventario_lotes (
                    lote_id, produto_id, quantidade_disponivel, data_entrada,
                    data_validade, dias_para_expirar, desconto_validade,
                    preco_final_atual, codigo_gs1_raw, estado
                ) VALUES (
                    :lote_id, :produto_id, :quantidade_disponivel, :data_entrada,
                    :data_validade, :dias_para_expirar, :desconto_validade,
                    :preco_final_atual, :codigo_gs1_raw, :estado
                )
            """, lotes)

    def carregar_do_sqlite(self) -> tuple[list[dict], list[dict]]:
        """Lê diretamente as tabelas SQLite caso se queira consultar o estado persistido."""
        with self._conectar() as conn:
            catalogo = [dict(row) for row in conn.execute("SELECT * FROM catalogo_produtos ORDER BY produto_id")]
            lotes = [dict(row) for row in conn.execute("SELECT * FROM inventario_lotes ORDER BY lote_id")]
        return catalogo, lotes

    def registar_telemetria_sqlite(self, data_ref: date, lotes: list[dict], cenario: str) -> tuple[bool, str]:
        """
        Regista o histórico de execuções na tabela `telemetria_execucoes` da base de dados SQLite local.
        """
        lotes_validade = [l for l in lotes if l.get("desconto_validade", 0.0) > 0]
        desc_medio = (
            sum(l["desconto_validade"] for l in lotes_validade) / max(1, len(lotes_validade))
        )

        with self._conectar() as conn:
            conn.executemany("""
             UPDATE inventario_lotes
             SET desconto_validade = ?, preco_final_atual = ?, estado = ?
             WHERE lote_id = ?
         """, [
             (
                 float(l.get("desconto_validade", 0.0)),
                 float(l.get("preco_final_atual", 0.0)),
                 str(l.get("estado", "ativo")),
                 str(l["lote_id"]),
             )
             for l in lotes
         ])

        return True, f"Telemetria registada em SQLite ({self.db_path}) na data {data_ref.isoformat()}."