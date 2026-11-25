from datetime import date

from dotenv import load_dotenv
import streamlit as st

load_dotenv(override=True)

from src.simulation.orchestrator import correr_simulacao
from src.ui.styles import injetar_css_global
from src.ui.tab_esl import renderizar_aba_esl
from src.ui.tab_operations import (
    renderizar_aba_operacoes,
    renderizar_explorador_rag,
    renderizar_historico_perturbacoes_sidebar,
    renderizar_resultados_multidia,
    renderizar_simulador_multidia_sidebar,
)

st.set_page_config(
    page_title="Desperdíci0%",
    page_icon="♻️",
    layout="wide",
)

injetar_css_global()
st.title("♻️ Desperdíci0% - Simulação")


def _repor_dia_normal() -> None:
    st.session_state.select_perturbacao = "Nenhuma (Operação Normal)"
    st.session_state.select_meteo = "Automático (Tempo Real - Coimbra)"
    st.session_state.perturbacoes_acumuladas = []
    st.session_state.historico_sessao = []
    st.session_state.resultados_simulacao = None


# ==============================================================================
# SIDEBAR: SIMULAÇÃO DE STRESS OPERACIONAL E METEOROLOGIA
# ==============================================================================
st.sidebar.header("🎛️ Painel de Simulação de Stress")
perturbacao = st.sidebar.selectbox(
    "Injetar Perturbação no Sistema:",
    [
        "Nenhuma (Operação Normal)",
        "A menos de 2 horas de fechar a loja.",
        "Quebra Repentina de Clientes (-50% Procura)",
        "Feriado / Loja Fechada Amanhã (Urgência Máxima)",
        "Pico de Stock Excedente em Frutas e Carne",
    ],
    key="select_perturbacao",
)

modo_meteo = st.sidebar.selectbox(
    "🌦️ Contexto Meteorológico (Open-Meteo):",
    [
        "Automático (Tempo Real - Coimbra)",
        "Simular: Chuva Intensa / Temporal",
        "Simular: Calor Elevado (> 30°C)",
    ],
    key="select_meteo",
)

simular_btn = st.sidebar.button("▶️ Reexecutar Orquestração / Sincronizar DB", type="primary", width="stretch")
st.sidebar.button("🗑️ Repor Dia (Operação Normal)", on_click=_repor_dia_normal, width="stretch")

# ==============================================================================
# GESTÃO DE ESTADO E ORQUESTRAÇÃO
# ==============================================================================
st.session_state.setdefault("resultados_simulacao", None)
st.session_state.setdefault("perturbacoes_acumuladas", [])

precisa_recalcular = (
    st.session_state.resultados_simulacao is None
    or simular_btn
    or st.session_state.get("data_referencia_ativa") != date.today()
)

if precisa_recalcular:
    if perturbacao == "Nenhuma (Operação Normal)":
        st.session_state.perturbacoes_acumuladas = []
    elif perturbacao not in st.session_state.perturbacoes_acumuladas:
        st.session_state.perturbacoes_acumuladas.append(perturbacao)

    with st.spinner("A sincronizar base de dados em tempo real (500 lotes) e a executar agentes..."):
        estado = correr_simulacao(
            perturbacao,
            st.session_state.perturbacoes_acumuladas,
            modo_meteo=modo_meteo,
        )
        snapshot = estado.pop("snapshot")
        for chave, valor in estado.items():
            st.session_state[chave] = valor
        st.session_state["modo_meteo_ativo"] = modo_meteo
        st.session_state.setdefault("historico_sessao", []).append(snapshot)

if st.session_state.perturbacoes_acumuladas:
    st.sidebar.markdown("**⚡ Perturbações ativas no dia:**")
    for p_ativa in st.session_state.perturbacoes_acumuladas:
        st.sidebar.markdown(f"- {p_ativa}")

# Ferramentas auxiliares na barra lateral (abaixo do painel de stress)
st.sidebar.divider()
renderizar_historico_perturbacoes_sidebar()
renderizar_simulador_multidia_sidebar()
renderizar_explorador_rag()

data_ativa = st.session_state.data_referencia_ativa
_, db_msg = st.session_state.db_status
meteo_ativa = st.session_state.get("meteorologia_ativa", {})
meteo_desc = meteo_ativa.get("descricao", "N/A")
meteo_fonte = meteo_ativa.get("fonte", "")

st.info(
    f"📅 **Data Operacional:** `{data_ativa.strftime('%d/%m/%Y')}` "
    f"&nbsp;|&nbsp; 🌦️ **Meteorologia ({meteo_fonte}):** `{meteo_desc}` "
    f"&nbsp;|&nbsp; 🗄️ **Base de Dados (SQLite):** {db_msg}"
)

# ==============================================================================
# ABAS PRINCIPAIS
# ==============================================================================
tab1, tab2 = st.tabs([
    "📊 Dashboard de Operações (200 Artigos)",
    "🏷️ Etiquetas Eletrónicas (ESL)",
])

with tab1:
    renderizar_resultados_multidia()
    renderizar_aba_operacoes()

with tab2:
    renderizar_aba_esl(data_ativa)