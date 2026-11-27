import logging
from pathlib import Path
import sqlite3
from src.csp.constraints import _normalizar_categoria

logger = logging.getLogger(__name__)

REGRAS_CONHECIMENTO = [
    # ==========================================================================
    # 1. METEOROLOGIA E FLUXO DE CLIENTES
    # ==========================================================================
    {
        "id": "Meteorologia: Dia de Chuva / Temporal",
        "categoria": "geral",
        "texto": (
          "Dias de chuva intensa ou temporal reduzem o tráfego pedonal e as visitas espontâneas "
          "(quebra de 20% a 40% na procura diária). Os agentes devem aplicar descontos graduais "
          "(até 30% a 2 dias e até 45% no último dia) para escoar perecíveis antes de recorrer "
          "a encaminhamento externo elegível."
        ),
    },
    {
        "id": "Meteorologia: Calor Elevado",
        "categoria": "bebidas",
        "texto": (
            "Dias de calor elevado aumentam fortemente a procura por bebidas frescas, águas, sumos, "
            "fruta de verão e produtos de churrasco, reduzindo a necessidade de descontos agressivos "
            "nessas categorias, mas acelerando a deterioração térmica de frescos fora do frio."
        ),
    },

    # ==========================================================================
    # 2. CICLO MENSAL (PODER DE COMPRA E RENDIMENTOS)
    # ==========================================================================
    {
        "id": "Ciclo Mensal: Início do Mês (Salários)",
        "categoria": "geral",
        "texto": (
            "No início do mês (dias 1 a 10, após pagamento de salários e pensões), há maior afluência "
            "e carrinhos de compras maiores, incluindo produtos de maior valor (carne, pescado). "
            "A rotação natural de stock é elevada, pelo que descontos moderados (15% a 30%) bastam para escoar lotes."
        ),
    },
    {
        "id": "Ciclo Mensal: Fim do Mês (Contenção)",
        "categoria": "geral",
        "texto": (
            "No fim do mês (dias 22 a 31), as famílias privilegiam preço baixo e artigos premium "
            "(carne fresca, pescado) perdem rotação. Aplicar primeiro descontos graduais "
            "(25% a 45%) para preservar margem e encaminhar apenas o excedente residual para cozinha "
            "interna ou Sacos Surpresa."
        ),
    },

    # ==========================================================================
    # 3. CALENDÁRIO SEMANAL, FERIADOS E ÉPOCAS FESTIVAS
    # ==========================================================================
    {
        "id": "Calendário: Pico de Fim de Semana",
        "categoria": "geral",
        "texto": (
            "À sexta-feira e sábado regista-se o pico semanal de compras familiares. Se um lote expira "
            "no domingo ou segunda-feira, o sábado é a última janela de alta procura para escoar na prateleira."
        ),
    },
    {
        "id": "Calendário: Véspera e Dia de Feriado",
        "categoria": "geral",
        "texto": (
            "Na véspera de feriados e nos próprios feriados (quando a loja está aberta), há grande afluência "
            "para compras de última hora e convívios (carne, pescado, bebidas, padaria, fruta). Contudo, se a loja "
            "encerrar no dia seguinte (feriado fechado), qualquer lote com validade <= 1 dia deve ter "
            "urgência máxima: desconto agressivo até 2 horas antes do fecho e encaminhamento interno elegível "
            "(cozinha interna para carne/pescado ou Sacos Surpresa/ração animal para padaria e pastelaria; "
            "doação externa IPSS apenas para lotes 'Consumir até' com >= 48h de validade)."
        ),
    },
    {
        "id": "Sazonalidade: Época de Natal e Ano Novo",
        "categoria": "geral",
        "texto": (
            "Na época de Natal e Ano Novo (dezembro), as compras aumentam significativamente, com picos "
            "de procura em pescado (bacalhau), carne (peru, cabrito), fruta e pastelaria festiva. "
            "Porém, após o dia 24 e dia 31 de dezembro, a procura cai abruptamente e os excedentes sazonais "
            "exigem liquidação imediata (50% a 70%) ou encaminhamento elegível para evitar desperdício pós-festa."
        ),
    },
    {
        "id": "Sazonalidade: Páscoa e Santos Populares",
        "categoria": "geral",
        "texto": (
            "Na Páscoa (março/abril) e nos Santos Populares (junho), disparam as compras de carne, pescado "
            "(sardinha), padaria tradicional (folar, broa) e bebidas. Lotes de produtos festivos que sobram "
            "no dia seguinte ao evento perdem atratividade comercial e devem ser escoados via descontos críticos "
            "ou destino operacional elegível."
        ),
    },
    {
        "id": "Sazonalidade: Férias de Agosto",
        "categoria": "geral",
        "texto": (
            "Em agosto, nas zonas urbanas não turísticas, a saída de residentes para férias reduz o fluxo "
            "diário nas lojas de bairro, aumentando o risco de acumulação de stock em laticinios, padaria e frescos."
        ),
    },

    # ==========================================================================
    # 4. REGRAS OPERACIONAIS POR CATEGORIA E SEGURANÇA ALIMENTAR
    # ==========================================================================
    {
        "id": "Regra Categoria: Padaria, Pastelaria e Sacos Surpresa",
        "categoria": "padaria",
        "texto": (
          "Produtos de padaria e pastelaria fresca têm ciclo de vida curto (24h a 48h). Durante o dia, "
          "descontos de 25% escoam o stock em prateleira, enquanto a quota elegível para Sacos Surpresa "
          "(35% em operação normal ou 50% com perturbação/fecho a <= 2h) recebe desconto de 45% em lotes "
          "equilibrados de 0,50 kg. No fim de vida útil, 100% do pão simples elegível segue para farinha "
          "de ração animal, enquanto os 9 artigos com chocolate, chouriço, ovos/gorduras doces, alho ou "
          "nozes seguem para descarte obrigatório por segurança alimentar (SANDACH)."
        ),
    },
    {
        "id": "Regra Categoria: Laticínios (Teto 50% a 24h)",
        "categoria": "laticinios",
        "texto": (
            "Artigos de laticínios com 24h ou menos para expirar têm limite máximo de desconto de 50% "
            "em etiqueta ESL para preservar equilíbrio comercial e evitar distorção de procura."
        ),
    },
    {
        "id": "Segurança Alimentar: Carne (Consumir Até)",
        "categoria": "carne",
        "texto": (
            "A carne fresca ostenta data-limite de consumo ('Consumir até'). Por segurança alimentar, "
            "nunca pode ser vendida após a data de validade, nunca vai para ração animal e não pode ir "
            "para doação externa a <= 24h: no último dia útil, sem escoamento previsto, segue para cozinha interna."
        ),
    },
    {
        "id": "Segurança Alimentar: Pescado (Consumir Até)",
        "categoria": "pescado",
        "texto": (
            "O pescado fresco ostenta data-limite de consumo ('Consumir até'). Por segurança alimentar, "
            "nunca pode ser vendido após a data de validade, nunca vai para ração animal e não pode ir "
            "para doação externa a <= 24h: no último dia útil, sem escoamento previsto, segue para cozinha interna."
        ),
    },
    {
        "id": "Regra Categoria: Mercearia e Bebidas",
        "categoria": "mercearia",
        "texto": (
            "Artigos de mercearia e bebidas têm data de durabilidade mínima ('Consumir de preferência antes de'). "
            "Descontos graduais (20% a 40%) nos últimos 3 a 5 dias são suficientes e mantêm margem positiva."
        ),
    },
    {
      "id": "Regra Categoria: Fruta Fresca",
      "categoria": "fruta",
      "texto": (
          "Fruta fresca em pico de stock excedente perde atratividade visual rapidamente. "
          "Aplicar descontos graduais (20% a 30% com 2 a 3 dias e 40% ou mais no último dia, até ao teto "
          "legal de 70%) para maximizar a receita em loja, encaminhando para doação IPSS o excesso "
          "severo a 48h da validade."
      ),
  },
]


