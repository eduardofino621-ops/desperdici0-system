import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from simulation.mock_db import INVENTARIO_MOCK
from agents.inventory_agent import agente_controlo_inventario
from agents.pricing_agent import agente_dynamic_pricing
from agents.logistics_agent import agente_logistica_doacao
from csp.constraints import validar_regras_csp

# Configuração da Página Streamlit
st.set_page_config(
    page_title="Desperdíci0% - Sistema Multiagente Orquestrado",
    page_icon="♻️",
    layout="wide"
)

st.title("♻️ Desperdíci0% - Orquestração Multiagente e Validação CSP")
st.markdown("Arquitetura modular: Agentes autónomos com LangChain/OpenRouter orquestrados no ciclo central.")

# Sidebar de stress
st.sidebar.header("🎛️ Painel de Simulação de Stress")
perturbacao = st.sidebar.selectbox(
    "Injetar Perturbação no Sistema:",
    [
        "Nenhuma (Operação Normal)",
        "Quebra Repentina de Clientes (-50% Procura)",
        "Feriado / Loja Fechada Amanhã (Urgência Máxima)",
        "Pico de Stock Excedente nas Frutas/Frescos"
    ],
    key="select_perturbacao"
)

simular_btn = st.sidebar.button("Executar Orquestração em Lote dos Agentes")

# Gestão de Estado da Aplicação
if "resultados_simulacao" not in st.session_state:
    st.session_state.resultados_simulacao = None
if "logs_orquestracao" not in st.session_state:
    st.session_state.logs_orquestracao = []

if simular_btn:
    with st.spinner("A orquestrar agentes e restrições CSP para todo o inventário..."):
        inv_copia = [dict(p) for p in INVENTARIO_MOCK]

        # Aplicar perturbações de stress selecionadas
        if perturbacao == "Quebra Repentina de Clientes (-50% Procura)":
            for p in inv_copia:
                p["historico_vendas_diarias"] = max(0.2, p["historico_vendas_diarias"] * 0.5)
        elif perturbacao == "Feriado / Loja Fechada Amanhã (Urgência Máxima)":
            for p in inv_copia:
                p["dias_para_validade"] = 1
        elif perturbacao == "Pico de Stock Excedente nas Frutas/Frescos":
            for p in inv_copia:
                if p["categoria"] in ["frescos", "fruta"]:
                    p["quantidade_kg"] *= 2.5

        resultados_lote = []
        logs_sessao = []
        logs_sessao.append(f"🚀 **[Orquestrador]** Ciclo iniciado. Contexto: *{perturbacao}*")

        for prod in inv_copia:
            logs_sessao.append(
                f"\n📦 **[Inventário]** A processar lote `{prod['id']}` ({prod['nome']}) — Validade: {prod['dias_para_validade']}d.")

            # 1. Agente de Inventário (LangChain/OpenRouter)
            res_inventario = agente_controlo_inventario({"produto_atual": prod})
            logs_sessao.append(f"🔍 **[Agente Inventário]** {res_inventario['parecer_inventario']}")

            # 2. Agente de Pricing (LangChain/OpenRouter)
            res_pricing = agente_dynamic_pricing({"produto_atual": prod})
            desc_proposto = res_pricing["desconto_proposto"]
            logs_sessao.append(f"🏷️ **[Agente Pricing]** {res_pricing['raciocinio_pricing']}")

            # 3. Agente de Logística
            res_logistica = agente_logistica_doacao({"produto_atual": prod})
            destino = res_logistica["destino_proposto"]
            logs_sessao.append(f"🚚 **[Agente Logística]** {res_logistica['razao_logistica']}")

            # 4. Módulo CSP (Decreto-Lei n.º 166/2013 e restrições operacionais)
            val_csp = validar_regras_csp(prod, desc_proposto, destino)

            if not val_csp["valido"]:
                for erro in val_csp["erros"]:
                    logs_sessao.append(f"🛡️ **[Módulo CSP / Regulador]** Veto aplicado: *{erro}*")
            else:
                logs_sessao.append(f"✅ **[Módulo CSP]** Conformidade legal validada com sucesso.")

            preco_final = prod["preco_base"] * (1 - val_csp["desconto_ajustado"])

            resultados_lote.append({
                "Produto": prod["nome"],
                "Categoria": prod["categoria"],
                "Validade (Dias)": prod["dias_para_validade"],
                "Preço Base": f"{prod['preco_base']:.2f}€",
                "Desconto Final": f"{int(val_csp['desconto_ajustado'] * 100)}%",
                "Preço Final": f"{preco_final:.2f}€",
                "Destino Final": val_csp["destino_ajustado"].upper().replace("_", " "),
                "Estado CSP": "Aprovado" if val_csp["valido"] else "Ajustado"
            })

        logs_sessao.append("\n🏁 **[Orquestrador]** Ciclo concluído com sucesso. Etiquetas ESL atualizadas.")

        st.session_state.resultados_simulacao = resultados_lote
        st.session_state.logs_orquestracao = logs_sessao
        st.session_state.inventario_simulado = inv_copia

