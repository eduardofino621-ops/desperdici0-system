# ♻️ Desperdíci0% — Sistema Multiagente para *Dynamic Pricing* e Otimização de Doação

> **Resumo:** Sistema multiagente híbrido (neuro-simbólico) para redução do desperdício alimentar no retalho. A arquitetura integra *Dynamic Pricing* com Etiquetas Eletrónicas de Prateleira (ESL), *exhaustive search optimisation* com replaneamento *online* diário (*Search in Complex Environments*), *Retrieval-Augmented Generation* (RAG) sobre regras operacionais e histórico SQLite, e validação por *Constraint Satisfaction Problems* (CSP).

---

## 🏗️ Arquitetura e Pipeline Multiagente

O sistema opera sobre um catálogo de 200 artigos distribuídos por 8 categorias (*bebidas, carne, charcutaria, fruta, laticínios, mercearia, padaria* e *pescado*) e 500 lotes (6 lotes por artigo na padaria e 2 nas restantes categorias), com rastreabilidade GS1 DataMatrix e persistência em SQLite (`data/desperdicio.db`).

Para lotes com validade $\le 5$ dias, o orquestrador (`src/simulation/orchestrator.py`) executa quatro módulos em cadeia:

1. **Agente de Controlo de Inventário (`src/agents/inventory_agent.py`):**
   - Avalia validades, regimes de conservação (`consumir_ate` vs. `preferencia_antes`), Preço por Unidade de Medida (PUM), cobertura de stock e excedente previsto perante a procura ajustada pela meteorologia e pelas perturbações ativas.
   - Consulta o motor RAG (`src/rag/retriever.py`) através de representação TF-IDF e similaridade de cosseno para recuperar regras sazonais, meteorológicas, de calendário e registos históricos do SQLite.

2. **Agente de Logística e Doação (`src/agents/logistics_agent.py`):**
   - Atribui o destino operacional de cada lote: `prateleira_desconto`, `sacos_surpresa`, `cozinha_interna`, `doacao_externa`, `racao_animal` ou `descarte_obrigatorio`.
   - Prioriza o escoamento comercial com ESL; atribui a cozinha interna a excedentes de carne e pescado no último dia útil ($\le 1\text{ d}$), a doação externa (IPSS) a excedentes na última janela legal elegível ($2\text{ d}$ em `consumir_ate` ou $0\text{ d}$ em `preferencia_antes`) e os Sacos Surpresa ($0{,}50\text{ kg}$) à padaria de véspera.
   - Em véspera de feriado (*Loja Fechada Amanhã*), preserva a validade física de 48h para elegibilidade de doação IPSS, contabilizando 1 dia útil de vendas.

3. **Agente de *Dynamic Pricing* (`src/agents/pricing_agent.py`):**
   - Implementa *Search in Complex Environments* através de *exhaustive search optimisation* (`_otimizar_desconto_curva`) sobre o domínio discreto admissível $D = \{0{,}00;\ 0{,}01;\ \dots;\ d_{\max}\}$ ($d_{\max} \le 0{,}70$, máximo de 71 estados), garantindo a determinação do ótimo global da função de utilidade esperada:

     $$U(d) = \text{Receita}(d) - \text{Sobra}(d) \times \left(\text{Custo}_{\text{aquisição}} + \text{Custo}_{\text{descarte}}\right)$$

   - Incorpora sinais sazonais recuperados pelo RAG ($+10\%$ na procura em início de mês ou fim de semana; $-10\%$ em fim de mês ou férias de agosto) no modo local determinístico, suportando ainda refinamento estruturado via LLM (OpenRouter / DeepSeek) mediante disponibilização de chave de API.
   - Na simulação multi-dia (`simular_horizonte_temporal`), o ciclo diário realiza replaneamento *online* face a procura estocástica e perturbações operacionais.

4. **Módulo Regulador CSP (`src/csp/constraints.py`):**
   - Valida e corrige as propostas dos agentes antes da atualização das etiquetas ESL ou da retirada de prateleira.

---

## ⚙️ Restrições CSP e Base de Conhecimento (RAG)

Todas as decisões finais obedecem às restrições codificadas em `src/csp/constraints.py`:

