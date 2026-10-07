"""
Dólar para convertir gastos en USD: tipo de cambio mayorista de referencia
del BCRA (Com. A 3500, variable 5 de la API de estadísticas), el mismo que se
usa en la planilla. Se guarda una vez por día en `cotizaciones`.

Si el BCRA no responde, cae al dólar oficial de dolarapi.com (venta).
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx

from lib.supabase_client import get_supabase

BCRA_URL = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/5"
DOLARAPI_URL = "https://dolarapi.com/v1/dolares/oficial"
FUENTE_BCRA = "bcra_a3500"
FUENTE_FALLBACK = "dolarapi_oficial"


def _guardar(fecha: str, fuente: str, valor: float) -> None:
    try:
        get_supabase().table("cotizaciones").upsert(
            {"fecha": fecha, "fuente": fuente, "valor": round(valor, 4)},
            on_conflict="fecha,fuente",
        ).execute()
    except Exception:
        pass


def _ultima_guardada(desde: date) -> float | None:
    r = (
        get_supabase().table("cotizaciones").select("valor, fecha")
        .eq("fuente", FUENTE_BCRA).gte("fecha", desde.isoformat())
        .order("fecha", desc=True).limit(1).execute()
    )
    return float(r.data[0]["valor"]) if r.data else None


async def _fetch_bcra() -> tuple[str, float] | None:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(BCRA_URL, params={"limit": 1})
            if r.status_code != 200:
                return None
            det = r.json()["results"][0]["detalle"][0]
            return det["fecha"], float(det["valor"])
    except Exception:
        return None


async def _fetch_dolarapi() -> float | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(DOLARAPI_URL)
            if r.status_code == 200:
                return float(r.json()["venta"])
    except Exception:
        pass
    return None


async def actualizar_cotizacion() -> float | None:
    """Trae el último valor del BCRA y lo guarda. Lo llama el cron diario."""
    res = await _fetch_bcra()
    if res:
        fecha, valor = res
        _guardar(fecha, FUENTE_BCRA, valor)
        return valor
    return None


async def get_dolar() -> float | None:
    """Dólar a usar hoy. Usa el valor del BCRA guardado en los últimos 4 días
    (cubre fines de semana y feriados); si no hay, lo busca; si el BCRA no
    responde, usa el oficial de dolarapi."""
    try:
        guardado = _ultima_guardada(date.today() - timedelta(days=4))
        if guardado:
            return guardado
    except Exception:
        pass
    valor = await actualizar_cotizacion()
    if valor:
        return valor
    valor = await _fetch_dolarapi()
    if valor:
        _guardar(date.today().isoformat(), FUENTE_FALLBACK, valor)
    return valor


def campos_usd(monto_usd: float, tasa: float) -> dict:
    """Campos de un movimiento en USD: monto en pesos + original + tipo de cambio."""
    return {
        "monto": round(monto_usd * tasa, 2),
        "moneda": "USD",
        "monto_original": round(monto_usd, 2),
        "tipo_cambio": round(tasa, 4),
    }
