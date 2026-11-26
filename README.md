# Desperdíci0% — Sistema Multiagente para Dynamic Pricing e Otimização de Doação

> **Resumo do Projeto:** Sistema multiagente desenvolvido para combater o desperdício alimentar em superfícies comerciais, combinando **Dynamic Pricing** em tempo real (com Etiquetas Eletrónicas de Prateleira — ESL), **procura local** para otimização de curvas de desconto, **RAG (Retrieval-Augmented Generation)** com regras operacionais e histórico SQLite, e **validação CSP (Constraint Satisfaction Problems)** para encaminhamento atempado de excedentes.

---

## 🏗️ Arquitetura e Pipeline Multiagente

O sistema orquestra uma arquitetura multiagente sobre um catálogo de **200 produtos** e **500 lotes** com rastreabilidade **GS1 DataMatrix** e base de dados temporal **SQLite**, garantindo o cumprimento estrito de restrições operacionais e legais (CSP). É composto por três agentes especializados executados em cadeia para lotes críticos ($\le 5$ dias de validade):

1. **Agente de Controlo de Inventário (`src/agents/inventory_agent.py`):**
   - Rastreia validades, regimes de conservação (`Consumir até` vs. `De preferência antes de`), PUM (Preço por Unidade de Medida), cobertura de stock e excesso previsto face à procura média ajustada pela meteorologia e perturbações.
   - Consulta o **Motor RAG** (`src/rag/retriever.py`) para recuperar regras sazonais, meteorológicas, de ciclo mensal e padrões históricos do SQLite.
2. **Agente de Logística e Doação (`src/agents/logistics_agent.py`):**
   - Decide o destino operacional mais adequado para cada lote: `prateleira_desconto`, `sacos_surpresa`, `cozinha_interna`, `doacao_externa`, `racao_animal` ou `descarte_obrigatorio`.
   - Gere a alocação dinâmica de padaria de véspera para **Sacos Surpresa** equilibrados ($0{,}50\text{ kg}$) e o desvio de excedentes críticos para IPSS, cozinha interna ou valorização em ração animal.
3. **Agente de Dynamic Pricing (`src/agents/pricing_agent.py`):**
   - Implementa **Search in Complex Environments** (*Random-Restart Hill Climbing* em `otimizar_curva_precos_3dias`) para explorar trajetórias de desconto nos últimos 3 dias ($D-3, D-2, D-1$), encontrando o equilíbrio entre atratividade para o consumidor, preservação de margem e custo de desperdício evitado.
   - Integra propostas estruturadas via LLM (OpenRouter / DeepSeek) com fallback determinístico baseado em elasticidade-preço, pisos progressivos FEFO e contexto RAG.

---

## ⚙️ Regras Críticas, CSP e Base de Conhecimento (RAG)

Para garantir conformidade legal (incluindo proteção contra vendas com prejuízo/dumping) e segurança alimentar, todas as decisões passam pelo validador **CSP (`src/csp/constraints.py`)**:

- **Teto Global de Desconto:** Os descontos de validade nunca excedem os **70%** sobre o PVP.
- **Segurança Alimentar (`Consumir até` vs. `Preferência antes`):** Produtos com data-limite de consumo (como carne e pescado frescos) nunca são vendidos após a validade; no último dia útil sem escoamento previsto seguem para cozinha interna ou valorização elegível, sem doação externa a $\le 24\text{h}$.
- **Pisos de Recuperação e Margem:** Respeita margens mínimas em operação normal e pisos críticos face ao custo de descarte.
- **Gestão de Padaria e Sacos Surpresa:** Pão de véspera combina desconto progressivo em prateleira com agregação em **Sacos Surpresa** de $0{,}50\text{ kg}$ (quota dinâmica de 35% a 50% consoante a proximidade do fecho ou quebra de procura) e encaminhamento final para farinha de ração animal.
- **Memória RAG Híbrida (`src/rag/retriever.py`):** Combina regras indexadas (meteorologia, ciclo salarial mensal, fins de semana, feriados, Natal, Páscoa, Santos Populares, férias de agosto e segurança alimentar) com telemetria histórica agregada a partir de `data/desperdicio.db` (SQLite).

