"""
Análisis de renta fija: carry trade ARS/USD, vencimientos, P&L en USD.
No usa RSI/EMA — lógica específica para instrumentos de renta fija.
"""
from datetime import date, datetime, timezone


def analizar_carry_trade(
    tna_caucion: float,
    dolar_mep_actual: float,
    dolar_mep_hace_30d: float | None,
) -> dict:
    """
    Evalúa si conviene estar en ARS (caución) vs quedarse en USD.

    carry > 2%  → ENTRAR  (ARS rinde más que la devaluación mensual)
    carry 0-2%  → NEUTRAL (zona gris, consultar contexto)
    carry < 0%  → SALIR   (dólar sube más de lo que rinde la caución)

    Returns:
        {accion, carry_mensual, tna_mensual, devaluacion_mensual, razon}
    """
    tna_mensual = tna_caucion / 12

    if dolar_mep_hace_30d and dolar_mep_hace_30d > 0:
        devaluacion_mensual = (dolar_mep_actual - dolar_mep_hace_30d) / dolar_mep_hace_30d * 100
    else:
        # Sin dato histórico: asumir devaluación conservadora del 3% mensual
        devaluacion_mensual = 3.0

    carry = tna_mensual - devaluacion_mensual

    if carry > 2:
        accion = "entrar"
        razon = (
            f"Carry favorable: caución rinde {tna_mensual:.1f}% mensual "
            f"vs devaluación de {devaluacion_mensual:.1f}% — diferencia de {carry:.1f}%."
        )
    elif carry < 0:
        accion = "salir"
        razon = (
            f"Carry negativo: devaluación ({devaluacion_mensual:.1f}% mensual) "
            f"supera TNA de caución ({tna_mensual:.1f}%). Mejor mantenerse en USD."
        )
    else:
        accion = "neutral"
        razon = (
            f"Zona gris: caución {tna_mensual:.1f}% vs devaluación {devaluacion_mensual:.1f}% "
            f"— diferencia de {carry:.1f}%. Evaluá según tu horizonte."
        )

    return {
        "accion": accion,
        "carry_mensual": round(carry, 2),
        "tna_mensual": round(tna_mensual, 2),
        "devaluacion_mensual": round(devaluacion_mensual, 2),
        "razon": razon,
    }


def evaluar_vencimientos(posiciones: list[dict], dias_alerta: int = 3) -> list[dict]:
    """
    Retorna posiciones que vencen en <= dias_alerta días.
    posiciones: lista de dicts con fecha_vencimiento (str ISO o date) y estado='abierta'
    """
    hoy = date.today()
    proximas = []

    for p in posiciones:
        if p.get("estado") != "abierta":
            continue
        venc = p.get("fecha_vencimiento")
        if not venc:
            continue

        if isinstance(venc, str):
            try:
                venc = date.fromisoformat(venc[:10])
            except ValueError:
                continue

        dias_restantes = (venc - hoy).days
        if dias_restantes <= dias_alerta:
            proximas.append({**p, "dias_restantes": dias_restantes})

    return sorted(proximas, key=lambda x: x["dias_restantes"])


def calcular_rendimiento_usd(
    posicion: dict,
    dolar_mep_actual: float,
) -> dict:
    """
    Calcula el P&L en USD de una posición abierta o vencida.

    Retorna:
        {rendimiento_ars_pct, rendimiento_usd, rendimiento_usd_pct}
    """
    monto_ars = posicion.get("monto_ars", 0)
    monto_usd_entrada = posicion.get("monto_usd")
    tipo_cambio_entrada = posicion.get("tipo_cambio_entrada")
    tna = posicion.get("tna_contratada") or 0

    # Calcular días transcurridos
    fecha_entrada = posicion.get("fecha_entrada")
    if isinstance(fecha_entrada, str):
        try:
            fecha_entrada = datetime.fromisoformat(fecha_entrada.replace("Z", "+00:00"))
        except ValueError:
            fecha_entrada = None

    dias = 0
    if fecha_entrada:
        ahora = datetime.now(timezone.utc)
        if fecha_entrada.tzinfo is None:
            fecha_entrada = fecha_entrada.replace(tzinfo=timezone.utc)
        dias = (ahora - fecha_entrada).days

    # Rendimiento bruto en ARS
    rendimiento_ars_pct = (tna / 365 * dias) if dias > 0 else 0
    monto_ars_final = monto_ars * (1 + rendimiento_ars_pct / 100)

    # Convertir a USD al tipo actual
    usd_actual = monto_ars_final / dolar_mep_actual if dolar_mep_actual > 0 else 0

    # P&L en USD
    if monto_usd_entrada:
        rendimiento_usd = usd_actual - monto_usd_entrada
        rendimiento_usd_pct = (rendimiento_usd / monto_usd_entrada * 100) if monto_usd_entrada > 0 else 0
    elif tipo_cambio_entrada and tipo_cambio_entrada > 0:
        usd_entrada = monto_ars / tipo_cambio_entrada
        rendimiento_usd = usd_actual - usd_entrada
        rendimiento_usd_pct = (rendimiento_usd / usd_entrada * 100) if usd_entrada > 0 else 0
    else:
        rendimiento_usd = 0
        rendimiento_usd_pct = 0

    return {
        "dias_transcurridos": dias,
        "rendimiento_ars_pct": round(rendimiento_ars_pct, 2),
        "monto_ars_final_estimado": round(monto_ars_final, 2),
        "usd_actual_estimado": round(usd_actual, 2),
        "rendimiento_usd": round(rendimiento_usd, 2),
        "rendimiento_usd_pct": round(rendimiento_usd_pct, 2),
    }


def calcular_allocation(
    posiciones_rf: list[dict],
    capital_usd: float,
    dolar_mep_actual: float,
) -> dict:
    """
    Calcula la distribución actual del capital entre RF y efectivo en USD.

    Returns:
        {total_usd_rf, total_usd_libre, pct_rf, pct_libre}
    """
    if not capital_usd or capital_usd <= 0:
        return {"total_usd_rf": 0, "total_usd_libre": 0, "pct_rf": 0, "pct_libre": 100}

    total_ars_rf = sum(
        p.get("monto_ars", 0)
        for p in posiciones_rf
        if p.get("estado") == "abierta"
    )
    total_usd_rf = total_ars_rf / dolar_mep_actual if dolar_mep_actual > 0 else 0
    total_usd_libre = max(0, capital_usd - total_usd_rf)
    pct_rf = round(total_usd_rf / capital_usd * 100, 1)
    pct_libre = round(total_usd_libre / capital_usd * 100, 1)

    return {
        "total_usd_rf": round(total_usd_rf, 2),
        "total_usd_libre": round(total_usd_libre, 2),
        "pct_rf": pct_rf,
        "pct_libre": pct_libre,
    }
