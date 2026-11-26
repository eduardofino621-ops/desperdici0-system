import pytest
from src.agents.inventory_agent import agente_controlo_inventario
from src.agents.logistics_agent import agente_logistica_doacao
from src.agents.pricing_agent import (
    TETO_DESCONTO_GLOBAL,
    agente_dynamic_pricing,
    otimizar_curva_precos_3dias,
)


@pytest.fixture
def produto_padaria():
    return {
        "produto_id": "PROD-0001",
        "nome": "Pão de Água",
        "categoria": "padaria",
        "unidade_medida": "un",
        "conteudo_liquido": 0.10,
        "unidade_referencia": "kg",
        "pvp": 0.40,
        "desconto_campanha": 0.0,
        "custo_aquisicao": 0.12,
        "margem_minima_pct": 0.05,
        "custo_descarte": 0.05,
        "vendas_medias_diarias": 20.0,
        "elasticidade_preco": 1.4,
        "conservacao": "ambiente",
        "tipo_validade": "consumir_ate",
    }


@pytest.fixture
def produto_carne():
    return {
        "produto_id": "PROD-0050",
        "nome": "Peito de Frango",
        "categoria": "carne",
        "unidade_medida": "kg",
        "conteudo_liquido": 1.0,
        "unidade_referencia": "kg",
        "pvp": 6.50,
        "desconto_campanha": 0.0,
        "custo_aquisicao": 3.80,
        "margem_minima_pct": 0.05,
        "custo_descarte": 0.40,
        "vendas_medias_diarias": 5.0,
        "elasticidade_preco": 1.5,
        "conservacao": "refrigerado",
        "tipo_validade": "consumir_ate",
    }


def test_inventario_calcula_excesso_e_risco(produto_carne):
    lote = {
        "lote_id": "LOTE1001",
        "produto_id": "PROD-0050",
        "quantidade_disponivel": 20.0,
        "dias_para_expirar": 2,
        "data_validade": "2026-11-28",
    }
    res = agente_controlo_inventario({"lote_atual": lote, "produto_catalogo": produto_carne})
    assert res["excesso_estimado"] == 10.0
    assert res["dias_cobertura_stock"] == 4.0
    assert res["risco_critico"] is True


def test_logistica_padaria_expirada_vai_para_racao(produto_padaria):
    lote = {"lote_id": "LOTE1010", "quantidade_disponivel": 15, "dias_para_expirar": 0}
    res = agente_logistica_doacao({"lote_atual": lote, "produto_catalogo": produto_padaria})
    assert res["destino_proposto"] == "racao_animal"


def test_logistica_carne_excesso_critico_ultimo_dia_cozinha_interna(produto_carne):
    lote = {"lote_id": "LOTE1020", "quantidade_disponivel": 25.0, "dias_para_expirar": 1}
    state = {
        "lote_atual": lote,
        "produto_catalogo": produto_carne,
        "excesso_estimado": 20.0,
        "dias_cobertura_stock": 5.0,
    }
    res = agente_logistica_doacao(state)
    assert res["destino_proposto"] == "cozinha_interna"


def test_logistica_excesso_elevado_48h_doacao_externa(produto_carne):
    lote = {"lote_id": "LOTE1021", "quantidade_disponivel": 40.0, "dias_para_expirar": 2}
    state = {
        "lote_atual": lote,
        "produto_catalogo": produto_carne,
        "excesso_estimado": 30.0,
        "dias_cobertura_stock": 8.0,
    }
    res = agente_logistica_doacao(state)
    assert res["destino_proposto"] == "doacao_externa"


def test_otimizador_curva_3dias_respeita_limites_e_monotonia(produto_carne):
    lote = {"lote_id": "LOTE1030", "quantidade_disponivel": 22.0, "dias_para_expirar": 3}
    res = otimizar_curva_precos_3dias(
        produto=produto_carne,
        lote=lote,
        piso_minimo=0.10,
        teto_maximo=0.60,
    )
    curva = res["curva"]
    assert len(curva) == 3
    assert curva == sorted(curva)
    assert all(0.10 <= d <= 0.60 for d in curva)
    assert res["desconto_hoje"] == curva[0]


def test_pricing_deterministico_sem_api_key(monkeypatch, produto_carne):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    lote = {"lote_id": "LOTE1040", "quantidade_disponivel": 18.0, "dias_para_expirar": 1}
    state = {
        "lote_atual": lote,
        "produto_catalogo": produto_carne,
        "excesso_estimado": 13.0,
        "destino_proposto": "prateleira_desconto",
        "contexto_rag": [],
    }
    res = agente_dynamic_pricing(state)
    assert 0.0 <= res["desconto_proposto"] <= TETO_DESCONTO_GLOBAL
    assert res["preco_proposto"] <= produto_carne["pvp"]
