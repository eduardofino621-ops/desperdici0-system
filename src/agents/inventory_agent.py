import os
from datetime import date
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.csp.constraints import _calcular_pum, _normalizar_categoria
from src.rag.retriever import construir_query_contextual_rag


def _detetar_chuva_temporal(meteo: dict | None, contexto_rag: list[dict] | None = None) -> bool:
    """Deteta chuva ou temporal exclusivamente a partir dos dados meteorológicos reais/simulados."""
    if not isinstance(meteo, dict):
        return False
    texto = " ".join(
        str(meteo.get(k, ""))
        for k in ("condicao", "descricao", "estado", "modo", "tipo", "alerta")
    ).lower()
    return any(p in texto for p in ("chuva", "temporal", "aguaceiro", "trovoada", "rain", "storm"))


def agente_controlo_inventario(state: dict) -> dict:
    """
    Agente autónomo de Controlo de Inventário alimentado por LangChain, OpenRouter e RAG.
    """
    lote = state.get("lote_atual", {})
    produto = state.get("produto_catalogo", {})

    if not produto and lote:
        catalogo = state.get("catalogo_produtos", [])
        produto = next(
            (p for p in catalogo if p.get("produto_id") == lote.get("produto_id")),
            {}
        )

    nome = produto.get("nome", "Produto Desconhecido")
    categoria = _normalizar_categoria(produto.get("categoria", "geral"))
    unidade = produto.get("unidade_medida", "un")
    pvp = float(produto.get("pvp", 0.0))
    pum_str = _calcular_pum(pvp, produto)
    desconto_campanha = float(produto.get("desconto_campanha", 0.0))
    vendas_medias = float(produto.get("vendas_medias_diarias", 0.0))
    conservacao = produto.get("conservacao", "N/A")

    lote_id = lote.get("lote_id", "N/A")
    quantidade = float(lote.get("quantidade_disponivel", 0.0))
    data_entrada = lote.get("data_entrada", "N/A")
    data_validade = lote.get("data_validade", "N/A")
    dias_restantes = int(lote.get("dias_para_expirar", 3))
    codigo_gs1 = lote.get("codigo_gs1_raw", "N/A")
    estado_lote = lote.get("estado", "ativo")

    meteo = state.get("meteorologia")
    data_ref = state.get("data_referencia", date.today())
    data_hoje = data_ref.isoformat()
    perturbacoes = state.get("perturbacoes_ativas", [])

    # Consulta RAG contextual
    rag = state.get("rag_retriever")
    contexto_rag = state.get("contexto_rag", [])
    if rag and not contexto_rag:
        query_rag = construir_query_contextual_rag(produto, lote, perturbacoes, data_ref, meteo)
        contexto_rag = rag.recuperar_contexto(query_rag, categoria=categoria, top_k=3)

    chuva_temporal = _detetar_chuva_temporal(meteo)

    bloco_rag = (
        "\n".join(f"- [{c['id']}] {c['texto']}" for c in contexto_rag)
        if contexto_rag
        else "Sem regras sazonais ou históricas adicionais."
    )

    dias_cobertura_stock = round(quantidade / max(0.1, vendas_medias), 1)
    excesso_estimado = max(0.0, round(quantidade - (vendas_medias * max(0, dias_restantes)), 2))
    risco_critico = dias_restantes <= 1 or dias_cobertura_stock > dias_restantes

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if api_key:
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.3
            )

            prompt = f"""
És o Agente de Controlo de Inventário de uma superfície comercial.
Analisa o seguinte lote lido via código 2D GS1 DataMatrix na data de hoje ({data_hoje}):

- Artigo: {nome} (Categoria: {categoria} | Conservação: {conservacao})
- Lote ID: {lote_id} (Estado: {estado_lote}) | Código GS1: {codigo_gs1}
- Preço de catálogo: {pvp:.2f} €/{unidade} (PUM legal: {pum_str} | Desconto campanha ativo: {desconto_campanha * 100:.0f}%)
- Stock atual do lote: {quantidade} {unidade} (Entrada em loja: {data_entrada})
- Data de validade: {data_validade} (Faltam {dias_restantes} dia(s))
- Procura média efetiva: {vendas_medias} {unidade}/dia
- Cobertura de stock atual: {dias_cobertura_stock} dias (Excesso previsto ao ritmo atual: {excesso_estimado} {unidade})

### Contexto Histórico e Sazonal Recuperado (RAG):
{bloco_rag}

Avalia o risco de desperdício deste lote específico considerando o contexto RAG e emite um parecer técnico curto (máximo 2 frases) para os agentes de Logística e Pricing.
"""
            resposta = llm.invoke([
                SystemMessage(content="Aja estritamente como um agente de inventário autónomo, objetivo e orientado a métricas."),
                HumanMessage(content=prompt)
            ]).content

            return {
                "parecer_inventario": resposta,
                "risco_critico": risco_critico,
                "excesso_estimado": excesso_estimado,
                "dias_cobertura_stock": dias_cobertura_stock,
                "pum_inicial": pum_str,
                "contexto_rag": contexto_rag,
                "chuva_temporal": chuva_temporal,
            }
        except Exception:
            pass

    parecer = (
        f"Análise local ({data_hoje}): Lote {lote_id} de {nome} com {quantidade} {unidade} "
        f"(validade {data_validade}, {dias_restantes}d restantes, PUM {pum_str}). "
        f"Excesso previsto: {excesso_estimado} {unidade}. Risco crítico: {risco_critico}."
    )
    return {
        "parecer_inventario": parecer,
        "risco_critico": risco_critico,
        "excesso_estimado": excesso_estimado,
        "dias_cobertura_stock": dias_cobertura_stock,
        "pum_inicial": pum_str,
        "contexto_rag": contexto_rag,
        "chuva_temporal": chuva_temporal,
    }