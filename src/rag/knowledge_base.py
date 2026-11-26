from pathlib import Path
import sqlite3


def _normalizar_categoria(categoria: str | None) -> str:
    cat = (categoria or "geral").strip().lower()
    if cat in ["peixe", "pescado"]:
        return "pescado"
    if cat in ["horticolas", "hortícolas", "legumes"]:
        return "legumes"
    if cat in ["laticínios", "laticinios"]:
        return "laticinios"
    return cat


REGRAS_CONHECIMENTO = [
    # ==========================================================================
    # 1. METEOROLOGIA E FLUXO DE CLIENTES
    # ==========================================================================
    {
        "id": "Meteorologia: Dia de Chuva / Temporal",
        "categoria": "geral",
        "texto": (
            "Dias de chuva intensa ou temporal reduzem drasticamente o tráfego pedonal e as visitas "
            "espontâneas à loja (quebra de 20% a 40% na procura diária). Os agentes devem antecipar "
            "excesso de stock em perecíveis (padaria, fruta, legumes, carne e pescado) e aplicar descontos de "
            "validade mais cedo (a partir de 3 dias) para compensar a menor afluência."
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
            "e carrinhos de compras maiores, incluindo produtos de maior valor (carne, pescado, charcutaria). "
            "A rotação natural de stock é elevada, pelo que descontos moderados (15% a 30%) bastam para escoar lotes."
        ),
    },
    {
        "id": "Ciclo Mensal: Fim do Mês (Contenção)",
        "categoria": "geral",
        "texto": (
            "No fim do mês (dias 22 a 31), as famílias reduzem compras e procuram fortemente preço baixo. "
            "Produtos premium (carne fresca, pescado, charcutaria) sofrem quebra de rotação e exigem "
            "descontos mais agressivos (35% a 60%) ou encaminhamento rápido para cozinha interna e Sacos Surpresa."
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
            "urgência máxima: desconto agressivo até 2 horas antes do fecho e doação externa (IPSS) no encerramento."
        ),
    },
    {
        "id": "Sazonalidade: Época de Natal e Ano Novo",
        "categoria": "geral",
        "texto": (
            "Na época de Natal e Ano Novo (dezembro), as compras aumentam significativamente, com picos "
            "de procura em pescado (bacalhau), carne (peru, cabrito), charcutaria, fruta e pastelaria festiva. "
            "Porém, após o dia 24 e dia 31 de dezembro, a procura cai abruptamente e os excedentes sazonais "
            "exigem liquidação imediata (50% a 70%) ou doação para evitar desperdício pós-festa."
        ),
    },
    {
        "id": "Sazonalidade: Páscoa e Santos Populares",
        "categoria": "geral",
        "texto": (
            "Na Páscoa (março/abril) e nos Santos Populares (junho), disparam as compras de carne, pescado "
            "(sardinha), padaria tradicional (folar, broa) e bebidas. Lotes de produtos festivos que sobram "
            "no dia seguinte ao evento perdem atratividade comercial e devem ser escoados via descontos críticos ou doação."
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
        "id": "Regra Categoria: Padaria e Sacos Surpresa",
        "categoria": "padaria",
        "texto": (
            "Produtos de padaria fresca têm ciclo de vida de 24h. A menos de 2 horas do fecho da loja, "
            "descontos de 50% a 70% ou a agregação em Sacos Surpresa equilibrados (0,50 kg) maximizam a "
            "recuperação financeira; excedentes sem saída seguem para transformação em farinha de ração animal."
        ),
    },
    {
        "id": "Segurança Alimentar: Carne (Consumir Até)",
        "categoria": "carne",
        "texto": (
            "A carne fresca ostenta data-limite de consumo ('Consumir até'). Por segurança alimentar, "
            "nunca pode ser vendida após a data de validade: no último dia útil, se não houver escoamento "
            "previsto até ao fecho, deve seguir para cozinha interna (até às 18h) ou valorização/doação elegível."
        ),
    },
    {
        "id": "Segurança Alimentar: Pescado (Consumir Até)",
        "categoria": "pescado",
        "texto": (
            "O pescado fresco ostenta data-limite de consumo ('Consumir até'). Por segurança alimentar, "
            "nunca pode ser vendido após a data de validade e não pode ir para doação externa a <= 24h: "
            "no último dia útil, se não houver escoamento previsto, deve seguir para cozinha interna ou valorização."
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
        "id": "Regra Categoria: Fruta e Legumes",
        "categoria": "fruta",
        "texto": (
            "Fruta e legumes em pico de stock excedente sofrem perda rápida de qualidade visual. "
            "Descontos de 30% a 50% com 2 a 3 dias de antecedência aceleram o escoamento; excedentes aptos "
            "seguem para doação ou encaminhamento útil antes de irem para o lixo."
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

            # 1. Histórico agregado por cenário (telemetria_execucoes)
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

            # 2. Eficiência financeira e recuperação de margem por categoria
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

            # 3. Comportamento por regime de conservação e urgência (dias_para_expirar)
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

            # 4. Top 15 produtos individuais mais recorrentes em risco (memória por artigo)
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
                ORDER BY n_lotes DESC, desc_medio DESC
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

            # 5. Artigos de alta rotação que escoam sem precisar de desconto de validade
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
    except Exception:
        pass

    return documentos