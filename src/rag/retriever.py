from datetime import date
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.rag.knowledge_base import _normalizar_categoria, carregar_documentos_rag


def construir_query_contextual_rag(
    prod: dict,
    lote: dict,
    perturbacoes_ativas: list[str],
    data_ref: date,
    meteo: dict | None = None,
) -> str:
    cat_norm = _normalizar_categoria(prod.get("categoria"))
    partes = [
        f"Produto {prod.get('nome', '')} categoria {cat_norm}",
        f"validade {lote.get('dias_para_expirar', 3)} dias",
    ]

    if meteo and meteo.get("condicao_rag"):
        partes.append(meteo["condicao_rag"])

    if data_ref.day <= 10:
        partes.append("início do mês maior procura poder de compra")
    elif data_ref.day >= 22:
        partes.append("fim do mês menor procura sensibilidade ao preço")

    if data_ref.weekday() in (4, 5):
        partes.append("fim de semana pico de compras")
    if data_ref.month == 12:
        partes.append("época de Natal aumento de compras")
    elif data_ref.month == 8:
        partes.append("agosto férias")

    for p in perturbacoes_ativas:
        if "2 horas" in p:
            partes.append("menos de 2 horas para fechar a loja fecho")
        if "Clientes" in p:
            partes.append("quebra de clientes dia de chuva menor afluência")
        if "Feriado" in p:
            partes.append("feriado loja fechada amanhã urgência máxima")
        if "Stock Excedente" in p:
            partes.append("pico de stock excedente")

    return ", ".join(partes)


class RecuperadorRAG:
    def __init__(self, db_path: str = "data/desperdicio.db"):
        self.documentos = carregar_documentos_rag(db_path)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        textos = [doc["texto"] for doc in self.documentos]
        self.matriz_tfidf = self.vectorizer.fit_transform(textos) if textos else None

    def recuperar_contexto(self, consulta: str, categoria: str = "", top_k: int = 2) -> list[dict]:
        if self.matriz_tfidf is None or not self.documentos:
            return []

        cat_norm = _normalizar_categoria(categoria) if categoria else ""
        query_enriquecida = f"{cat_norm} {consulta}".strip()
        vec_query = self.vectorizer.transform([query_enriquecida])
        scores = cosine_similarity(vec_query, self.matriz_tfidf).flatten()

        for idx, doc in enumerate(self.documentos):
            if cat_norm and doc.get("categoria") == cat_norm:
                scores[idx] = min(1.0, float(scores[idx]) + 0.15)

        indices_top = scores.argsort()[::-1][:top_k]
        return [
            {
                "id": self.documentos[i]["id"],
                "texto": self.documentos[i]["texto"],
                "score": round(float(scores[i]), 3),
            }
            for i in indices_top
            if scores[i] > 0.05
        ]