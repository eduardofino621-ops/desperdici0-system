import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


def agente_dynamic_pricing(state: dict) -> dict:
    """
    Agente autónomo de Dynamic Pricing com LangChain e OpenRouter.
    """
    produto = state.get("produto_atual", {})
    dias = produto.get("dias_para_validade", 3)
    preco_base = produto.get("preco_base", 0.0)
    nome = produto.get("nome", "Produto")
    categoria = produto.get("categoria", "geral")

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
            És o Agente de Dynamic Pricing da superfície comercial.
            Artigo: {nome} ({categoria}) | Preço Base: {preco_base}€ | Dias para validade: {dias}.
            Define o desconto percentual adequado (entre 0.05 e 0.70) para escoar o produto sem destruir margem.
            Responde no formato: 
            DESCONTO: [valor decimal, ex: 0.35]
            RAZAO: [justificação curta em português]
            """
            resposta = llm.invoke([SystemMessage(content="Aja estritamente como um agente de pricing autónomo."),
                                   HumanMessage(content=prompt)]).content

            import re
            match = re.search(r'0\.\d+', resposta)
            desc_proposto = float(match.group()) if match else (0.65 if dias <= 1 else 0.35)

            return {
                "desconto_proposto": desc_proposto,
                "raciocinio_pricing": resposta
            }
        except Exception as e:
            pass

    # Fallback local se não houver chave
    desc_proposto = 0.65 if dias <= 1 else (0.35 if dias == 2 else 0.15)
    return {
        "desconto_proposto": desc_proposto,
        "raciocinio_pricing": f"Fallback local: Desconto de {int(desc_proposto * 100)}% atribuído com base em {dias} dia(s) de validade."
    }