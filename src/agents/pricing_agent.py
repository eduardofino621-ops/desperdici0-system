import math
import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.agents.inventory_agent import _detetar_chuva_temporal
from src.csp.constraints import CATEGORIAS_PADARIA_PASTELARIA, _normalizar_categoria


class DecisaoPricing(BaseModel):
    desconto_proposto: float = Field(
        description="Percentagem de desconto entre 0.0 e 0.70 (ex.: 0.35 para 35%)."
    )
    raciocinio_pricing: str = Field(
        description="Justificação económica e de procura curta (máximo 2 frases)."
    )


def _calcular_teto_financeiro(
    pvp: float,
    custo: float,
    margem_minima: float,
    custo_descarte: float,
    dias: int,
) -> tuple[float, float]:
    """Devolve (teto_financeiro, preco_piso) alinhados com a Regra 8 do CSP."""
    if pvp <= 0 or dias <= 0:
        return 0.0, 0.0

    if dias > 1 and custo > 0:
        preco_piso = round(custo * (1.0 + margem_minima), 2)
        teto_fin = math.floor((1.0 - (preco_piso / pvp)) * 100) / 100.0
    else:
        preco_piso = round(max(custo_descarte, pvp * 0.15), 2)
        teto_fin = math.floor((1.0 - (preco_piso / pvp)) * 100) / 100.0

    return max(0.0, teto_fin), preco_piso


def _otimizar_desconto_curva(
    quantidade: float,
    vendas_medias: float,
    dias: int,
    elasticidade: float,
    pvp: float,
    custo: float,
    custo_descarte: float,
    desconto_campanha: float,
    teto_efetivo: float,
) -> float:
    """
    Pesquisa discreta (2.4.2 Search in Complex Environments) sobre a grelha [0.00..teto_efetivo]
    para maximizar a receita líquida esperada considerando elasticidade-preço e custo de descarte.
    """
    if pvp <= 0 or dias <= 0 or quantidade <= 0:
        return 0.0

    melhor_desc = 0.0
    melhor_utilidade = -1e12
    min_com_campanha = round(desconto_campanha + 0.05, 2) if desconto_campanha > 0 else 0.0

    passos = int(round(teto_efetivo * 100)) + 1
    for i in range(passos):
        d = round(i / 100.0, 2)
        if desconto_campanha > 0 and 0 < d < min_com_campanha - 1e-9:
            continue

        desc_efetivo = max(d, desconto_campanha)
        procura_prevista = vendas_medias * max(1, dias) * (1.0 + desc_efetivo * max(0.2, elasticidade))
        vendidas = min(quantidade, procura_prevista)
        sobra = max(0.0, quantidade - vendidas)

        preco_un = pvp * (1.0 - desc_efetivo)
        receita = vendidas * preco_un
        penalizacao_sobra = sobra * (custo + custo_descarte)
        utilidade = receita - penalizacao_sobra

        if utilidade > melhor_utilidade + 1e-6:
            melhor_utilidade = utilidade
            melhor_desc = d

    return melhor_desc


