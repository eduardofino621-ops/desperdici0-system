import os
import json
import random
import itertools
from pathlib import Path
from urllib.parse import urlparse
from datetime import date, datetime, timedelta, timezone

try:
    from influxdb_client_3 import InfluxDBClient3, Point
    INFLUX_DISPONIVEL = True
except ImportError:
    INFLUX_DISPONIVEL = False


# ==============================================================================
# GERADOR DETERMINÍSTICO DE 1.000 PRODUTOS ÚNICOS (1:1 COM EAN-13)
# ==============================================================================
CATEGORIAS_CONFIG = {
    "frescos": {
        "prefixos": [
            "Bife de Vazia", "Lombo de Porco", "Peito de Frango", "Novilho para Estufar",
            "Hambúrguer de Novilho", "Costeletas de Borrego", "Perú Fatiado", "Alheira Tradicional",
            "Chouriço de Carne", "Entrecosto Fresco", "Picanha Maturada", "Perna de Frango"
        ],
        "marcas": ["Talho Seleção", "Monte Alentejano", "Quinta Fresca", "Origem Nacional", "Sabor Campo", "Beira Tradicional"],
        "formatos": [
            ("Granel", "kg", 1.0, 1.0),
            ("Cuvete 400g", "un", 0.40, 0.45),
            ("Cuvete 800g", "un", 0.80, 0.85),
            ("Pack Familiar 1,2kg", "pack", 1.20, 1.18),
        ],
        "un_ref": "kg",
        "pvp_base_kg": (6.49, 19.99),
        "margem": 0.05, "descarte": 0.75, "elasticidade": 1.55, "conservacao": "refrigerado_0_4C",
    },
    "pescado": {
        "prefixos": [
            "Salmão Fresco", "Lombos de Bacalhau", "Dourada Fresca", "Robalo de Mar",
            "Pescada em Postas", "Miolo de Camarão", "Polvo Limpo", "Sardinha Fresca",
            "Atum Fresco", "Filetes de Linguado", "Pargo Fresco", "Lulas Limpas"
        ],
        "marcas": ["Mar Atlântico", "Costa Portuguesa", "Pesca do Dia", "Oceano Vivo", "Ria Fresca", "Norte Mar"],
        "formatos": [
            ("Fresco", "kg", 1.0, 1.0),
            ("Embalado 350g", "un", 0.35, 0.40),
            ("Embalado 600g", "un", 0.60, 0.65),
            ("Pack 2 Postas 500g", "pack", 0.50, 0.55),
        ],
        "un_ref": "kg",
        "pvp_base_kg": (7.99, 24.50),
        "margem": 0.05, "descarte": 0.85, "elasticidade": 1.65, "conservacao": "refrigerado_0_2C",
    },
    "laticinios": {
        "prefixos": [
            "Iogurte Natural", "Queijo Gouda Fatiado", "Leite Meio-Gordo", "Queijo Flamengo Bola",
            "Manteiga com Sal", "Iogurte Grego", "Requeijão de Ovelha", "Nata para Culinária",
            "Queijo Fresco", "Kefir Natural", "Iogurte Líquido Morango", "Queijo Curado Amanteigado"
        ],
        "marcas": ["Mimosa", "Agros", "Terra Nostra", "Açores DOP", "Danone", "Nestlé"],
        "formatos": [
            ("200g", "un", 0.20, 1.0),
            ("500g", "un", 0.50, 2.1),
            ("Pack 4x125g", "pack", 0.50, 1.8),
            ("Pack 8x125g", "pack", 1.00, 3.3),
        ],
        "un_ref": "kg",
        "pvp_base_kg": (1.19, 2.89),
        "margem": 0.06, "descarte": 0.30, "elasticidade": 1.25, "conservacao": "refrigerado_2_6C",
    },
    "padaria": {
        "prefixos": [
            "Pão de Centeio", "Broa de Milho", "Pão de Mafra", "Papo-Seco Tradicional",
            "Croissant Brioche", "Bola de Berlim", "Pão Integral Sementes", "Regueifa Doce",
            "Pastel de Nata", "Pão de Forma Rústico", "Pão de Água", "Trança Doce"
        ],
        "marcas": ["Forno do Dia", "Padaria Tradicional", "Moinho Velho", "Arte do Pão", "Trigo Dourado", "Casa do Pão"],
        "formatos": [
            ("Unidade 250g", "un", 0.25, 1.0),
            ("Fatiado 500g", "un", 0.50, 1.7),
            ("Pack 4 Unidades", "pack", 0.32, 1.5),
            ("Pack 6 Unidades", "pack", 0.48, 2.1),
        ],
        "un_ref": "kg",
        "pvp_base_kg": (0.99, 2.49),
        "margem": 0.10, "descarte": 0.15, "elasticidade": 1.80, "conservacao": "ambiente",
    },
    "fruta": {
        "prefixos": [
            "Morangos Frescos", "Maçã Gala Alcobaça", "Banana da Madeira", "Pêra Rocha Oeste",
            "Laranja do Algarve", "Mirtilos Frescos", "Kiwi Verde", "Uva Branca sem Grainha",
            "Manga Maturada", "Framboesas", "Pêssego Amarelo", "Ameixa Rainha Cláudia"
        ],
        "marcas": ["Pomar Oeste", "Horta Fresca", "Frutas do Sol", "Quinta Bio", "Vale Verde", "Colheita Nacional"],
        "formatos": [
            ("Pack 250g", "pack", 0.25, 1.0),
            ("Pack 500g", "pack", 0.50, 1.8),
            ("Pack 1kg", "pack", 1.00, 3.2),
            ("Pack Bio 400g", "pack", 0.40, 1.9),
        ],
        "un_ref": "kg",
        "pvp_base_kg": (1.29, 2.79),
        "margem": 0.05, "descarte": 0.30, "elasticidade": 1.85, "conservacao": "refrigerado_2_6C",
    },
    "mercearia": {
        "prefixos": [
            "Azeite Virgem Extra", "Arroz Carolino", "Massa Esparguete", "Grão-de-Bico Cozido",
            "Atum em Posta", "Café Torrado Moído", "Bolacha Maria", "Aveia Integral",
            "Tomate Pelado", "Mel Multifloral", "Feijão Preto Cozido", "Azeite Seleção"
        ],
        "marcas": ["Gallo", "Oliveira da Serra", "Cigala", "Nacional", "Delta", "Bom Petisco"],
        "formatos": [
            ("250g", "un", 0.25, 1.0),
            ("500g", "un", 0.50, 1.8),
            ("1kg", "un", 1.00, 3.3),
            ("Pack 3 Unidades", "pack", 0.75, 2.6),
        ],
        "un_ref": "kg",
        "pvp_base_kg": (1.19, 3.99),
        "margem": 0.08, "descarte": 0.20, "elasticidade": 1.15, "conservacao": "ambiente",
    },
    "bebidas": {
        "prefixos": [
            "Sumo Laranja 100%", "Água Mineral Natural", "Leite de Aveia Barista", "Néctar Pêssego",
            "Chá Verde Frio", "Sumo Maçã Bio", "Bebida de Amêndoa", "Néctar Manga Laranja",
            "Água com Gás Limão", "Infusão Frutos Vermelhos", "Sumo Ananás", "Bebida de Soja"
        ],
        "marcas": ["Compal", "Luso", "Vitalis", "Alpro", "Frize", "Um Bongo"],
        "formatos": [
            ("Garrafa 33cl", "un", 0.33, 1.0),
            ("Garrafa 1L", "un", 1.00, 2.1),
            ("Pack 4x20cl", "pack", 0.80, 2.3),
            ("Pack 6x1,5L", "pack", 9.00, 5.4),
        ],
        "un_ref": "L",
        "pvp_base_kg": (0.85, 1.99),
        "margem": 0.08, "descarte": 0.15, "elasticidade": 1.20, "conservacao": "ambiente",
    },
}


