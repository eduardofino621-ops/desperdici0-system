import pytest
from src.agents.inventory_agent import agente_controlo_inventario
from src.agents.logistics_agent import agente_logistica_doacao
from src.agents.pricing_agent import (
    _otimizar_desconto_curva,
    agente_dynamic_pricing,
)

TETO_DESCONTO_GLOBAL = 0.70


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
def produto_pastelaria_excluida():
    return {
        "produto_id": "PROD-0002",
        "nome": "Croissant com Chocolate",
        "categoria": "padaria",
        "unidade_medida": "un",
        "conteudo_liquido": 0.09,
        "unidade_referencia": "kg",
        "pvp": 1.15,
        "desconto_campanha": 0.0,
        "custo_aquisicao": 0.45,
        "margem_minima_pct": 0.10,
        "custo_descarte": 0.15,
        "vendas_medias_diarias": 10.0,
        "elasticidade_preco": 1.8,
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


def test_logistica_pastelaria_excluida_sandach_vai_para_descarte(produto_pastelaria_excluida):
    lote = {"lote_id": "LOTE1011", "quantidade_disponivel": 10, "dias_para_expirar": 0}
    res = agente_logistica_doacao({"lote_atual": lote, "produto_catalogo": produto_pastelaria_excluida})
    assert res["destino_proposto"] == "descarte_obrigatorio"


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


def test_otimizador_desconto_discreto_respeita_teto(produto_carne):
    desc = _otimizar_desconto_curva(
        quantidade=22.0,
        vendas_medias=produto_carne["vendas_medias_diarias"],
        dias=2,
        elasticidade=produto_carne["elasticidade_preco"],
        pvp=produto_carne["pvp"],
        custo=produto_carne["custo_aquisicao"],
        custo_descarte=produto_carne["custo_descarte"],
        desconto_campanha=0.0,
        teto_efetivo=0.60,
    )
    assert 0.0 <= desc <= 0.60