import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


def agente_controlo_inventario(state: dict) -> dict:
    """
    Agente autónomo de Controlo de Inventário alimentado por LangChain e OpenRouter.
    Analisa os níveis de stock, códigos 2D GS1 DataMatrix e prazos de validade.
    """
    produto = state.get("produto_atual", {})
    nome = produto.get("nome", "Produto")
    dias = produto.get("dias_para_validade", 3)
    quantidade = produto.get("quantidade_kg", 0.0)
    vendas = produto.get("historico_vendas_diarias", 0.0)
    codigo_2d = produto.get("codigo_2d", "N/A")

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if api_key:
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.7
            )
            prompt = f"""
            És o Agente de Controlo de Inventário de uma superfície comercial.
            Analisa o seguinte lote lido via código GS1 DataMatrix (2D):
            - Artigo: {nome}
            - Código 2D: {codigo_2d}
            - Stock atual: {quantidade} kg
            - Dias para validade: {dias} dia(s)
            - Vendas diárias esperadas: {vendas} kg/dia

            Avalia o risco de desperdício e emite um parecer técnico curto (máximo 2 frases) para os outros agentes.
            """
            resposta = llm.invoke([SystemMessage(content="Aja estritamente como um agente de inventário autónomo."),
                                   HumanMessage(content=prompt)]).content

            return {
                "parecer_inventario": resposta,
                "risco_critico": dias <= 1 or (quantidade / max(0.1, vendas)) > dias
            }
        except Exception:
            pass

    # Fallback local se não houver chave API
    risco = dias <= 1
    parecer = f"Análise local: Lote {nome} com {quantidade}kg e {dias} dia(s) de validade. Risco crítico: {risco}."
    return {
        "parecer_inventario": parecer,
        "risco_critico": risco
    }