- **Teto Global de Desconto:** Limite máximo de $70\%$ sobre o PVP em perecíveis, padaria e Sacos Surpresa.
- **Teto em Laticínios:** Lotes com validade $\le 24\text{ h}$ apresentam limite máximo de $50\%$.
- **Modulação Meteorológica (Chuva / Temporal):** Em dias de chuva intensa (sem fecho em 2h nem quebra de clientes), o desconto é limitado a $30\%$ a 2 dias e $45\%$ no último dia.
- **Coerência com Campanha Semanal:** Qualquer desconto de validade tem de exceder a campanha ativa em pelo menos $+5\%$; caso o teto financeiro ou legal impeça esse acréscimo, mantém-se o desconto de campanha.
- **Margem e Piso de Recuperação:** Para validade $> 1\text{ d}$, o preço respeita a margem mínima sobre o custo de aquisição; no último dia ($\le 1\text{ d}$), garante o piso $\max(\text{custo\_descarte},\ 0{,}15 \times \text{PVP})$.
- **Segurança Alimentar (`consumir_ate` vs. `preferencia_antes`):**
  - Artigos de *mercearia* e *bebidas* possuem data de durabilidade mínima (`preferencia_antes`), sendo elegíveis para doação a $0\text{ d}$.
  - As restantes categorias possuem data-limite de consumo (`consumir_ate`): carne e pescado a $\le 24\text{ h}$ são vedados a doação externa (encaminhados para cozinha interna) e artigos `consumir_ate` exigem $\ge 48\text{ h}$ de validade para recolha por IPSS.
- **Padaria, Sacos Surpresa e Ração Animal (SANDACH):**
  - Artigos de padaria não entram na cozinha interna e são a única categoria elegível para Sacos Surpresa (peso agregado mínimo de $0{,}50\text{ kg}$, quota de $35\%$ em operação normal ou $50\%$ com fecho $\le 2\text{ h}$ ou quebra de procura).
  - No fim de vida útil ($0\text{ d}$), $100\%$ do pão simples elegível (16 em 25 artigos de padaria) segue para transformação em farinha para ração animal.
  - Por composição alimentar (chocolate, carne/chouriço, ovos/gorduras doces, alho ou frutos secos), 9 artigos são excluídos de ração animal pelo CSP e seguem para descarte obrigatório: *Croissant Brioche, Croissant Folhado, Croissant com Chocolate, Pão com Chouriço, Bolo do Caco, Pão de Leite, Pão de Deus, Regueifa* e *Pão de Centeio com Nozes*.
  - O inventário inicial inclui 2 lotes de pão simples elegível a $0\text{ d}$, representando excedentes da véspera destinados a valorização.
- **Memória RAG Híbrida (`src/rag/knowledge_base.py` e `src/rag/retriever.py`):** Indexa regras operacionais (meteorologia, ciclo salarial mensal, fins de semana, feriados, épocas festivas e segurança alimentar) e 5 visões agregadas de histórico operacional e financeiro armazenadas em `data/desperdicio.db`.

---

## 🔬 Reprodutibilidade e Metodologia Experimental

- **Inventário Determinístico com Datas Relativas:** O catálogo de 200 produtos, os 500 lotes (`LOTE1001` a `LOTE1500`), os stocks e os dias até expirar são gerados a partir de *seeds* fixas (`SEED_FIXA = 43` na simulação e *seed* fixa no catálogo base), com datas de validade projetadas sobre `date.today()`. Execuções em datas distintas mantêm a estrutura de lotes e refletem a sazonalidade correspondente ao dia de execução.
- **Modo Determinístico Local vs. LLM:** A aplicação opera sem chave de API em modo local determinístico (*exhaustive search optimisation*, regras RAG e auditoria CSP). A definição de `OPENROUTER_API_KEY` ativa o raciocínio generativo opcional, preservando o CSP como mecanismo de validação obrigatório.
- **Protocolo de Comparação (*Benchmark* Desperdíci0% vs. Lidl):**
  - ***Common Random Numbers* (CRN):** Ambos os modelos partilham o mesmo choque estocástico diário de procura (`uniform(0.85, 1.15)`) por par `(dia, produto)`, bem como as mesmas perturbações e condições meteorológicas.
  - **Simetria Económica nos Sacos Surpresa:** Tanto o Desperdíci0% como a *baseline* Lidl determinam a venda dos Sacos Surpresa em função da procura elástica efetiva dos clientes.
  - **Parâmetros da *Baseline* Lidl:** Desconto DLL de $30\%$ (a 2d) e $50\%$ no último dia; quota de $40\%$ para sacos de padaria ($50\%$ de desconto e $10\%$ de contribuição social); taxa de doação de $45\%$ em `consumir_ate` elegíveis e $35\%$ em `preferencia_antes`; taxa de encaminhamento de $40\%$ das sobras de padaria para ração animal.
  - **Controlo Meteorológico:** Para reprodução dos resultados experimentais sem dependência da API Open-Meteo em tempo real, seleciona-se o modo `Simular: Céu Limpo / Normal` (ou outro cenário simulado fixo) antes da Simulação Acelerada.