def carregar_documentos_rag(db_path: str = "data/desperdicio.db") -> list[dict]:
    documentos = [
        {**doc, "categoria": _normalizar_categoria(doc.get("categoria"))}
        for doc in REGRAS_CONHECIMENTO
    ]
    caminho = Path(db_path)
    if not caminho.exists():
        return documentos

    try:
        with sqlite3.connect(caminho) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT cenario, COUNT(*), ROUND(AVG(lotes_desconto_validade), 1), ROUND(AVG(desconto_medio_pct), 1)
                FROM telemetria_execucoes
                GROUP BY cenario
                ORDER BY MAX(id) DESC
                LIMIT 15
            """)
            for cenario, n_exec, media_lotes, media_desc in cursor.fetchall():
                documentos.append({
                    "id": f"Histórico Cenário: {cenario}",
                    "categoria": "geral",
                    "texto": (
                        f"Histórico operacional ({n_exec} execuções): No cenário '{cenario}', "
                        f"aplicou-se desconto de validade em média a {media_lotes} lotes, "
                        f"com redução média de {media_desc}% sobre o PVP."
                    ),
                })

            cursor.execute("""
                SELECT
                    p.categoria,
                    COUNT(l.lote_id),
                    ROUND(AVG(l.desconto_validade) * 100, 1),
                    ROUND(SUM(l.quantidade_disponivel * l.preco_final_atual), 2),
                    ROUND(SUM(l.quantidade_disponivel * (p.custo_aquisicao + p.custo_descarte)), 2)
                FROM inventario_lotes l
                JOIN catalogo_produtos p ON l.produto_id = p.produto_id
                WHERE l.desconto_validade > 0
                GROUP BY p.categoria
            """)
            for cat, qtd_lotes, desc_medio, receita_rec, prejuizo_evitado in cursor.fetchall():
                cat_norm = _normalizar_categoria(str(cat))
                documentos.append({
                    "id": f"Histórico Financeiro: {cat_norm.capitalize()}",
                    "categoria": cat_norm,
                    "texto": (
                        f"Histórico financeiro ({cat_norm}): {qtd_lotes} lotes críticos escoados com desconto médio "
                        f"de {desc_medio}%, gerando {receita_rec:.2f}€ de receita recuperada e evitando "
                        f"{prejuizo_evitado:.2f}€ em perdas de aquisição e descarte."
                    ),
                })

            cursor.execute("""
                SELECT
                    p.conservacao,
                    l.dias_para_expirar,
                    COUNT(l.lote_id),
                    ROUND(AVG(l.desconto_validade) * 100, 1)
                FROM inventario_lotes l
                JOIN catalogo_produtos p ON l.produto_id = p.produto_id
                WHERE l.dias_para_expirar <= 5
                GROUP BY p.conservacao, l.dias_para_expirar
                HAVING COUNT(l.lote_id) >= 2
            """)
            for conservacao, dias, qtd, desc_med in cursor.fetchall():
                documentos.append({
                    "id": f"Histórico Conservação: {conservacao} ({dias}d)",
                    "categoria": "geral",
                    "texto": (
                        f"Padrão de conservação ({conservacao}, validade {dias} dia(s)): "
                        f"em {qtd} lotes analisados, o desconto médio aplicado foi de {desc_med}%."
                    ),
                })

            cursor.execute("""
                SELECT
                    p.produto_id,
                    p.nome,
                    p.categoria,
                    p.elasticidade_preco,
                    COUNT(l.lote_id) AS n_lotes,
                    ROUND(AVG(l.desconto_validade) * 100, 1) AS desc_medio,
                    ROUND(AVG(l.preco_final_atual), 2) AS preco_medio
                FROM inventario_lotes l
                JOIN catalogo_produtos p ON l.produto_id = p.produto_id
                WHERE l.dias_para_expirar <= 5 AND l.desconto_validade > 0
                GROUP BY p.produto_id
                ORDER BY n_lotes DESC, preco_medio DESC
                LIMIT 15
            """)
            for prod_id, nome, cat, elast, n_lotes, desc_med, preco_med in cursor.fetchall():
                cat_norm = _normalizar_categoria(str(cat))
                documentos.append({
                    "id": f"Histórico Artigo: {nome}",
                    "categoria": cat_norm,
                    "texto": (
                        f"Histórico do artigo '{nome}' ({prod_id}, {cat_norm}, elasticidade {elast}): "
                        f"{n_lotes} lote(s) em risco escoados com desconto médio de {desc_med}% "
                        f"(preço ativo médio de {preco_med:.2f}€)."
                    ),
                })

            cursor.execute("""
                SELECT
                    p.categoria,
                    COUNT(l.lote_id),
                    ROUND(AVG(p.vendas_medias_diarias), 1)
                FROM inventario_lotes l
                JOIN catalogo_produtos p ON l.produto_id = p.produto_id
                WHERE l.dias_para_expirar BETWEEN 1 AND 3
                  AND l.desconto_validade = 0
                GROUP BY p.categoria
            """)
            for cat, qtd_sem_desc, vendas_med in cursor.fetchall():
                cat_norm = _normalizar_categoria(str(cat))
                documentos.append({
                    "id": f"Histórico Rotação Natural: {cat_norm.capitalize()}",
                    "categoria": cat_norm,
                    "texto": (
                        f"Padrão de rotação natural ({cat_norm}): {qtd_sem_desc} lotes a 1-3 dias da validade "
                        f"não necessitaram de desconto extra porque a procura média ({vendas_med} un/dia) "
                        f"absorve o stock disponível."
                    ),
                })
    except Exception as exc:
        logger.warning("Falha ao carregar histórico SQLite para o RAG (%s): %s", caminho, exc)

    return documentos