def _calcular_digito_controlo_ean13(base_12: str) -> str:
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base_12))
    resto = soma % 10
    return "0" if resto == 0 else str(10 - resto)


def _gerar_gtin13(indice: int) -> str:
    base_12 = f"560{indice:09d}"
    return base_12 + _calcular_digito_controlo_ean13(base_12)


def _calcular_periodo_semana(data_ref: date) -> str:
    segunda = data_ref - timedelta(days=data_ref.weekday())
    domingo = segunda + timedelta(days=6)
    return f"{segunda.strftime('%d/%m/%Y')} a {domingo.strftime('%d/%m/%Y')}"


class GestorBaseDadosTemporal:
    """
    Gere a evolução temporal de 1.000 artigos distintos e respetivos lotes:
    - Cada artigo + formato/conteúdo líquido possui um único EAN-13 (relação 1:1).
    - Múltiplos lotes físicos do mesmo artigo partilham o mesmo EAN-13 e distinguem-se
      pela data de validade e identificador de lote no código GS1 DataMatrix.
    """

    def __init__(self, total_produtos: int = 1000, seed: int = 2026):
        self.total_produtos = total_produtos
        self.seed = seed
        self.state_file = Path("data/estado_temporal.json")
        self.influx_url = os.environ.get("INFLUXDB_URL", "")
        self.influx_token = os.environ.get("INFLUXDB_TOKEN", "")
        self.influx_org = os.environ.get("INFLUXDB_ORG", "Dev Team")
        self.influx_db = os.environ.get("INFLUXDB_DATABASE", os.environ.get("INFLUXDB_BUCKET", "desperdici0"))

    def obter_data_referencia(self, dias_avanco_simulado: int = 0) -> date:
        return date.today() + timedelta(days=dias_avanco_simulado)

    def _construir_pool_artigos_unicos(self, rng: random.Random) -> list[dict]:
        """
        Gera todas as combinações únicas (artigo + marca + formato) sem repetições
        e seleciona exatamente `total_produtos - 4` artigos distintos.
        """
        nomes_reservados = {
            "Salmão Fresco Atlântico",
            "Bife de Vazia Maturado",
            "Iogurte Natural (Pack 4)",
            "Azeite Virgem Extra 0,75L",
        }

        pool_completo = []
        for cat_nome, cfg in CATEGORIAS_CONFIG.items():
            for artigo, marca, (rotulo_fmt, unidade, conteudo, mult_preco) in itertools.product(
                cfg["prefixos"], cfg["marcas"], cfg["formatos"]
            ):
                nome_completo = f"{artigo} {marca} ({rotulo_fmt})"
                if nome_completo in nomes_reservados:
                    continue
                pool_completo.append({
                    "nome": nome_completo,
                    "categoria": cat_nome,
                    "unidade_medida": unidade,
                    "conteudo_liquido": conteudo,
                    "unidade_referencia": cfg["un_ref"],
                    "mult_preco": mult_preco,
                    "pvp_range": cfg["pvp_base_kg"],
                    "margem": cfg["margem"],
                    "descarte": cfg["descarte"],
                    "elasticidade": cfg["elasticidade"],
                    "conservacao": cfg["conservacao"],
                })

        rng.shuffle(pool_completo)
        return pool_completo[: max(0, self.total_produtos - 4)]

    def gerar_dataset_temporal(self, data_ref: date | None = None) -> tuple[list[dict], list[dict]]:
        if data_ref is None:
            data_ref = date.today()

        rng = random.Random(self.seed)
        periodo_semana = _calcular_periodo_semana(data_ref)
        artigos_unicos = self._construir_pool_artigos_unicos(rng)

        indices_todos = list(range(1, self.total_produtos + 1))
        indices_validade_curta = set(rng.sample(indices_todos, int(self.total_produtos * 0.16)))  # 16% (1–5 dias)
        indices_campanha = set(rng.sample(indices_todos, int(self.total_produtos * 0.40)))        # 40% em campanha

        indices_validade_curta.update({1, 2})
        indices_validade_curta.discard(3)
        indices_validade_curta.discard(4)

        indices_campanha.update({1, 3})
        indices_campanha.discard(2)
        indices_campanha.discard(4)

        catalogo: list[dict] = []
        lotes: list[dict] = []
        contador_lote = 1000

        for idx in indices_todos:
            prod_id = f"PROD-{idx:04d}"
            gtin = _gerar_gtin13(idx)

            if idx == 1:
                cat_nome = "pescado"
                nome = "Salmão Fresco Atlântico"
                unidade_prod = "kg"
                conteudo_liq = 1.0
                un_ref = "kg"
                pvp = 18.50
                vendas_dia = 3.0
                cfg = CATEGORIAS_CONFIG[cat_nome]
            elif idx == 2:
                cat_nome = "frescos"
                nome = "Bife de Vazia Maturado"
                unidade_prod = "kg"
                conteudo_liq = 1.0
                un_ref = "kg"
                pvp = 12.99
                vendas_dia = 5.0
                cfg = CATEGORIAS_CONFIG[cat_nome]
            elif idx == 3:
                cat_nome = "laticinios"
                nome = "Iogurte Natural (Pack 4)"
                unidade_prod = "pack"
                conteudo_liq = 0.50
                un_ref = "kg"
                pvp = 1.80
                vendas_dia = 10.0
                cfg = CATEGORIAS_CONFIG[cat_nome]
            elif idx == 4:
                cat_nome = "mercearia"
                nome = "Azeite Virgem Extra 0,75L"
                unidade_prod = "un"
                conteudo_liq = 0.75
                un_ref = "L"
                pvp = 7.49
                vendas_dia = 4.0
                cfg = CATEGORIAS_CONFIG[cat_nome]
            else:
                spec = artigos_unicos[idx - 5]
                cat_nome = spec["categoria"]
                nome = spec["nome"]
                unidade_prod = spec["unidade_medida"]
                conteudo_liq = spec["conteudo_liquido"]
                un_ref = spec["unidade_referencia"]
                pvp_base = rng.uniform(*spec["pvp_range"])
                pvp = round(pvp_base * spec["mult_preco"], 2)
                vendas_dia = round(rng.uniform(2.0, 14.0), 1)
                cfg = spec

            custo = round(pvp * rng.uniform(0.52, 0.68), 2)

            tem_campanha = idx in indices_campanha
            desc_campanha = rng.choice([0.15, 0.20, 0.25, 0.30]) if tem_campanha else 0.0
            if idx == 1:
                desc_campanha = 0.25
            elif idx == 3:
                desc_campanha = 0.20

            catalogo.append({
                "produto_id": prod_id,
                "gtin": gtin,
                "nome": nome,
                "categoria": cat_nome,
                "unidade_medida": unidade_prod,
                "conteudo_liquido": conteudo_liq,
                "unidade_referencia": un_ref,
                "pvp": pvp,
                "desconto_campanha": desc_campanha,
                "periodo_campanha": periodo_semana if tem_campanha else "",
                "custo_aquisicao": custo,
                "margem_minima_pct": cfg["margem"],
                "custo_descarte": cfg["descarte"],
                "vendas_medias_diarias": vendas_dia,
                "elasticidade_preco": cfg["elasticidade"],
                "conservacao": cfg["conservacao"],
            })

            tem_validade_curta = idx in indices_validade_curta

            if idx == 1:
                especificacoes_lotes = [(1, 7.0, 4), (2, 11.0, 3), (4, 10.0, 1)]
            elif tem_validade_curta:
                dias_exp = rng.randint(1, 5)
                qtd = round(vendas_dia * dias_exp * rng.uniform(1.35, 2.2), 1)
                especificacoes_lotes = [(dias_exp, max(6.0, qtd), rng.randint(2, 6))]
                if idx % 4 == 0:
                    dias_exp_2 = min(5, dias_exp + rng.randint(1, 2))
                    if dias_exp_2 > dias_exp:
                        especificacoes_lotes.append((dias_exp_2, round(vendas_dia * 1.6, 1), 1))
            else:
                dias_exp = rng.randint(6, 55)
                qtd = round(vendas_dia * rng.uniform(1.5, 4.0), 1)
                especificacoes_lotes = [(dias_exp, max(5.0, qtd), rng.randint(2, 10))]

            for dias_exp, qtd, dias_desde_entrada in especificacoes_lotes:
                contador_lote += 1
                lote_id = f"LOTE{contador_lote:04d}"
                data_val = data_ref + timedelta(days=dias_exp)
                data_ent = data_ref - timedelta(days=dias_desde_entrada)
                gs1_data = data_val.strftime("%y%m%d")
                preco_inicial = round(pvp * (1 - desc_campanha), 2)

                lotes.append({
                    "lote_id": lote_id,
                    "produto_id": prod_id,
                    "quantidade_disponivel": qtd,
                    "data_entrada": data_ent.isoformat(),
                    "data_validade": data_val.isoformat(),
                    "dias_para_expirar": dias_exp,
                    "desconto_validade": 0.0,
                    "preco_final_atual": preco_inicial,
                    "codigo_gs1_raw": f"01|{gtin}|17|{gs1_data}|10|{lote_id}",
                    "estado": "ativo",
                })

        self._registar_execucao_local(data_ref, catalogo, lotes)
        return catalogo, lotes

    def _registar_execucao_local(self, data_ref: date, catalogo: list[dict], lotes: list[dict]) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            historico = {}
            if self.state_file.exists():
                historico = json.loads(self.state_file.read_text(encoding="utf-8"))

            historico[data_ref.isoformat()] = {
                "timestamp": datetime.now().isoformat(),
                "total_produtos": len(catalogo),
                "total_lotes": len(lotes),
                "lotes_1_a_5_dias": sum(1 for l in lotes if l["dias_para_expirar"] <= 5),
                "produtos_em_campanha": sum(1 for p in catalogo if p["desconto_campanha"] > 0),
            }
            self.state_file.write_text(json.dumps(historico, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def registar_telemetria_influxdb(self, data_ref: date, lotes: list[dict], cenario: str) -> tuple[bool, str]:
        if not INFLUX_DISPONIVEL:
            return False, "Biblioteca 'influxdb3-python' não encontrada neste ambiente (corre: pip install influxdb3-python)."

        if not self.influx_url or not self.influx_token:
            return False, "INFLUXDB_URL ou INFLUXDB_TOKEN vazios no ficheiro .env."

        parsed = urlparse(self.influx_url.strip())
        host_limpo = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else self.influx_url.strip()

        try:
            client = InfluxDBClient3(
                host=host_limpo,
                token=self.influx_token.strip(),
                org=self.influx_org.strip(),
                database=self.influx_db.strip(),
            )

            agora_utc = datetime.now(timezone.utc)
            ts = datetime(
                data_ref.year,
                data_ref.month,
                data_ref.day,
                agora_utc.hour,
                agora_utc.minute,
                agora_utc.second,
                tzinfo=timezone.utc,
            )

            lotes_validade = [l for l in lotes if l.get("desconto_validade", 0.0) > 0]
            desc_medio = (
                sum(l["desconto_validade"] for l in lotes_validade) / max(1, len(lotes_validade))
            )

            ponto_resumo = (
                Point("resumo_diario_loja")
                .tag("cenario", cenario)
                .tag("data_operacao", data_ref.isoformat())
                .field("total_lotes", len(lotes))
                .field("lotes_com_desconto_validade", len(lotes_validade))
                .field("desconto_validade_medio_pct", round(desc_medio * 100, 2))
                .time(ts)
            )
            pontos = [ponto_resumo]

            for lote in lotes_validade[:50]:
                pontos.append(
                    Point("evolucao_lotes_esl")
                    .tag("produto_id", lote["produto_id"])
                    .tag("lote_id", lote["lote_id"])
                    .tag("destino", lote.get("destino_final", "prateleira_desconto"))
                    .field("dias_para_expirar", int(lote["dias_para_expirar"]))
                    .field("desconto_validade_pct", round(lote["desconto_validade"] * 100, 2))
                    .field("preco_final_eur", float(lote["preco_final_atual"]))
                    .field("stock_disponivel", float(lote["quantidade_disponivel"]))
                    .time(ts)
                )

            client.write(record=pontos)
            client.close()
            return True, f"Sincronizado com InfluxDB Cloud ({len(pontos)} registos em '{self.influx_db}' na data {data_ref.isoformat()})."
        except Exception as exc:
            return False, f"Erro InfluxDB ({host_limpo} | org='{self.influx_org}' | db='{self.influx_db}'): {exc}"