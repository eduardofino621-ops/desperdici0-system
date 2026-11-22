from datetime import date
from src.database.db_manager import GestorBaseDadosTemporal

gestor_db = GestorBaseDadosTemporal(total_produtos=200, seed=2026)

CATALOGO_PRODUTOS, INVENTARIO_LOTES = gestor_db.gerar_dataset_temporal(data_ref=date.today())


def calcular_pum(preco_atual: float, produto: dict) -> str:
    """
    Calcula o Preço por Unidade de Medida (PUM) obrigatório nas etiquetas ESL.
    """
    conteudo = produto.get("conteudo_liquido", 1.0)
    un_ref = produto.get("unidade_referencia", produto.get("unidade_medida", "un"))
    pum = preco_atual / max(0.0001, conteudo)
    return f"{pum:.2f} €/{un_ref}"


def calcular_preco_efetivo_lote(lote: dict, produto: dict) -> tuple[float, float]:
    """
    Resolve o desconto efetivo e o preço final de um lote específico:
    1. Se tiver desconto de aproximação de validade, aplica-o (garantindo >= campanha).
    2. Caso contrário, aplica o desconto de campanha do produto (se existir).
    """
    pvp = produto.get("pvp", 0.0)
    desc_campanha = produto.get("desconto_campanha", 0.0)
    desc_validade = lote.get("desconto_validade", 0.0)

    if desc_validade > 0:
        desconto_final = max(desc_validade, desc_campanha)
    else:
        desconto_final = desc_campanha

    preco_final = round(pvp * (1 - desconto_final), 2)
    return desconto_final, preco_final