def agente_dynamic_pricing(state: dict) -> dict:
    """
    Agente autónomo de Dynamic Pricing alinhado com o CSP e com o contexto RAG.
    """
    lote = state.get("lote_atual", {})
    produto = state.get("produto_catalogo", {})
    destino = state.get("destino_proposto", "prateleira_desconto")
    fecho_loja_2h = bool(state.get("fecho_loja_2h", False))
    perturbacoes = state.get("perturbacoes_ativas", [])
    quebra_clientes = "Quebra Repentina de Clientes (-50% Procura)" in perturbacoes
    contexto_rag = state.get("contexto_rag", [])
    meteo = state.get("meteorologia")

    nome = produto.get("nome", "Produto")
    categoria = _normalizar_categoria(produto.get("categoria", "geral"))
    pvp = float(produto.get("pvp", 0.0))
    custo = float(produto.get("custo_aquisicao", 0.0))
    margem_minima = float(produto.get("margem_minima_pct", 0.05))
    custo_descarte = float(produto.get("custo_descarte", 0.0))
    desconto_campanha = float(produto.get("desconto_campanha", 0.0))
    elasticidade = float(produto.get("elasticidade_preco", 1.2))
    vendas_medias = float(produto.get("vendas_medias_diarias", 0.0))

    quantidade = float(lote.get("quantidade_disponivel", 0.0))
    dias = int(lote.get("dias_para_expirar", 3))
    excesso = float(state.get("excesso_estimado", 0.0))

    if dias <= 0 or destino in ["doacao_externa", "cozinha_interna", "racao_animal", "descarte_obrigatorio"]:
        return {
            "desconto_proposto": 0.0,
            "raciocinio_pricing": (
                f"Destino '{destino}' sem etiqueta ESL de venda ao público; desconto definido em 0%."
            ),
        }

    chuva_temporal = _detetar_chuva_temporal(meteo)

    teto_categoria = 0.70
    if categoria == "laticinios" and dias <= 1:
        teto_categoria = min(teto_categoria, 0.50)
    if chuva_temporal and not fecho_loja_2h and not quebra_clientes:
        teto_meteo = 0.30 if dias == 2 else (0.45 if dias <= 1 else 0.70)
        teto_categoria = min(teto_categoria, teto_meteo)

    teto_financeiro, preco_piso = _calcular_teto_financeiro(
        pvp=pvp,
        custo=custo,
        margem_minima=margem_minima,
        custo_descarte=custo_descarte,
        dias=dias,
    )
    teto_efetivo = min(teto_categoria, teto_financeiro)
    min_com_campanha = round(desconto_campanha + 0.05, 2) if desconto_campanha > 0 else 0.0

    if desconto_campanha > 0 and teto_efetivo + 1e-9 < min_com_campanha:
        return {
            "desconto_proposto": 0.0,
            "raciocinio_pricing": (
                f"Campanha ativa ({int(desconto_campanha * 100)}%) já atinge o teto permitido "
                f"({int(teto_efetivo * 100)}%); mantido preço de campanha sem desconto extra de validade."
            ),
        }

    if categoria in CATEGORIAS_PADARIA_PASTELARIA:
        if destino == "sacos_surpresa" or fecho_loja_2h:
            desc_padaria = 0.45
        elif dias == 1:
            desc_padaria = 0.25
        else:
            desc_padaria = 0.0

        if desc_padaria > 0:
            if desconto_campanha > 0:
                desc_padaria = max(desc_padaria, min_com_campanha)
            if desc_padaria > teto_efetivo + 1e-9:
                desc_padaria = 0.0 if desconto_campanha > 0 else teto_efetivo

        return {
            "desconto_proposto": round(desc_padaria, 2),
            "raciocinio_pricing": (
                f"Política de {categoria} ({dias}d, destino={destino}, fecho_2h={fecho_loja_2h}): "
                f"desconto ESL de {int(desc_padaria * 100)}%."
            ),
        }

    if excesso <= 0 and dias > 2 and not fecho_loja_2h:
        return {
            "desconto_proposto": 0.0,
            "raciocinio_pricing": (
                f"Rotação natural absorve o stock ({dias}d restantes sem excesso previsto); "
                "mantido preço de catálogo/campanha."
            ),
        }

    desc_otimo = _otimizar_desconto_curva(
        quantidade=quantidade,
        vendas_medias=vendas_medias,
        dias=dias,
        elasticidade=elasticidade,
        pvp=pvp,
        custo=custo,
        custo_descarte=custo_descarte,
        desconto_campanha=desconto_campanha,
        teto_efetivo=teto_efetivo,
    )

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key and excesso > 0:
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1,
            ).with_structured_output(DecisaoPricing)

            bloco_rag = (
                "\n".join(f"- [{c['id']}] {c['texto']}" for c in contexto_rag)
                if contexto_rag
                else "Sem contexto RAG adicional."
            )

            regra_campanha = (
                f"- Como há campanha ativa ({desconto_campanha * 100:.0f}%), devolve 0.0 ou um valor entre "
                f"{min_com_campanha:.2f} e {teto_efetivo:.2f}."
                if desconto_campanha > 0
                else f"- Devolve desconto_proposto entre 0.0 e {teto_efetivo:.2f}."
            )

            prompt = f"""
És o Agente de Dynamic Pricing de uma superfície comercial. Define o desconto ESL para este lote:
- Artigo: {nome} (Categoria: {categoria}) | PVP: {pvp:.2f}€ | Campanha ativa: {desconto_campanha * 100:.0f}%
- Stock: {quantidade} | Validade: {dias} dia(s) | Excesso estimado: {excesso}
- Elasticidade-preço: {elasticidade} | Sugestão analítica base: {desc_otimo * 100:.0f}%
- Teto máximo permitido (categoria + margem/piso {preco_piso:.2f}€): {teto_efetivo * 100:.0f}%

### Contexto Histórico e Sazonal (RAG):
{bloco_rag}

Regras obrigatórias:
{regra_campanha}
"""
            decisao: DecisaoPricing = llm.invoke([
                SystemMessage(content="Define descontos ótimos cumprindo estritamente os tetos e pisos financeiros."),
                HumanMessage(content=prompt),
            ])
            desc_llm = max(0.0, min(teto_efetivo, round(float(decisao.desconto_proposto), 2)))
            if desconto_campanha > 0 and 0 < desc_llm < min_com_campanha:
                desc_llm = min_com_campanha
            return {
                "desconto_proposto": desc_llm,
                "raciocinio_pricing": decisao.raciocinio_pricing,
            }
        except Exception:
            pass

    return {
        "desconto_proposto": desc_otimo,
        "raciocinio_pricing": (
            f"Otimização por elasticidade ({elasticidade}) e cobertura ({dias}d): "
            f"desconto ESL de {int(desc_otimo * 100)}% (teto {int(teto_efetivo * 100)}%)."
        ),
    }