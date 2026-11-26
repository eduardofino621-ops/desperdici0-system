import math
import os
import random

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

TETO_DESCONTO_GLOBAL = 0.70


class PropostaPricing(BaseModel):
    desconto_proposto: float = Field(
        ge=0.0,
        le=TETO_DESCONTO_GLOBAL,
        description=(
            "Desconto decimal total entre 0.0 (0%) e 0.70 (70%). "
            "Ex: 0.35 para 35% de desconto."
        ),
    )
    raciocinio_pricing: str = Field(
        description=(
            "Justificação financeira e comercial concisa (máximo 2 frases) explicando o desconto "
            "face à elasticidade, custo, margem e contexto RAG."
        )
    )


def _calcular_pum(preco: float, produto: dict) -> str:
    conteudo = produto.get("conteudo_liquido", 1.0)
    un_ref = produto.get("unidade_referencia", produto.get("unidade_medida", "un"))
    pum = preco / max(0.0001, conteudo)
    return f"{pum:.2f} €/{un_ref}"

def otimizar_curva_precos_3dias(
    produto: dict,
    lote: dict,
    piso_minimo: float = 0.0,
    teto_maximo: float = TETO_DESCONTO_GLOBAL,
    fator_contexto_procura: float = 1.0,
    iteracoes: int = 80,
) -> dict:
    """
    Search in Complex Environments (Random-Restart Hill Climbing):
    Explora combinações de curvas de desconto (D-3, D-2, D-1) para maximizar
    a margem líquida esperada e minimizar o desperdício residual.
    """
    pvp = float(produto.get("pvp", 0.0))
    custo_aq = float(produto.get("custo_aquisicao", 0.0))
    custo_desc = float(produto.get("custo_descarte", 0.0))
    vendas_base = float(produto.get("vendas_medias_diarias", 1.0)) * fator_contexto_procura
    elast = float(produto.get("elasticidade_preco", 1.2))
    qtd_inicial = float(lote.get("quantidade_disponivel", 0.0))
    dias_restantes = max(1, min(3, int(lote.get("dias_para_expirar", 1))))

    if pvp <= 0 or qtd_inicial <= 0:
        return {"desconto_hoje": piso_minimo, "curva": [piso_minimo], "score": 0.0}

    # Grelha discreta de descontos (passos de 5%)
    niveis = [
        round(piso_minimo + 0.05 * i, 2)
        for i in range(int(round((teto_maximo - piso_minimo) / 0.05)) + 1)
    ]
    if not niveis:
        niveis = [round(piso_minimo, 2)]

    def avaliar_curva(curva: list[float]) -> float:
        stock = qtd_inicial
        receita = 0.0
        vendido_total = 0.0
        for d in curva:
            if stock <= 0:
                break
            preco = pvp * (1.0 - d)
            procura_dia = vendas_base * (1.0 + d * elast)
            vendido = min(stock, procura_dia)
            receita += vendido * preco
            vendido_total += vendido
            stock -= vendido

        # Lucro bruto das unidades vendidas menos prejuízo total das unidades que sobram (lixo)
        margem_realizada = receita - (vendido_total * custo_aq)
        perda_desperdicio = stock * (custo_aq + custo_desc)
        # Pequena penalização por descontos desnecessários quando o stock já escoa
        penalizacao_desconto = sum(curva) * 0.15 * pvp
        return margem_realizada - perda_desperdicio - penalizacao_desconto

    rng = random.Random(f"{lote.get('lote_id', '')}-{dias_restantes}")
    melhor_curva = [niveis[0]] * dias_restantes
    melhor_score = avaliar_curva(melhor_curva)

    # Procura local com reinícios aleatórios (Search in Complex Environments)
    for _ in range(iteracoes):
        # Gera estado inicial válido (curva não decrescente ao longo dos dias)
        candidato = sorted(rng.choice(niveis) for _ in range(dias_restantes))
        score_atual = avaliar_curva(candidato)

        # Hill-climbing na vizinhança (±5% num dos dias)
        melhorou = True
        while melhorou:
            melhorou = False
            for idx in range(dias_restantes):
                for delta in (-0.05, 0.05):
                    novo_val = round(candidato[idx] + delta, 2)
                    if novo_val < niveis[0] or novo_val > niveis[-1]:
                        continue
                    vizinho = list(candidato)
                    vizinho[idx] = novo_val
                    # Mantém progressividade temporal (desconto sobe ou mantém à medida que expira)
                    if vizinho != sorted(vizinho):
                        continue
                    s_viz = avaliar_curva(vizinho)
                    if s_viz > score_atual + 1e-6:
                        candidato = vizinho
                        score_atual = s_viz
                        melhorou = True

        if score_atual > melhor_score:
            melhor_score = score_atual
            melhor_curva = candidato

    return {
        "desconto_hoje": melhor_curva[0],
        "curva": melhor_curva,
        "score": round(melhor_score, 2),
    }

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
            {},
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
    fecho_loja_2h = state.get("fecho_loja_2h", False)

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
            ),
        }

    piso_progressivo = desconto_campanha
    if destino_proposto in ["prateleira_desconto", "sacos_surpresa"]:
        if categoria == "padaria" and dias <= 1:
            piso_pao = 0.40 if fecho_loja_2h else 0.25
            piso_progressivo = min(TETO_DESCONTO_GLOBAL, max(desconto_campanha + 0.05, piso_pao))
        elif excesso_estimado > 0 or destino_proposto == "sacos_surpresa":
            if dias <= 1:
                if categoria == "laticinios":
                    piso_progressivo = min(0.45, max(desconto_campanha + 0.10, 0.35))
                elif categoria == "mercearia":
                    piso_progressivo = min(0.50, max(desconto_campanha + 0.10, 0.35))
                elif categoria == "bebidas":
                    piso_progressivo = min(0.45, max(desconto_campanha + 0.10, 0.30))
                else:
                    piso_progressivo = min(0.55, max(desconto_campanha + 0.15, 0.40))
            elif dias == 2:
                piso_2d = 0.25 if categoria == "mercearia" else (
                    0.25 if categoria in ["laticinios", "charcutaria", "fruta"] else 0.20
                )
                piso_progressivo = min(desconto_max_margem, max(desconto_campanha + 0.05, piso_2d))
            elif dias == 3 and categoria in ["mercearia", "laticinios", "charcutaria", "fruta"]:
                piso_3d = 0.20 if categoria == "mercearia" else 0.15
                piso_progressivo = min(desconto_max_margem, max(desconto_campanha + 0.05, piso_3d))

    bloco_rag = (
        "\n".join(f"- [{c['id']}] {c['texto']}" for c in contexto_rag)
        if contexto_rag
        else "Sem regras sazonais ou históricas adicionais."
    )

    ids_rag = {c["id"] for c in contexto_rag}
    fator_ctx = (
        0.75
        if ({"Ciclo Mensal: Fim do Mês (Contenção)", "Meteorologia: Dia de Chuva / Temporal"} & ids_rag)
        else 1.0
    )
    teto_busca = TETO_DESCONTO_GLOBAL if dias <= 1 else max(piso_progressivo, desconto_max_margem)
    resultado_busca = otimizar_curva_precos_3dias(
        produto=produto,
        lote=lote,
        piso_minimo=piso_progressivo,
        teto_maximo=teto_busca,
        fator_contexto_procura=fator_ctx,
    )
    desconto_busca = resultado_busca["desconto_hoje"]
    curva_str = " → ".join(f"{int(d * 100)}%" for d in resultado_busca["curva"])

    api_key = os.environ.get("OPENROUTER_API_KEY")

    if api_key:
        try:
            llm = ChatOpenAI(
                model="deepseek/deepseek-chat",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.2,
            ).with_structured_output(PropostaPricing)

            prompt = f"""
    És o Agente de Dynamic Pricing de uma superfície comercial.
    Define o desconto total ótimo (em decimal de 0.0 a {TETO_DESCONTO_GLOBAL:.2f} sobre o PVP) para escoar este lote específico sem destruir margem desnecessariamente.

    ### Dados Financeiros e de Procura:
    - Artigo: {nome} (Lote: {lote_id} | Categoria: {categoria})
    - PVP Normal: {pvp:.2f} €/{unidade} (PUM normal: {_calcular_pum(pvp, produto)})
    - Desconto de campanha geral já ativo no artigo: {desconto_campanha * 100:.0f}%
    - Piso mínimo obrigatório para este lote (FEFO): {piso_progressivo * 100:.0f}%
    - Sugestão da busca local (3 dias): {desconto_busca * 100:.0f}% (Curva: {curva_str})
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
    1. O desconto proposto NUNCA pode ser inferior ao piso progressivo ({piso_progressivo:.2f}) quando há excesso de stock a <= 3 dias ou padaria a <= 1 dia, garantindo diferenciação clara face à campanha ({desconto_campanha:.2f}).
    2. Se não houver excesso previsto e faltarem >= 4 dias, propõe apenas o desconto de campanha ({desconto_campanha:.2f}).
    3. Usa a elasticidade ({elasticidade}), a sugestão da busca local ({desconto_busca:.2f}) e o contexto RAG (ciclo do mês, meteorologia, épocas festivas) para calibrar o desconto acima do piso sem comprometer a margem.
    4. Na tua justificação (`raciocinio_pricing`), refere explicitamente o PVP original ({pvp:.2f}€) e o preço final resultante após o desconto proposto.
    """
            proposta: PropostaPricing = llm.invoke([
                SystemMessage(
                    content="És um agente especialista em Revenue Management e Dynamic Pricing retalhista. Responde com rigor matemático."
                ),
                HumanMessage(content=prompt),
            ])

            desc = min(TETO_DESCONTO_GLOBAL, round(max(piso_progressivo, proposta.desconto_proposto), 2))
            if (excesso_estimado > 0 or dias <= 2) and desc > 0 and desconto_campanha > 0 and desc <= desconto_campanha:
                desc = min(TETO_DESCONTO_GLOBAL, round(desconto_campanha + 0.05, 2))
            preco_final = round(pvp * (1 - desc), 2)

            return {
                "desconto_proposto": desc,
                "preco_proposto": preco_final,
                "pum_proposto": _calcular_pum(preco_final, produto),
                "raciocinio_pricing": proposta.raciocinio_pricing,
            }

        except Exception:
            pass

    bonus_rag = (
        0.05
        if excesso_estimado > 0
           and ({"Ciclo Mensal: Fim do Mês (Contenção)", "Meteorologia: Dia de Chuva / Temporal"} & ids_rag)
        else 0.0
    )
    if excesso_estimado <= 0 and dias > 2:
        desc_proposto = desconto_campanha
    elif excesso_estimado > 0 and dias <= 3:
        desc_proposto = round(min(teto_busca, max(piso_progressivo, desconto_busca + bonus_rag)), 2)
    else:
        fator_aceleracao = (quantidade / max(0.1, vendas_medias * max(1, dias))) - 1.0
        desc_necessario = max(0.10, (fator_aceleracao / max(0.5, elasticidade)) + bonus_rag)
        teto_desconto = TETO_DESCONTO_GLOBAL if dias <= 1 else max(0.15, desconto_max_margem)
        desc_proposto = round(max(piso_progressivo, min(desc_necessario, teto_desconto)), 2)

    if desc_proposto > 0 and desconto_campanha > 0 and desc_proposto <= desconto_campanha:
        desc_proposto = min(TETO_DESCONTO_GLOBAL, round(desconto_campanha + 0.05, 2))

    preco_final = round(pvp * (1 - desc_proposto), 2)
    pvp_fmt = f"{pvp:.2f}€".replace(".", ",")
    preco_fmt = f"{preco_final:.2f}€".replace(".", ",")
    pum_fmt = _calcular_pum(preco_final, produto).replace(".", ",")
    info_curva = f" Curva ({dias}d): {curva_str}." if dias <= 3 and excesso_estimado > 0 else ""
    return {
        "desconto_proposto": desc_proposto,
        "preco_proposto": preco_final,
        "pum_proposto": _calcular_pum(preco_final, produto),
        "raciocinio_pricing": (
            f"Desconto progressivo FEFO de {int(desc_proposto * 100)}% sobre o PVP de {pvp_fmt} "
            f"(preço proposto: {preco_fmt}, PUM: {pum_fmt}) aplicado para {dias} dia(s) de validade "
            f"e excesso de {excesso_estimado} {unidade}.{info_curva}"
        ),
    }