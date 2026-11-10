import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Carregar variáveis de ambiente do ficheiro .env
load_dotenv()

from simulation.mock_db import INVENTARIO_MOCK
from csp.constraints import validar_regras_csp
from agents.inventory_agent import agente_controlo_inventario
from agents.pricing_agent import agente_dynamic_pricing
from agents.logistics_agent import agente_logistica_doacao

# Configuração da Página Streamlit
st.set_page_config(
    page_title="Desperdíci0% - Sistema Multiagente",
    page_icon="♻️",
    layout="wide"
)

st.title("♻️ Desperdíci0% - Sistema Multiagente para Dynamic Pricing e Doações")
st.markdown(
    "Plataforma inteligente de gestão de inventário em tempo real, Etiquetas Eletrónicas (ESL) e Otimização de Doações com códigos 2D[cite: 1, 2].")

# Sidebar para Simulação de Stress e Configurações
st.sidebar.header("🎛️ Painel de Controlo da Loja")
perturbacao = st.sidebar.selectbox(
    "Injetar Perturbação no Sistema:",
    ["Nenhuma (Operação Normal)", "Quebra Repentina de Clientes (-50% Procura)",
     "Excesso de Stock Crítico (Validade < 24h)"]
)

# Verificar estado da API Key
api_key_status = "Ativa (OpenRouter/LLM conectado)" if os.environ.get(
    "OPENROUTER_API_KEY") else "Inativa (A usar regras heurísticas locais)"
st.sidebar.info(f"Estado da IA: {api_key_status}")

simular_btn = st.sidebar.button("Executar Ciclo de Decisão dos Agentes")

# Inicializar inventário no session_state do Streamlit
if "inventario" not in st.session_state:
    st.session_state.inventario = INVENTARIO_MOCK.copy()

# Layout Principal em Abas
tab1, tab2, tab3 = st.tabs(
    ["📊 Dashboard & Códigos 2D", "🏷️ Protótipo de Etiquetas (ESL)", "⚙️ Estado dos Agentes e CSP"])

with tab1:
    st.subheader("Inventário Atual com Suporte a Códigos de Barras 2D (GS1 DataMatrix)")
    st.markdown(
        "Cada artigo em risco possui um código 2D que codifica nativamente a referência do produto e a data de validade para leitura automática no POS[cite: 2].")

    inv_atual = st.session_state.inventario.copy()
    if perturbacao == "Quebra Repentina de Clientes (-50% Procura)":
        st.sidebar.warning("⚠️ Perturbação ativa: Quebra de clientes detetada!")
        for p in inv_atual:
            p["historico_vendas_diarias"] = max(0.5, p["historico_vendas_diarias"] * 0.5)

    df_inv = pd.DataFrame(inv_atual)
    st.dataframe(df_inv, use_container_width=True)

    if simular_btn:
        with st.spinner("A executar agentes multiagentes, raciocínio LLM e validação CSP..."):
            produto_alvo = inv_atual[0]

            # Simular estado inicial para os agentes
            estado_teste = {
                "produto_atual": produto_alvo,
                "inventario": inv_atual
            }

            # Executar Agente de Pricing (com suporte a LLM se chave ativa)
            res_pricing = agente_dynamic_pricing(estado_teste)
            desc_proposto = res_pricing.get("desconto_proposto", 0.30)

            # Executar Agente de Logística
            res_logistica = agente_logistica_doacao(res_pricing)
            destino = res_logistica.get("destino_proposto", "prateleira_desconto")

            # Validação CSP
            val_csp = validar_regras_csp(produto_alvo, desc_proposto, destino)

            st.success("Ciclo de decisão executado com sucesso pelos agentes!")

            col1, col2, col3 = st.columns(3)
            col1.metric("Produto Analisado", produto_alvo["nome"])
            col2.metric("Desconto Gerado", f"{int(val_csp['desconto_ajustado'] * 100)}%")
            col3.metric("Destino Final Decidido", destino.upper().replace("_", " "))

            if val_csp["erros"]:
                st.warning(f"⚠️ Restrições CSP Aplicadas: {val_csp['erros'][0]}")
            else:
                st.info("✅ Conformidade CSP Total: Nenhuma violação detetada[cite: 2].")

with tab2:
    st.subheader("🏷️ Simulação de Etiquetas Eletrónicas de Prateleira (ESL)")
    st.markdown("Visualização em tempo real dos preços refletidos nas prateleiras digitais da loja[cite: 2].")

    cols = st.columns(len(inv_atual))
    for i, prod in enumerate(inv_atual):
        with cols[i]:
            preco_base = prod["preco_base"]
            dias = prod["dias_para_validade"]
            desconto_estimado = 0.60 if dias == 1 else 0.30
            preco_promocional = preco_base * (1 - desconto_estimado)

            st.markdown(f"""
            <div style="border: 2px solid #e0e0e0; padding: 15px; border-radius: 10px; text-align: center; background-color: #fafafa;">
                <h4>{prod['nome']}</h4>
                <p style="color: gray; font-size: 12px;">Validade: {dias} dia(s)</p>
                <p style="font-size: 10px; background-color: #e2e8f0; padding: 2px; border-radius: 3px; font-family: monospace;">2D: {prod['codigo_2d']}</p>
                <hr>
                <p style="font-size: 14px; text-decoration: line-through; color: #888;">Preço Base: {preco_base:.2f}€</p>
                <h2 style="color: #d9534f; margin: 0;">{preco_promocional:.2f}€</h2>
                <p style="font-size: 11px; background-color: #ffefc4; padding: 3px; border-radius: 5px;">Desconto Lote: -{int(desconto_estimado * 100)}%</p>
            </div>
            """, unsafe_allow_html=True)

with tab3:
    st.subheader("⚙️ Estado dos Agentes Especializados e Conformidade Legal")
    st.markdown("""
    * **Agente de Controlo de Inventário:** Monitoriza em tempo real as datas de validade e o escoamento[cite: 2].
    * **Agente de Dynamic Pricing:** Ajusta curvas de desvalorização otimizadas para os últimos dias, integrando LLMs via OpenRouter[cite: 1, 2].
    * **Agente de Logística e Doação:** Coordena o redirecionamento interno e externo[cite: 2].
    * **Módulo CSP (Decreto-Lei n.º 166/2013):** Assegura o bloqueio de doações a menos de 48h e limites de desconto em frescos até 70%[cite: 2].
    """)