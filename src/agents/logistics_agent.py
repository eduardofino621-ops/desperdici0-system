import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


class DecisaoLogistica(BaseModel):
    destino_proposto: str = Field(
        description=(
            "Um de: 'prateleira_desconto', 'sacos_surpresa', 'cozinha_interna', "
            "'doacao_externa', 'racao_animal'."
        )
    )
    razao_logistica: str = Field(
        description="Justificação operacional curta (máximo 2 frases)."
    )


def _eh_elegivel_saco_padaria(lote_id: str, quota_fracao: float = 0.50) -> bool:
    """Seleciona de forma determinística a fração alvo (ex. 50% ou 65%) dos lotes para sacos surpresa."""
    digitos = "".join(c for c in str(lote_id) if c.isdigit())
    if not digitos:
        return False
    valor = (int(digitos) % 100) / 100.0
    return valor < max(0.0, min(1.0, quota_fracao))


def agente_logistica_doacao(state: dict) -> dict:
    lote = state.get("lote_atual", {})
    produto = state.get("produto_catalogo", {})
    fecho_loja_2h = state.get("fecho_loja_2h", False)
    perturbacoes = state.get("perturbacoes_ativas", [])
    quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbacoes
    contexto_rag = state.get("contexto_rag", [])

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
                "razao_logistica": (
                    "Pão em fim de vida útil encaminhado para instituição de transformação em farinha "
                    "para ração animal."
                ),
            }
        return {
            "destino_proposto": "descarte_obrigatorio",
            "razao_logistica": "Lote expirado; retirada imediata obrigatória.",
        }

    if categoria == "padaria":
        lote_id = lote.get("lote_id", "")
        quota_sacos = 0.50 if (fecho_loja_2h or quebra_clientes) else 0.35
        elegivel_saco = _eh_elegivel_saco_padaria(lote_id, quota_fracao=quota_sacos)

        if dias == 1 and fecho_loja_2h and quantidade > 0:
            if elegivel_saco:
                return {
                    "destino_proposto": "sacos_surpresa",
                    "razao_logistica": (
                        f"A <= 2h do fecho: fração prioritária ({int(quota_sacos * 100)}%) do pão de "
                        f"véspera ({quantidade} {unidade}, 1d) alocada a Sacos Surpresa."
                    ),
                }
            return {
                "destino_proposto": "prateleira_desconto",
                "razao_logistica": (
                    f"A <= 2h do fecho: pão de véspera ({quantidade} {unidade}, 1d) em prateleira com "
                    "desconto de fim de dia antes da valorização em ração animal."
                ),
            }

        if dias == 1 and not fecho_loja_2h and quantidade > 0:
            if elegivel_saco:
                return {
                    "destino_proposto": "sacos_surpresa",
                    "razao_logistica": (
                        f"Pão de véspera ({quantidade} {unidade}, 1d) alocado à pool de Sacos Surpresa "
                        f"(quota dinâmica de {int(quota_sacos * 100)}%)."
                    ),
                }
            return {
                "destino_proposto": "prateleira_desconto",
                "razao_logistica": (
                    f"Pão de véspera ({quantidade} {unidade}, 1d) mantido em prateleira com desconto ESL "
                    "progressivo para escoamento direto."
                ),
            }

        if dias == 2 and fecho_loja_2h and quantidade > 0 and elegivel_saco:
            return {
                "destino_proposto": "sacos_surpresa",
                "razao_logistica": (
                    f"A <= 2h do fecho: fração ({int(quota_sacos * 100)}%) de pão ({quantidade} {unidade}, 2d) "
                    "alocada preventivamente a Sacos Surpresa."
                ),
            }

        return {
            "destino_proposto": "prateleira_desconto",
            "razao_logistica": "Padaria mantida em prateleira para escoamento com etiqueta ESL.",
        }

    # Encaminhamento antecipado para não-padaria quando o excesso excede a capacidade de venda
    fator_cobertura_critica = 2.6 if categoria in ["laticinios", "charcutaria", "pescado", "carne"] else 3.5
    if excesso > 0 and cobertura > (dias * fator_cobertura_critica):
        if categoria in ["pescado", "carne", "charcutaria"] and dias <= 1:
            return {
                "destino_proposto": "cozinha_interna",
                "razao_logistica": (
                    f"Excesso crítico ({quantidade} {unidade} para {dias}d); desviado para cozinha interna."
                ),
            }
        if dias >= 2:
            return {
                "destino_proposto": "doacao_externa",
                "razao_logistica": (
                    f"Excesso elevado ({quantidade} {unidade}) com >= 48h de validade; encaminhado para "
                    "doação IPSS."
                ),
            }

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and excesso > 0 and cobertura > (dias * 2.0):
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
            ).with_structured_output(DecisaoLogistica)

            bloco_rag = (
                "\n".join(f"- [{c['id']}] {c['texto']}" for c in contexto_rag)
                if contexto_rag
                else "Sem contexto RAG adicional."
            )

            prompt = f"""
És o Agente de Logística de uma superfície comercial. Define o destino deste lote:
- Artigo: {nome} (Categoria: {categoria}) | Stock: {quantidade} {unidade} | Validade: {dias} dia(s)
- Excesso estimado: {excesso} {unidade} | Parecer Inventário: {parecer_inv}

### Contexto Histórico e Sazonal (RAG):
{bloco_rag}

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