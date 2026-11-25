import math
import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


class PropostaPricing(BaseModel):
    desconto_proposto: float = Field(
        ge=0.0,
        le=0.70,
        description="Desconto decimal total entre 0.0 (0%) e 0.70 (70%). Ex: 0.35 para 35% de desconto."
    )
    raciocinio_pricing: str = Field(
        description="Justificação financeira e comercial concisa (máximo 2 frases) explicando o desconto face à elasticidade, custo, margem e contexto RAG."
    )


def _calcular_pum(preco: float, produto: dict) -> str:
    conteudo = produto.get("conteudo_liquido", 1.0)
    un_ref = produto.get("unidade_referencia", produto.get("unidade_medida", "un"))
    pum = preco / max(0.0001, conteudo)
    return f"{pum:.2f} €/{un_ref}"


def agente_dynamic_pricing(state: dict) -> dict:
    """
    Agente autónomo de Dynamic Pricing alimentado por LangChain, OpenRouter e RAG.
    """
    lote = state.get("lote_atual", {})
    produto = state.get("produto_catalogo", {})

    if not produto and lote:
        catalogo = state.get("catalogo_produtos", [])
        produto = next(
            (p for p in catalogo if p.get("produto_id") == lote.get("produto_id")),
            {}
        )

    nome = produto.get("nome", "Produto")
    categoria = produto.get("categoria", "geral")
    unidade = produto.get("unidade_medida", "un")
    pvp = produto.get("pvp", 0.0)
    desconto_campanha = produto.get("desconto_campanha", 0.0)
    custo = produto.get("custo_aquisicao", 0.0)
    margem_minima = produto.get("margem_minima_pct", 0.05)
    custo_descarte = produto.get("custo_descarte", 0.0)
    vendas_medias = produto.get("vendas_medias_diarias", 0.0)
    elasticidade = produto.get("elasticidade_preco", 1.0)

    lote_id = lote.get("lote_id", "N/A")
    quantidade = lote.get("quantidade_disponivel", 0.0)
    dias = lote.get("dias_para_expirar", 3)

    parecer_inventario = state.get("parecer_inventario", "Sem parecer de inventário.")
    excesso_estimado = state.get("excesso_estimado", 0.0)
    destino_proposto = state.get("destino_proposto", "prateleira_desconto")
    razao_logistica = state.get("razao_logistica", "")
    contexto_rag = state.get("contexto_rag", [])

    preco_minimo_normal = round(custo * (1 + margem_minima), 2)
    desconto_max_margem = max(
        desconto_campanha,
        math.floor((1 - (preco_minimo_normal / max(0.01, pvp))) * 100) / 100,
    )
    prejuizo_se_expirar = round(custo + custo_descarte, 2)

    if destino_proposto in ["doacao_externa", "cozinha_interna", "racao_animal"]:
        return {
            "desconto_proposto": 0.0,
            "preco_proposto": pvp,
            "pum_proposto": _calcular_pum(pvp, produto),
            "raciocinio_pricing": (
                f"Sem desconto ESL aplicado: lote {lote_id} encaminhado para '{destino_proposto}' "
                f"pelo Agente de Logística ({razao_logistica})."
            )
        }

    piso_progressivo = desconto_campanha
    if excesso_estimado > 0 and destino_proposto in ["prateleira_desconto", "sacos_surpresa"]:
        if dias <= 1:
            piso_progressivo = min(0.65, max(desconto_campanha + 0.25, 0.45))
        elif dias == 2:
            piso_progressivo = min(desconto_max_margem, max(desconto_campanha + 0.10, 0.25))

    bloco_rag = (
        "\n".join(f"- [{c['id']}] {c['texto']}" for c in contexto_rag)
        if contexto_rag
        else "Sem regras sazonais ou históricas adicionais."
    )

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if api_key:
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.2
            ).with_structured_output(PropostaPricing)

            prompt = f"""
És o Agente de Dynamic Pricing de uma superfície comercial.
Define o desconto total ótimo (em decimal de 0.0 a 0.70 sobre o PVP) para escoar este lote específico sem destruir margem desnecessariamente.

### Dados Financeiros e de Procura:
- Artigo: {nome} (Lote: {lote_id} | Categoria: {categoria})
- PVP Normal: {pvp:.2f} €/{unidade} (PUM normal: {_calcular_pum(pvp, produto)})
- Desconto de campanha geral já ativo no artigo: {desconto_campanha * 100:.0f}%
- Piso mínimo obrigatório para este lote (FEFO): {piso_progressivo * 100:.0f}%
- Custo de Aquisição: {custo:.2f} €/{unidade}
- Margem mínima exigida (operação normal): {margem_minima * 100:.0f}% (Preço mínimo normal: {preco_minimo_normal:.2f} € -> desconto máx. s/ quebrar margem: {desconto_max_margem * 100:.0f}%)
- Custo de descarte se expirar: {custo_descarte:.2f} €/{unidade} (Prejuízo total por expiração: {prejuizo_se_expirar:.2f} €/{unidade})
- Elasticidade-preço da procura: {elasticidade} (Vendas médias normais: {vendas_medias} {unidade}/dia)

### Estado do Lote e Pareceres dos Outros Agentes:
- Stock disponível: {quantidade} {unidade} | Validade: {dias} dia(s) | Excesso estimado: {excesso_estimado} {unidade}
- Destino definido pela Logística: {destino_proposto} ({razao_logistica})
- Parecer do Inventário: "{parecer_inventario}"

### Contexto Histórico e Sazonal Recuperado (RAG):
{bloco_rag}

### Regras de Decisão:
1. O desconto proposto NUNCA pode ser inferior ao piso progressivo ({piso_progressivo:.2f}) quando há excesso de stock a <= 2 dias, garantindo diferenciação clara face à campanha ({desconto_campanha:.2f}).
2. Se não houver excesso previsto e faltarem >= 3 dias, propõe apenas o desconto de campanha ({desconto_campanha:.2f}).
3. Usa a elasticidade ({elasticidade}) e o contexto RAG (ciclo do mês, meteorologia, épocas festivas) para calibrar o desconto acima do piso sem comprometer a margem.
4. Na tua justificação (`raciocinio_pricing`), refere explicitamente o PVP original ({pvp:.2f}€) e o preço final resultante após o desconto proposto.
"""
            proposta: PropostaPricing = llm.invoke([
                SystemMessage(content="És um agente especialista em Revenue Management e Dynamic Pricing retalhista. Responde com rigor matemático."),
                HumanMessage(content=prompt)
            ])

            desc = round(max(piso_progressivo, proposta.desconto_proposto), 2)
            if (excesso_estimado > 0 or dias <= 2) and desc > 0 and desconto_campanha > 0 and desc <= desconto_campanha:
                desc = min(0.75, round(desconto_campanha + 0.05, 2))
            preco_final = round(pvp * (1 - desc), 2)

            return {
                "desconto_proposto": desc,
                "preco_proposto": preco_final,
                "pum_proposto": _calcular_pum(preco_final, produto),
                "raciocinio_pricing": proposta.raciocinio_pricing
            }

        except Exception:
            pass

    # Fallback determinístico sensibilizado pelo RAG
    ids_rag = {c["id"] for c in contexto_rag}
    bonus_rag = 0.05 if ({"CICLO-FIM-MES-02", "METEO-CHUVA-01"} & ids_rag) else 0.0

    if excesso_estimado <= 0 and dias > 2:
        desc_proposto = desconto_campanha
    else:
        fator_aceleracao = (quantidade / max(0.1, vendas_medias * max(1, dias))) - 1.0
        desc_necessario = max(0.10, (fator_aceleracao / max(0.5, elasticidade)) + bonus_rag)
        teto_desconto = 0.65 if dias <= 1 else max(0.15, desconto_max_margem)
        desc_proposto = round(max(piso_progressivo, min(desc_necessario, teto_desconto)), 2)
        if desc_proposto > 0 and desconto_campanha > 0 and desc_proposto <= desconto_campanha:
            desc_proposto = min(0.75, round(desconto_campanha + 0.05, 2))

    preco_final = round(pvp * (1 - desc_proposto), 2)
    pvp_fmt = f"{pvp:.2f}€".replace(".", ",")
    preco_fmt = f"{preco_final:.2f}€".replace(".", ",")
    pum_fmt = _calcular_pum(preco_final, produto).replace(".", ",")
    ref_rag = f" [Evidências RAG: {', '.join(c['id'] for c in contexto_rag)}]" if contexto_rag else ""
    return {
        "desconto_proposto": desc_proposto,
        "preco_proposto": preco_final,
        "pum_proposto": _calcular_pum(preco_final, produto),
        "raciocinio_pricing": (
            f"Desconto progressivo FEFO de {int(desc_proposto * 100)}% sobre o PVP de {pvp_fmt} "
            f"(preço proposto: {preco_fmt}, PUM: {pum_fmt}) aplicado para {dias} dia(s) de validade "
            f"e excesso de {excesso_estimado} {unidade}.{ref_rag}"
        )
    }