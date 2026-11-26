from src.simulation.orchestrator import simular_horizonte_temporal


def test_simulacao_acelerada_invariantes():
    res = simular_horizonte_temporal(
        dias_simulacao=2,
        modo_meteo="Simular: Tempo Ameno / Seco",
        combinar_perturbacoes_aleatorias=False,
    )
    assert res["dias_simulados"] == 2
    assert 0.0 <= res["ts_pct"] <= 100.0
    assert 0.0 <= res["taxa_desperdicio_pct"] <= 100.0
    assert res["receita_total"] >= 0.0
    assert res["total_desperdicadas"] >= 0.0
    assert "comparacao_baseline" in res
    assert res["comparacao_baseline"]["receita_total"] >= 0.0