---

## 🚀 Instalação e Configuração

Certifique-se de que tem o **Python 3.10+** instalado no seu sistema.

```bash
# 1. Clonar o repositório
git clone https://github.com/eduardofino621-ops/desperdici0-system.git
cd desperdici0-system

# 2. Criar e ativar o ambiente virtual
python -m venv venv
# No Windows (PowerShell):
venv\Scripts\Activate.ps1
# No macOS / Linux:
source venv/bin/activate

# 3. Instalar as dependências necessárias
pip install langchain langchain-openai langgraph streamlit pandas pydantic streamlit-aggrid altair scikit-learn qrcode[pil] pytest
```

*(Opcional)* Para ativar o raciocínio generativo dos agentes via OpenRouter, defina a variável de ambiente:

```bash
# Windows (PowerShell)
$env:OPENROUTER_API_KEY="sua_chave_openrouter"

# macOS / Linux
export OPENROUTER_API_KEY="sua_chave_openrouter"
```
*(Sem esta chave, o sistema opera integralmente em modo determinístico local com otimização Hill Climbing e regras RAG.)*

---

## 💻 Executar a Aplicação (Dashboard de Simulação)

O dashboard desenvolvido em **Streamlit** permite monitorizar o inventário em tempo real, inspecionar a justificativa de cada agente e o parecer CSP por lote, simular meteorologia (tempo real em Coimbra ou cenários simulados) e injetar perturbações operacionais:

```bash
streamlit run app.py
```

### Funcionalidades Principais do Dashboard
- **Simulação em Tempo Real e Perturbações:** Injeção de cenários como *A menos de 2 horas de fechar a loja*, *Quebra Repentina de Clientes (-50% Procura)*, *Feriado / Loja Fechada Amanhã* e *Pico de Stock Excedente em Frutas e Carne*.
- **Simulação Acelerada Multi-Dia (2, 5 ou 7 dias):** Simula a evolução diária com perturbações e clima variados e executa uma **comparação direta (benchmark)** contra o modelo operacional tradicional (**Lidl** — descontos DLL de 30% / último dia 50%, sacos de padaria e regras padrão) sobre o mesmo catálogo e lotes iniciais.
- **Análise por Categoria e Destinos:** Visualização comparativa em **Altair** do desperdício evitado e da distribuição entre *Vendido (Desconto/Saco)*, *Doação / Cozinha* e *Ração / Valorização*.
- **Explorador RAG e Histórico de Perturbações:** Consulta direta na barra lateral às regras indexadas e aos registos históricos persistidos em SQLite.

---

## 🧪 Testes Automatizados

O projeto inclui testes unitários e de simulação na pasta `tests/` (`test_agents.py`, `test_rag.py` e `test_simulation.py`), validando agentes, otimização de curvas de desconto, normalização/recuperação RAG e invariantes da simulação multi-dia.

Para executar a suíte de testes:

```bash
pytest -v
```
---

## 📊 Métricas de Avaliação

O desempenho do sistema é medido através da **Taxa de Salvamento (TS)** em massa ($\text{kg}$), complementada pela **Taxa de Desperdício Global**, **Custo Direto de Desperdício Evitado (€)** e **Receita Total de Vendas (€)**:

- **Fórmula:** `TS = ((QVD + QD + QR) / QTAR) × 100`
- **Legenda:**
  - `QVD` = Quantidade Vendida com Desconto / Sacos Surpresa ($\text{kg}$)
  - `QD` = Quantidade Doada / Cozinha Interna ($\text{kg}$)
  - `QR` = Quantidade Reaproveitada / Ração Animal ($\text{kg}$)
  - `QTAR` = Quantidade Total de Alimentos em Risco ($\text{kg}$)
- **Objetivo:** Alcançar uma Taxa de Salvamento superior a **90%**, preservando a receita comercial face à baseline tradicional.

---

## 👥 Autores

- Eduardo Coelho Fino (DEI-FCT, Universidade de Coimbra)
- Glória Costa Guimarães (DEI-FCT, Universidade de Coimbra)