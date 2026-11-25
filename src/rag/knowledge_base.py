from pathlib import Path
import sqlite3

REGRAS_CONHECIMENTO = [
    # ==========================================================================
    # 1. METEOROLOGIA E FLUXO DE CLIENTES
    # ==========================================================================
    {
        "id": "METEO-CHUVA-01",
        "categoria": "geral",
        "texto": (
            "Dias de chuva intensa ou temporal reduzem drasticamente o tráfego pedonal e as visitas "
            "espontâneas à loja (quebra de 20% a 40% na procura diária). Os agentes devem antecipar "
            "excesso de stock em perecíveis (padaria, fruta, carne e pescado) e aplicar descontos de "
            "validade mais cedo (a partir de 3 dias) para compensar a menor afluência."
        ),
    },
    {
        "id": "METEO-CALOR-02",
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
        "id": "CICLO-INICIO-MES-01",
        "categoria": "geral",
        "texto": (
            "No início do mês (dias 1 a 10, após pagamento de salários e pensões), há maior afluência "
            "e carrinhos de compras maiores, incluindo produtos de maior valor (carne, pescado, charcutaria). "
            "A rotação natural de stock é elevada, pelo que descontos moderados (15% a 30%) bastam para escoar lotes."
        ),
    },
    {
        "id": "CICLO-FIM-MES-02",
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
        "id": "CAL-FIM-SEMANA-01",
        "categoria": "geral",
        "texto": (
            "À sexta-feira e sábado regista-se o pico semanal de compras familiares. Se um lote expira "
            "no domingo ou segunda-feira, o sábado é a última janela de alta procura para escoar na prateleira."
        ),
    },
    {
        "id": "CAL-FERIADOS-02",
        "categoria": "geral",
        "texto": (
            "Na véspera de feriados e nos próprios feriados (quando a loja está aberta), há grande afluência "
            "para compras de última hora e convívios (carne, bebidas, padaria, fruta). Contudo, se a loja "
            "encerrar no dia seguinte (feriado fechado), qualquer lote com validade <= 1 dia deve ter "
            "urgência máxima: desconto agressivo até 2 horas antes do fecho e doação externa (IPSS) no encerramento."
        ),
    },
    {
        "id": "SAZONAL-NATAL-03",
        "categoria": "geral",
        "texto": (
            "Na época de Natal e Ano Novo (dezembro), as compras aumentam significativamente, com picos "
            "de procura em pescado (bacalhau), carne (peru, cabrito), charcutaria, fruta e pastelaria festiva. "
            "Porém, após o dia 24 e dia 31 de dezembro, a procura cai abruptamente e os excedentes sazonais "
            "exigem liquidação imediata (50% a 70%) ou doação para evitar desperdício pós-festa."
        ),
    },
    {
        "id": "SAZONAL-PASCOA-SANTOS-04",
        "categoria": "geral",
        "texto": (
            "Na Páscoa (março/abril) e nos Santos Populares (junho), disparam as compras de carne, pescado "
            "(sardinha), padaria tradicional (folar, broa) e bebidas. Lotes de produtos festivos que sobram "
            "no dia seguinte ao evento perdem atratividade comercial e devem ser escoados via descontos críticos ou doação."
        ),
    },
    {
        "id": "SAZONAL-AGOSTO-05",
        "categoria": "geral",
        "texto": (
            "Em agosto, nas zonas urbanas não turísticas, a saída de residentes para férias reduz o fluxo "
            "diário nas lojas de bairro, aumentando o risco de acumulação de stock em laticínios, padaria e frescos."
        ),
    },

    # ==========================================================================
    # 4. REGRAS OPERACIONAIS POR CATEGORIA E SEGURANÇA ALIMENTAR
    # ==========================================================================
    {
        "id": "CAT-PADARIA-01",
        "categoria": "padaria",
        "texto": (
            "Produtos de padaria fresca têm ciclo de vida de 24h. A menos de 2 horas do fecho da loja, "
            "descontos de 50% a 70% ou a agregação em Sacos Surpresa equilibrados (0,50 kg) maximizam a "
            "recuperação financeira sem custo de descarte."
        ),
    },
    {
        "id": "CAT-PERECIVEIS-02",
        "categoria": "carne",
        "texto": (
            "Carne fresca e pescado ostentam data-limite de consumo ('Consumir até'). Por segurança alimentar, "
            "nunca podem ser vendidos após a data de validade: no último dia útil, se não houver escoamento "
            "previsto até ao fecho, devem seguir para cozinha interna (até às 18h) ou doação refrigerada."
        ),
    },
    {
        "id": "CAT-MERCEARIA-03",
        "categoria": "mercearia",
        "texto": (
            "Artigos de mercearia e bebidas têm data de durabilidade mínima ('Consumir de preferência antes de'). "
            "Descontos graduais (20% a 40%) nos últimos 3 a 5 dias são suficientes e mantêm margem positiva."
        ),
    },
    {
        "id": "CAT-FRUTA-04",
        "categoria": "fruta",
        "texto": (
            "Fruta e hortícolas em pico de stock excedente sofrem perda rápida de qualidade visual. "
            "Descontos de 30% a 50% com 2 a 3 dias de antecedência aceleram o escoamento; fruta muito madura "
            "mas própria para consumo deve ser canalizada para cozinha interna ou parceria de ração animal."
        ),
    },
]


def carregar_documentos_rag(db_path: str = "data/desperdicio.db") -> list[dict]:
    documentos = list(REGRAS_CONHECIMENTO)
    caminho = Path(db_path)
    if not caminho.exists():
        return documentos

    try:
        with sqlite3.connect(caminho) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tabelas = {row[0] for row in cursor.fetchall()}

            for tabela in tabelas:
                cursor.execute(f"PRAGMA table_info({tabela})")
                colunas = {c[1] for c in cursor.fetchall()}
                if {"cenario", "categoria", "destino_final"}.issubset(colunas):
                    cursor.execute(
                        f"SELECT cenario, categoria, destino_final, COUNT(*) "
                        f"FROM {tabela} GROUP BY cenario, categoria, destino_final LIMIT 50"
                    )
                    for cen, cat, dest, qtd in cursor.fetchall():
                        documentos.append({
                            "id": f"HIST-{cen}-{cat}",
                            "categoria": str(cat).lower(),
                            "texto": (
                                f"Histórico operacional: No cenário '{cen}', para a categoria '{cat}', "
                                f"foram encaminhados {qtd} lotes para '{dest}'."
                            ),
                        })
    except Exception:
        pass

    return documentos