---

## 🚀 Instalação e Configuração

Requisito: **Python 3.10+**.

```bash
# 1. Clonar o repositório
git clone https://github.com/eduardofino621-ops/desperdici0-system.git
cd desperdici0-system

# 2. Criar e ativar o ambiente virtual
python -m venv venv
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

# 3. Instalar dependências
pip install langchain langchain-openai langgraph streamlit pandas pydantic streamlit-aggrid altair scikit-learn qrcode[pil] requests python-dotenv pytest
```

*(Opcional)* Para ativar o raciocínio generativo via OpenRouter, definir `OPENROUTER_API_KEY` num ficheiro `.env` na raiz do projeto ou na variável de ambiente:

```bash
# Windows (PowerShell)
$env:OPENROUTER_API_KEY="sua_chave_openrouter"

# macOS / Linux
export OPENROUTER_API_KEY="sua_chave_openrouter"
```

---

## 💻 Execução da Aplicação

```bash
python -m streamlit run app.py
```

### Funcionalidades do Dashboard

- **Dashboard de Operações e Explicabilidade por Lote:** Consulta dos 500 lotes com filtros por categoria, validade e pesquisa; a seleção da coluna *Decisão dos agentes* abre o registo da decisão com evidências TF-IDF do RAG, pareceres dos três agentes e auditoria CSP.
- **Perturbações e Meteorologia:** Injeção acumulativa de perturbações (*A menos de 2 horas de fechar a loja*, *Quebra Repentina de Clientes (-50% Procura)*, *Feriado / Loja Fechada Amanhã*, *Pico de Stock Excedente em Frutas e Carne*) e seleção de meteorologia em tempo real (Open-Meteo — Coimbra) ou simulada, com navegação pelo histórico de estados.
- **Etiquetas Eletrónicas de Prateleira (ESL):** Visualização de etiquetas FEFO (PUM legal, campanha semanal, lotes com desconto de validade, código QR e venda simulada de lotes e Sacos Surpresa).
- **Simulação Acelerada Multi-Dia (2, 5 ou 7 dias):** Evolução diária com comparação entre Desperdíci0% e *baseline* Lidl, decomposição da Taxa de Salvamento ($QVD, QD, QCI, QTAR$) e gráficos comparativos por categoria em Altair.
- **Explorador RAG:** Consulta na barra lateral das regras operacionais indexadas e dos registos históricos carregados do SQLite.

---

## 🧪 Testes Automatizados

A suíte de testes encontra-se em `tests/` (`test_agents.py`, `test_rag.py` e `test_simulation.py`):

```bash
pytest -v
```

---

## 📊 Métricas de Avaliação

O desempenho global é medido pela **Taxa de Salvamento ($TS$)** em massa ($\text{kg}$), complementada pela **Taxa de Desperdício Global**, **Custo de Desperdício Evitado (€)**, **Receita Total de Vendas (€)** e **Lucro Final ($\text{Receita} - \text{Custo de Desperdício}$)**:

$$TS = \frac{QVD + QD + QCI}{QTAR} \times 100$$

- **$QVD$ (Quantidade Vendida com Desconto):** Massa ($\text{kg}$) escoada através de descontos de validade (ESL) e Sacos Surpresa.
- **$QD$ (Quantidade Doada / Valorizada):** Massa ($\text{kg}$) encaminhada para doação externa (IPSS) e transformação em ração animal.
- **$QCI$ (Quantidade Cozinha Interna):** Massa ($\text{kg}$) encaminhada para confeção na cozinha interna.
- **$QTAR$ (Quantidade Total em Risco):** Massa crítica que atingiu o fim de vida útil no horizonte simulado ($QVD + QD + QCI + \text{Desperdício}$).
- **Meta Experimental:** Taxa de Salvamento superior a $90\%$, com melhoria do lucro final e redução do desperdício face à *baseline* Lidl.

---

## 👥 Autores

- Eduardo Coelho Fino (DEI-FCT, Universidade de Coimbra)
- Glória Costa Guimarães (DEI-FCT, Universidade de Coimbra)