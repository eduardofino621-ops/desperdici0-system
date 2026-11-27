import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.csp.constraints import (
    CATEGORIAS_PADARIA_PASTELARIA,
    _normalizar_categoria,
    eh_elegivel_saco_padaria,
)


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


def agente_logistica_doacao(state: dict) -> dict:
    lote = state.get("lote_atual", {})
    produto = state.get("produto_catalogo", {})
    fecho_loja_2h = bool(state.get("fecho_loja_2h", False))
    perturbacoes = state.get("perturbacoes_ativas", [])
    quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbacoes
    contexto_rag = state.get("contexto_rag", [])

    nome = produto.get("nome", "Produto")
    categoria = _normalizar_categoria(produto.get("categoria", "geral"))
    tipo_validade = (produto.get("tipo_validade") or "consumir_ate").lower()
    unidade = produto.get("unidade_medida", "un")
    vendas_medias = float(produto.get("vendas_medias_diarias", 0.0))
    quantidade = float(lote.get("quantidade_disponivel", 0.0))
    dias = int(lote.get("dias_para_expirar", 3))
    excesso = float(state.get("excesso_estimado", 0.0))
    cobertura = float(state.get("dias_cobertura_stock", 1.0))
    parecer_inv = state.get("parecer_inventario", "")

    if dias <= 0:
        if categoria in CATEGORIAS_PADARIA_PASTELARIA:
            return {
                "destino_proposto": "racao_animal",
                "razao_logistica": (
                    "Padaria/pastelaria em fim de vida útil encaminhada para instituição de transformação "
                    "em farinha para ração animal."
                ),
            }
        if tipo_validade == "preferencia_antes":
            return {
                "destino_proposto": "doacao_externa",
                "razao_logistica": (
                    "Artigo com data de durabilidade mínima ('Consumir de preferência antes de') "
                    "retirado de venda e encaminhado para doação externa."
                ),
            }
        return {
            "destino_proposto": "descarte_obrigatorio",
            "razao_logistica": "Lote expirado ('Consumir até'); retirada imediata obrigatória.",
        }

    if categoria in CATEGORIAS_PADARIA_PASTELARIA:
        lote_id = lote.get("lote_id", "")
        quota_sacos = 0.50 if (fecho_loja_2h or quebra_clientes) else 0.35
        elegivel_saco = eh_elegivel_saco_padaria(lote_id, quota_fracao=quota_sacos)

        if dias == 1 and fecho_loja_2h and quantidade > 0:
            if elegivel_saco:
                return {
                    "destino_proposto": "sacos_surpresa",
                    "razao_logistica": (
                        f"A <= 2h do fecho: fração prioritária ({int(quota_sacos * 100)}%) de "
                        f"{categoria} ({quantidade} {unidade}, 1d) alocada a Sacos Surpresa."
                    ),
                }
            return {
                "destino_proposto": "prateleira_desconto",
                "razao_logistica": (
                    f"A <= 2h do fecho: {categoria} ({quantidade} {unidade}, 1d) em prateleira com "
                    "desconto de fim de dia antes da valorização em ração animal."
                ),
            }

        if dias == 1 and not fecho_loja_2h and quantidade > 0:
            if elegivel_saco:
                return {
                    "destino_proposto": "sacos_surpresa",
                    "razao_logistica": (
                        f"Excedente de {categoria} ({quantidade} {unidade}, 1d) alocado à pool de "
                        f"Sacos Surpresa (quota dinâmica de {int(quota_sacos * 100)}%)."
                    ),
                }
            return {
                "destino_proposto": "prateleira_desconto",
                "razao_logistica": (
                    f"Excedente de {categoria} ({quantidade} {unidade}, 1d) mantido em prateleira com "
                    "desconto ESL progressivo para escoamento direto."
                ),
            }

        if dias == 2 and fecho_loja_2h and quantidade > 0 and elegivel_saco:
            return {
                "destino_proposto": "sacos_surpresa",
                "razao_logistica": (
                    f"A <= 2h do fecho: fração ({int(quota_sacos * 100)}%) de {categoria} "
                    f"({quantidade} {unidade}, 2d) alocada preventivamente a Sacos Surpresa."
                ),
            }

        return {
            "destino_proposto": "prateleira_desconto",
            "razao_logistica": "Padaria/pastelaria mantida em prateleira para escoamento com etiqueta ESL.",
        }

    # Capacidade estimada de escoamento em prateleira já contando com desconto ESL (ex.: 35%)
    elasticidade = float(produto.get("elasticidade_preco", 1.2))
    desc_ref_esl = 0.35 if dias <= 2 else 0.25
    procura_com_desconto = vendas_medias * (1.0 + desc_ref_esl * elasticidade) * max(1, dias)
    racio_excesso_real = quantidade / max(0.1, procura_com_desconto)

    # 1. Último dia de carne/pescado sem escoamento previsto -> Cozinha Interna
    if categoria in ["pescado", "carne"] and dias <= 1 and (racio_excesso_real > 1.35 or fecho_loja_2h):
        return {
            "destino_proposto": "cozinha_interna",
            "razao_logistica": (
                f"Último dia de vida útil ('Consumir até') em {categoria} com stock acima da venda prevista "
                f"mesmo com desconto ({quantidade} {unidade} vs. {procura_com_desconto:.1f} {unidade}); "
                "encaminhado para cozinha interna."
            ),
        }

    # 2. Doação externa IPSS apenas na última janela elegível (dias == 2) e perante excedente real
    fator_doacao_critica = 1.65 if categoria in ["laticinios", "charcutaria", "pescado", "carne"] else 2.0
    if excesso > 0 and dias == 2 and racio_excesso_real > fator_doacao_critica:
        return {
            "destino_proposto": "doacao_externa",
            "razao_logistica": (
                f"Excedente severo a 48h da validade ({quantidade} {unidade} vs. procura com ESL "
                f"{procura_com_desconto:.1f} {unidade}); encaminhado para doação IPSS."
            ),
        }

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and excesso > 0 and dias <= 2 and racio_excesso_real > 1.4:
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
- Procura prevista com desconto ESL: {procura_com_desconto:.1f} {unidade} | Parecer Inventário: {parecer_inv}

### Contexto Histórico e Sazonal (RAG):
{bloco_rag}

Regras obrigatórias:
- Prioriza SEMPRE 'prateleira_desconto' para maximizar receita; só uses 'doacao_externa' em último recurso quando o stock exceder muito a procura com desconto.
- Nunca escolhas 'sacos_surpresa' para categorias diferentes de 'padaria' ou 'pastelaria'.
- Nunca escolhas 'doacao_externa' para artigos 'Consumir até' com validade < 2 dias.
- Nunca escolhas 'racao_animal' para categorias diferentes de 'padaria' ou 'pastelaria'.
- Para 'carne' ou 'pescado' com validade <= 1 dia sem escoamento previsto, usa 'cozinha_interna'.
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