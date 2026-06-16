"""
Indicadores técnicos: RSI, EMA, tendencia.
Sin dependencias externas — puro Python.
"""


def calcular_rsi(precios: list[float], periodo: int = 14) -> float | None:
    """
    RSI clásico de Wilder (14 períodos por defecto).
    Requiere al menos periodo+1 precios.
    """
    if len(precios) < periodo + 1:
        return None

    ganancias = []
    perdidas = []
    for i in range(1, len(precios)):
        diff = precios[i] - precios[i - 1]
        if diff > 0:
            ganancias.append(diff)
            perdidas.append(0.0)
        else:
            ganancias.append(0.0)
            perdidas.append(abs(diff))

    avg_gan = sum(ganancias[-periodo:]) / periodo
    avg_per = sum(perdidas[-periodo:]) / periodo

    if avg_per == 0:
        return 100.0

    rs = avg_gan / avg_per
    return round(100 - (100 / (1 + rs)), 2)


def calcular_ema(precios: list[float], periodo: int) -> float | None:
    """
    EMA (Exponential Moving Average) para el último precio de la serie.
    """
    if len(precios) < periodo:
        return None

    mult = 2 / (periodo + 1)
    ema = sum(precios[:periodo]) / periodo
    for precio in precios[periodo:]:
        ema = (precio - ema) * mult + ema

    return round(ema, 8)


def detectar_tendencia(precios: list[float], ventana: int = 20) -> str:
    """
    Tendencia simple comparando EMA20 actual vs EMA20 de hace 5 períodos.
    Retorna 'alcista', 'bajista' o 'lateral'.
    """
    if len(precios) < ventana + 5:
        return "lateral"

    ema_actual = calcular_ema(precios, ventana)
    ema_anterior = calcular_ema(precios[:-5], ventana)

    if ema_actual is None or ema_anterior is None:
        return "lateral"

    diff_pct = (ema_actual - ema_anterior) / ema_anterior * 100

    if diff_pct > 1.0:
        return "alcista"
    if diff_pct < -1.0:
        return "bajista"
    return "lateral"


def tiene_senal(rsi: float | None, tendencia: str) -> bool:
    """
    True si hay una señal que vale la pena pasarle a Claude.
    Señal: RSI en zona extrema (sobreventa < 35 o sobrecompra > 65).
    """
    if rsi is None:
        return False
    return rsi < 35 or rsi > 65


def interpretar_rsi(rsi: float) -> str:
    if rsi < 30:
        return "sobreventa fuerte"
    if rsi < 40:
        return "sobreventa"
    if rsi > 70:
        return "sobrecompra fuerte"
    if rsi > 60:
        return "sobrecompra"
    return "neutral"
