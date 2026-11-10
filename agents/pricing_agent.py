import os
from openai import OpenAI


def agente_dynamic_pricing(state: dict) -> dict:
    """
    Calcula o desconto ótimo para o produto em risco. Se a chave da API estiver ativa,
    utiliza o LLM (via OpenRouter) para simular o raciocínio complexo de pricing.
    """
    produto = state.get("produto_atual")
    if not produto:
        return state

    print(f"[AGENTE PRICING] A calcular desconto ótimo para: {produto['nome']}...")

    dias = produto["dias_para_validade"]

    # Tentativa de integração com LLM via OpenRouter (se configurado)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        try:
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            prompt = f"""
            És um Agente de Dynamic Pricing num supermercado. 
            Produto: {produto['nome']}, Categoria: {produto['categoria']}, Preço Base: {produto['preco_base']}€, 
            Dias para a validade: {dias}, Vendas diárias esperadas: {produto['historico_vendas_diarias']}kg.
            Define uma percentagem de desconto (entre 0.10 e 0.70) para escoar o produto antes de expirar, maximizando a receita.
            Responde apenas com o valor numérico do desconto (ex: 0.50 para 50%).
            """
            response = client.chat.completions.create(
                model="deepseek/deepseek-chat",  # ou outro modelo via OpenRouter
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10
            )
            desconto_proposto = float(response.choices[0].message.content.strip())
            print(f"[AGENTE PRICING [LLM]] Desconto gerado por IA: {int(desconto_proposto * 100)}%")
        except Exception as e:
            print(f"[AGENTE PRICING] Erro ao chamar LLM: {e}. A usar regra heurística de fallback.")
            desconto_proposto = 0.60 if dias == 1 else 0.30
    else:
        # Fallback heurístico definido na proposta
        if dias == 1:
            desconto_proposto = 0.60
        elif dias == 2:
            desconto_proposto = 0.30
        else:
            desconto_proposto = 0.10

    state["desconto_proposto"] = desconto_proposto
    state["destino_proposto"] = "prateleira_desconto"

    return state