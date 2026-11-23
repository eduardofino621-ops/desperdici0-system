import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


class DecisaoLogistica(BaseModel):
    destino_proposto: str = Field(
        description="Um de: 'prateleira_desconto', 'sacos_surpresa', 'cozinha_interna', 'doacao_externa'."
    )
    razao_logistica: str = Field(
        description="Justificação operacional curta (máximo 2 frases)."
    )


def agente_logistica_doacao(state: dict) -> dict:
    lote = state.get("lote_atual", {})
    produto = state.get("produto_catalogo", {})
    fecho_loja_2h = state.get("fecho_loja_2h", False)

    nome = produto.get("nome", "Produto")
    categoria = produto.get("categoria", "geral")
    unidade = produto.get("unidade_medida", "un")
    quantidade = lote.get("quantidade_disponivel", 0.0)
    dias = lote.get("dias_para_expirar", 3)
    excesso = state.get("excesso_estimado", 0.0)
    cobertura = state.get("dias_cobertura_stock", 1.0)
    parecer_inv = state.get("parecer_inventario", "")

    if dias <= 0:
        if categoria == "padaria":
            return {
                "destino_proposto": "racao_animal",
                "razao_logistica": "Pão em fim de vida útil encaminhado para instituição de transformação em farinha para ração animal.",
            }
        return {
            "destino_proposto": "descarte_obrigatorio",
            "razao_logistica": "Lote expirado; retirada imediata obrigatória.",
        }

    if categoria == "padaria":
        if dias == 1 and fecho_loja_2h and quantidade > 0:
            return {
                "destino_proposto": "sacos_surpresa",
                "razao_logistica": f"A <= 2h do fecho: {quantidade} {unidade} de padaria (1d) alocados à pool de sacos surpresa.",
            }
        if excesso > 0 and cobertura > (dias * 3.2):
            return {
                "destino_proposto": "racao_animal",
                "razao_logistica": f"Excesso extremo de padaria ({quantidade} {unidade}); encaminhado para farinha de ração animal (cozinha proibida).",
            }
        return {
            "destino_proposto": "prateleira_desconto",
            "razao_logistica": "Padaria mantida em prateleira a preço normal fora da janela de 2h antes do fecho (anti-canibalismo).",
        }

    # Em operação normal, mantém na prateleira ESL para escoamento dinâmico;
    # só desvia para cozinha/doação quando o excesso ultrapassa 3.2x a procura restante.
    if excesso > 0 and cobertura > (dias * 3.2):
        if categoria in ["pescado", "carne"] and dias <= 1:
            return {
                "destino_proposto": "cozinha_interna",
                "razao_logistica": f"Excesso extremo ({quantidade} {unidade} para {dias}d); desviado para cozinha interna.",
            }
        if dias >= 2:
            return {
                "destino_proposto": "doacao_externa",
                "razao_logistica": f"Excesso extremo ({quantidade} {unidade}) com >= 48h de validade; encaminhado para doação IPSS.",
            }

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and excesso > 0 and cobertura > (dias * 2.5):
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
            ).with_structured_output(DecisaoLogistica)

            prompt = f"""
És o Agente de Logística de uma superfície comercial. Define o destino deste lote:
- Artigo: {nome} (Categoria: {categoria}) | Stock: {quantidade} {unidade} | Validade: {dias} dia(s)
- Excesso estimado: {excesso} {unidade} | Parecer Inventário: {parecer_inv}

Regra: Usa 'prateleira_desconto' sempre que seja viável escoar em loja com etiqueta ESL.
"""
            decisao: DecisaoLogistica = llm.invoke([
                SystemMessage(content="Responde de forma objetiva seguindo as regras operacionais de retalho."),
                HumanMessage(content=prompt),
            ])
            return {
                "destino_proposto": decisao.destino_proposto,
                "razao_logistica": decisao.razao_logistica,
            }
        except Exception:
            pass

    return {
        "destino_proposto": "prateleira_desconto",
        "razao_logistica": f"Mantido em prateleira ({dias}d restantes) para escoamento via etiqueta eletrónica ESL.",
    }