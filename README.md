# Desperdíci0% - Sistema Multiagente para Dynamic Pricing e Otimização de Doação

> **Resumo do Projeto:** Sistema multiagente desenvolvido para combater o desperdício alimentar em superfícies comerciais, combinando a gestão dinâmica de preços em tempo real (*dynamic pricing* através de Etiquetas Eletrónicas de Prateleira - ESL) com o encaminhamento atempado de excedentes para doação ou reutilização interna.

---

## 🏗️ Arquitetura do Sistema

O sistema baseia-se numa arquitetura orientada a grafos de estado (**LangGraph**), garantindo o cumprimento estrito de restrições operacionais e legais (CSP - *Constraint Satisfaction Problems*)[cite: 1, 2]. É composto por três agentes especializados:

1. **Agente de Controlo de Inventário:** Rastreia as datas de validade e a velocidade de escoamento das vendas.
2. **Agente de Dynamic Pricing:** Otimiza a curva de desvalorização de preços nos dias anteriores à validade, maximizando a recuperação de custos[cite: 1, 2].
3. **Agente de Logística e Doação:** Gere o encaminhamento de excedentes (ex: cozinha interna, sacos surpresa, doações a instituições), salvaguardando os limites temporais exigidos[cite: 1, 2].

---

## ⚙️ Regras Críticas e CSP (Constraint Satisfaction Problems)
Para garantir a conformidade legal (ex: Decreto-Lei n.º 166/2013 contra práticas predatórias/dumping) e operacional, o sistema valida restrições rígidas:
* **Bloqueio de Doação:** Produtos a menos de 48 horas da validade estão bloqueados para doação externa devido a restrições logísticas[cite: 1, 2].
* **Limites de Desconto:** Os descontos em produtos frescos não podem exceder os 70%[cite: 1, 2].
* **Gestão de Padaria:** O pão avulso não sofre descontos lineares, sendo alocado prioritariamente a "sacos surpresa"[cite: 1, 2].

---

## 🚀 Instalação e Configuração

Certifique-se de que tem o **Python 3.10+** instalado no seu sistema. Siga os passos abaixo para configurar o ambiente de desenvolvimento:

```bash
# 1. Clonar o repositório
git clone [https://github.com/o-teu-utilizador/desperdici0-system.git](https://github.com/o-teu-utilizador/desperdici0-system.git)
cd desperdici0-system

# 2. Criar e ativar o ambiente virtual
python -m venv venv
# No Windows:
venv\Scripts\activate
# No macOS / Linux:
source venv/bin/activate

# 3. Instalar as dependências necessárias
pip install langchain langgraph langchain-openai streamlit pandas pydantic