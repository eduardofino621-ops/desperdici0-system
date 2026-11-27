from datetime import date

from dotenv import load_dotenv
import streamlit as st

load_dotenv(override=True)

from src.simulation.orchestrator import correr_simulacao
from src.ui.components import formatar_meteo_rotulo
from src.ui.styles import injetar_css_global
from src.ui.tab_esl import renderizar_aba_esl
from src.ui.tab_operations import (
    renderizar_aba_operacoes,
    renderizar_explorador_rag,
    renderizar_resultados_acelerada,
    renderizar_simulador_acelerada_sidebar,
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
    st.session_state.perturbacoes_registadas = []
    st.session_state.historico_sessao = []
    st.session_state.pagina_decisoes = 0
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

simular_btn = st.sidebar.button("▶️ Orquestração dos Agentes", type="primary", width="stretch")

# ==============================================================================
# GESTÃO DE ESTADO E ORQUESTRAÇÃO
# ==============================================================================
st.session_state.setdefault("resultados_simulacao", None)
st.session_state.setdefault("perturbacoes_acumuladas", [])
st.session_state.setdefault("perturbacoes_registadas", [])
st.session_state.setdefault("historico_sessao", [])
st.session_state.setdefault("pagina_decisoes", 0)

eh_arranque_inicial = (
    not st.session_state.resultados_simulacao  # CORRIGIDO: apanha None e lista vazia
    or st.session_state.get("data_referencia_ativa") != date.today()
)
precisa_recalcular = eh_arranque_inicial or simular_btn

if precisa_recalcular:
    eh_perturbacao_op = perturbacao != "Nenhuma (Operação Normal)"
    eh_meteo_simulada = modo_meteo != "Automático (Tempo Real - Coimbra)"
    eh_nova_perturbacao = (not eh_arranque_inicial) and (eh_perturbacao_op or eh_meteo_simulada)

    if eh_perturbacao_op and perturbacao not in st.session_state.perturbacoes_acumuladas:
        st.session_state.perturbacoes_acumuladas.append(perturbacao)

    cenario_exec = perturbacao if eh_perturbacao_op else (
        "Alteração Meteorológica" if eh_meteo_simulada else "Nenhuma (Operação Normal)"
    )

    with st.spinner("A sincronizar base de dados em tempo real (500 lotes) e a executar agentes..."):
        estado = correr_simulacao(
            cenario_exec,
            st.session_state.perturbacoes_acumuladas,
            modo_meteo=modo_meteo,
        )
        snapshot = estado.pop("snapshot")
        snapshot["resultados_simulacao"] = estado["resultados_simulacao"]
        snapshot["logs_por_lote"] = estado["logs_por_lote"]
        snapshot["sacos_surpresa_lista"] = estado["sacos_surpresa_lista"]
        for chave, valor in estado.items():
            st.session_state[chave] = valor
        st.session_state["modo_meteo_ativo"] = modo_meteo
        st.session_state.pop("ultima_chave_cenario", None)  # CORRIGIDO: não apagar resultados novos

        if eh_arranque_inicial or not st.session_state.historico_sessao:
            st.session_state.historico_sessao = [snapshot]
            st.session_state.pagina_decisoes = 0
        elif eh_nova_perturbacao:
            num_pert = len(st.session_state.perturbacoes_registadas) + 1
            meteo_tipo, meteo_desc = formatar_meteo_rotulo(snapshot.get("meteorologia"))
            st.session_state.perturbacoes_registadas.append({
                "numero": num_pert,
                "descricao": cenario_exec,
                "meteo_tipo": meteo_tipo,
                "meteo_desc": meteo_desc,
            })
            snapshot["numero_perturbacao"] = num_pert
            snapshot["descricao_perturbacao"] = cenario_exec
            st.session_state.historico_sessao.append(snapshot)
            st.session_state.pagina_decisoes = len(st.session_state.historico_sessao) - 1
        else:
            # Reexecução sem nova perturbação/clima simulado: atualiza o último snapshot ativo
            ultimo = st.session_state.historico_sessao[-1]
            if "numero_perturbacao" in ultimo:
                snapshot["numero_perturbacao"] = ultimo["numero_perturbacao"]
                snapshot["descricao_perturbacao"] = ultimo["descricao_perturbacao"]
            st.session_state.historico_sessao[-1] = snapshot

# Bloco condicional: só aparece após existir pelo menos 1 perturbação injetada
if st.session_state.perturbacoes_registadas:
    st.sidebar.markdown("**⚡ Perturbações Ativas do Dia:**")
    for p_reg in st.session_state.perturbacoes_registadas:
        st.sidebar.markdown(
            f"**#{p_reg['numero']}** {p_reg['descricao']}  \n"
            f"<span style='font-size:12px;opacity:0.85;'>🌦️ Meteorologia ({p_reg['meteo_tipo']}): {p_reg['meteo_desc']}</span>",
            unsafe_allow_html=True,
        )
    st.sidebar.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
    st.sidebar.button(
        "🗑️ Repor Dia (Operação Normal)",
        key="btn_repor_dia",
        on_click=_repor_dia_normal,
        width="stretch",
    )

# Ferramentas auxiliares na barra lateral
st.sidebar.divider()
renderizar_simulador_acelerada_sidebar()
renderizar_explorador_rag()

data_ativa = st.session_state.data_referencia_ativa
st.info(f"📅 **Data Operacional:** `{data_ativa.strftime('%d/%m/%Y')}`")

# ==============================================================================
# ABAS PRINCIPAIS
# ==============================================================================
tab1, tab2 = st.tabs([
    "📊 Dashboard de Operações (200 Artigos)",
    "🏷️ Etiquetas Eletrónicas (ESL)",
])

with tab1:
    renderizar_resultados_acelerada()
    renderizar_aba_operacoes()

with tab2:
    renderizar_aba_esl(data_ativa)