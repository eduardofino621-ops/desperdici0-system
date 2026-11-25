import requests


def obter_meteorologia_atual(
    latitude: float = 40.2033,
    longitude: float = -8.4103,
    modo_override: str = "Automático (Tempo Real - Coimbra)",
) -> dict:
    """
    Obtém temperatura e precipitação em tempo real via Open-Meteo (sem API key)
    ou aplica uma condição meteorológica simulada para demonstração.
    """
    if modo_override == "Simular: Chuva Intensa / Temporal":
        return {
            "fonte": "Simulação Manual",
            "descricao": "Chuva intensa (14,5 mm/h)",
            "temperatura": 13.0,
            "precipitacao": 14.5,
            "condicao_rag": "dia de chuva intensa temporal menor afluência quebra de clientes",
            "fator_procura": 0.70,  # Reduz procura espontânea em 30%
        }
    if modo_override == "Simular: Calor Elevado (> 30°C)":
        return {
            "fonte": "Simulação Manual",
            "descricao": "Céu limpo e calor elevado (32,5 °C)",
            "temperatura": 32.5,
            "precipitacao": 0.0,
            "condicao_rag": "dias de calor elevado bebidas frescas fruta churrasco",
            "fator_procura": 1.15,  # Aumenta procura em bebidas/frescos
        }

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,precipitation,rain,weather_code",
                "timezone": "Europe/Lisbon",
            },
            timeout=3,
        )
        resp.raise_for_status()
        atual = resp.json().get("current", {})
        temp = float(atual.get("temperature_2m", 16.0))
        precip = float(atual.get("precipitation", 0.0))
        wmo = int(atual.get("weather_code", 0))

        # Códigos WMO >= 51 correspondem a chuvisco, chuva, aguaceiros ou trovoada
        esta_a_chover = precip > 0.2 or wmo >= 51
        esta_calor = temp >= 28.0

        if esta_a_chover:
            return {
                "fonte": "Open-Meteo (Tempo Real)",
                "descricao": f"Chuva ({temp:.1f} °C | {precip:.1f} mm)",
                "temperatura": temp,
                "precipitacao": precip,
                "condicao_rag": "dia de chuva menor afluência quebra de clientes",
                "fator_procura": 0.75,
            }
        if esta_calor:
            return {
                "fonte": "Open-Meteo (Tempo Real)",
                "descricao": f"Calor ({temp:.1f} °C)",
                "temperatura": temp,
                "precipitacao": precip,
                "condicao_rag": "dias de calor elevado bebidas frescas fruta churrasco",
                "fator_procura": 1.15,
            }

        return {
            "fonte": "Open-Meteo (Tempo Real)",
            "descricao": f"Tempo ameno/seco ({temp:.1f} °C)",
            "temperatura": temp,
            "precipitacao": precip,
            "condicao_rag": "tempo seco operação normal",
            "fator_procura": 1.0,
        }
    except Exception:
        return {
            "fonte": "Fallback Offline",
            "descricao": "Tempo ameno (16,0 °C — modo offline)",
            "temperatura": 16.0,
            "precipitacao": 0.0,
            "condicao_rag": "operação normal",
            "fator_procura": 1.0,
        }