# Layout Principal em Abas
tab1, tab2, tab3 = st.tabs(
    ["📊 Dashboard", "🏷️ Etiquetas Eletrónicas (ESL)", "⚙️ Raciocínio dos Agentes"])

with tab1:
    st.subheader("📦 Estado do Inventário Pós-Orquestração")
    if st.session_state.resultados_simulacao:
        df_res = pd.DataFrame(st.session_state.resultados_simulacao)
        st.markdown(df_res.to_html(index=False, classes="table table-striped table-bordered"), unsafe_allow_html=True)
    else:
        df_base = pd.DataFrame(INVENTARIO_MOCK)
        st.markdown(df_base.to_html(index=False, classes="table table-striped table-bordered"), unsafe_allow_html=True)
        st.info("ℹ️ Clica em **'Executar Orquestração em Lote dos Agentes'** na barra lateral para iniciar.")

with tab2:
    st.subheader("🏷️ Simulação Visual de Etiquetas Eletrónicas (ESL)")
    inv_para_esl = st.session_state.get("inventario_simulado", INVENTARIO_MOCK)
    num_cols = 3
    cols = st.columns(num_cols)

    for i, prod in enumerate(inv_para_esl):
        col_idx = i % num_cols
        with cols[col_idx]:
            preco_base = prod["preco_base"]
            dias = prod["dias_para_validade"]
            desc = 0.65 if dias <= 1 else (0.35 if dias == 2 else 0.15)
            preco_promocional = preco_base * (1 - desc)

            st.markdown(f"""
            <div style="border: 2px solid #e0e0e0; padding: 15px; border-radius: 10px; text-align: center; background-color: #ffffff; margin-bottom: 15px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                <h4 style="margin-bottom: 5px; color: #1f2937;">{prod['nome']}</h4>
                <span style="background-color: #fee2e2; color: #b91c1c; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">Validade: {dias} dia(s)</span>
                <p style="font-size: 10px; background-color: #f3f4f6; padding: 4px; border-radius: 4px; font-family: monospace; margin-top: 8px;">2D: {prod['codigo_2d']}</p>
                <hr style="margin: 10px 0;">
                <p style="font-size: 13px; text-decoration: line-through; color: #6b7280; margin-bottom: 0;">Preço Base: {preco_base:.2f}€</p>
                <h2 style="color: #ef4444; margin: 0;">{preco_promocional:.2f}€</h2>
                <p style="font-size: 11px; background-color: #fef3c7; color: #92400e; padding: 3px; border-radius: 4px; margin-top: 5px;">Desconto Lote: -{int(desc * 100)}%</p>
            </div>
            """, unsafe_allow_html=True)

with tab3:
    st.subheader("⚙️ Registo de Execução do Orquestrador e Agentes")
    if st.session_state.logs_orquestracao:
        log_container = st.container(height=500)
        with log_container:
            for linha in st.session_state.logs_orquestracao:
                st.markdown(linha)
    else:
        st.info("ℹ️ Executa a simulação na barra lateral para ver o fluxo orquestrado em tempo real.")