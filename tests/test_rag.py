from datetime import date

from src.rag.knowledge_base import _normalizar_categoria, carregar_documentos_rag
from src.rag.retriever import RecuperadorRAG, construir_query_contextual_rag


def test_normalizacao_categorias():
    assert _normalizar_categoria("Peixe") == "pescado"
    assert _normalizar_categoria("Hortícolas") == "legumes"
    assert _normalizar_categoria("Laticínios") == "laticinios"
    assert _normalizar_categoria(None) == "geral"


def test_carregar_documentos_rag_sem_sqlite(tmp_path):
    db_inexistente = tmp_path / "nao_existe.db"
    docs = carregar_documentos_rag(db_path=str(db_inexistente))
    assert len(docs) > 0
    assert all("id" in d and "texto" in d and "categoria" in d for d in docs)


def test_construir_query_contextual_rag():
    prod = {"nome": "Salmão", "categoria": "pescado"}
    lote = {"dias_para_expirar": 1}
    meteo = {"condicao_rag": "chuva intensa"}
    query = construir_query_contextual_rag(
        prod=prod,
        lote=lote,
        perturbacoes_ativas=["A menos de 2 horas de fechar a loja.", "Quebra Repentina de Clientes (-50% Procura)"],
        data_ref=date(2026, 11, 26),
        meteo=meteo,
    )
    assert "Salmão" in query
    assert "pescado" in query
    assert "validade 1 dias" in query
    assert "chuva intensa" in query
    assert "fim do mês" in query


def test_recuperador_rag_recupera_contexto_relevante(tmp_path):
    db_inexistente = tmp_path / "nao_existe.db"
    rag = RecuperadorRAG(db_path=str(db_inexistente))
    resultados = rag.recuperar_contexto(
        consulta="pão de véspera menos de 2 horas para fechar a loja fecho sacos surpresa",
        categoria="padaria",
        top_k=2,
    )
    assert len(resultados) > 0
    assert all("id" in r and "texto" in r and "score" in r for r in resultados)