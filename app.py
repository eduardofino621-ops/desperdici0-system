from datetime import date

from dotenv import load_dotenv
import streamlit as st

load_dotenv(override=True)

from src.simulation.orchestrator import correr_simulacao
from src.ui.styles import injetar_css_global
from src.ui.tab_esl import renderizar_aba_esl
from src.ui.tab_operations import renderizar_aba_operacoes

st.set_page_config(
    page_title="Desperdíci0%",
    page_icon="♻️",
    layout="wide",
)

injetar_css_global()
st.title("♻️ Desperdíci0% - Simulação")


def _repor_dia_normal() -> None:
    st.session_state.select_perturbacao = "Nenhuma (Operação Normal)"
    st.session_state.perturbacoes_acumuladas = []
    st.session_state.historico_sessao = []
    st.session_state.resultados_simulacao = None


# ==============================================================================
# SIDEBAR: SIMULAÇÃO DE STRESS OPERACIONAL
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
    or st.session_state.get("cenario_ativo") != perturbacao
    or st.session_state.get("data_referencia_ativa") != date.today()
)

if precisa_recalcular:
    if perturbacao == "Nenhuma (Operação Normal)":
        st.session_state.perturbacoes_acumuladas = []
    elif perturbacao not in st.session_state.perturbacoes_acumuladas:
        st.session_state.perturbacoes_acumuladas.append(perturbacao)

    with st.spinner("A sincronizar base de dados em tempo real (500 lotes) e a executar agentes..."):
        estado = correr_simulacao(perturbacao, st.session_state.perturbacoes_acumuladas)
        snapshot = estado.pop("snapshot")
        for chave, valor in estado.items():
            st.session_state[chave] = valor
        st.session_state.setdefault("historico_sessao", []).append(snapshot)

if st.session_state.perturbacoes_acumuladas:
    st.sidebar.markdown("**⚡ Perturbações ativas no dia:**")
    for p_ativa in st.session_state.perturbacoes_acumuladas:
        st.sidebar.markdown(f"- {p_ativa}")

data_ativa = st.session_state.data_referencia_ativa
_, db_msg = st.session_state.db_status

st.info(
    f"📅 **Data Operacional (Tempo Real):** `{data_ativa.strftime('%d/%m/%Y')}` "
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
    renderizar_aba_operacoes()

with tab2:
    renderizar_aba_esl(data_ativa)