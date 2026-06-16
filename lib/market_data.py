"""
Fetchers de precios de mercado.
Fuentes: Binance (crypto), IOL (CEDEARs/acciones AR), dolarapi (dólar/USDT).
"""
import os
import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

IOL_BASE = "https://api.invertironline.com"
BINANCE_BASE = "https://api.binance.com/api/v3"
DOLAR_BASE = "https://dolarapi.com/v1"

# ============================================================
# IOL — autenticación con caché de token
# ============================================================

_iol_token: str | None = None
_iol_token_expiry: datetime | None = None


async def _iol_get_token() -> str | None:
    global _iol_token, _iol_token_expiry

    now = datetime.now(timezone.utc)
    if _iol_token and _iol_token_expiry and now < _iol_token_expiry:
        return _iol_token

    user = os.getenv("IOL_USER")
    password = os.getenv("IOL_PASSWORD")
    if not user or not password:
        logger.warning("IOL_USER / IOL_PASSWORD no configurados")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{IOL_BASE}/token",
                data={
                    "grant_type": "password",
                    "username": user,
                    "password": password,
                    "scope": "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            r.raise_for_status()
            data = r.json()
            _iol_token = data["access_token"]
            expires_in = int(data.get("expires_in", 1800))
            from datetime import timedelta
            _iol_token_expiry = now + timedelta(seconds=expires_in - 60)
            return _iol_token
    except Exception as e:
        logger.error(f"IOL auth error: {e}")
        return None


async def fetch_iol_precio(simbolo: str) -> dict | None:
    """
    Retorna precio actual de un CEDEAR o acción argentina vía IOL.
    Intenta endpoint individual primero (rápido), cae al batch si falla.
    {precio, moneda, variacion_pct}
    """
    token = await _iol_get_token()
    if not token:
        return None

    # Intentar endpoint individual
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/bCBA/Titulos/{simbolo}/Cotizacion",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                data = r.json()
                precio = data.get("ultimoPrecio") or data.get("ultimo") or data.get("price")
                variacion = data.get("variacionPorcentual") or data.get("variation") or 0
                if precio:
                    return {
                        "precio": float(precio),
                        "moneda": "ARS",
                        "variacion_pct": float(variacion),
                    }
            logger.debug(f"IOL individual {simbolo} status={r.status_code}, intentando batch")
    except Exception as e:
        logger.debug(f"IOL individual {simbolo} error: {e}, intentando batch")

    # Fallback: endpoint batch de CEDEARs
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/Cotizaciones/acciones/cedears/bCBA",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = r.json()
            titulos = data.get("titulos", [])
            for t in titulos:
                if t.get("simbolo", "").upper() == simbolo.upper():
                    return {
                        "precio": float(t.get("ultimoPrecio", 0)),
                        "moneda": "ARS",
                        "variacion_pct": float(t.get("variacionPorcentual", 0)),
                    }
    except Exception as e:
        logger.error(f"IOL batch {simbolo}: {e}")
    return None


async def fetch_iol_debug(simbolo: str = "AAPL") -> dict:
    """
    Diagnóstico completo de IOL: estado del token + respuesta cruda del endpoint.
    Retorna dict con info para debugging.
    """
    result: dict = {"token_ok": False, "individual": None, "batch_sample": None, "error": None}

    user = os.getenv("IOL_USER")
    password = os.getenv("IOL_PASSWORD")
    if not user or not password:
        result["error"] = "IOL_USER / IOL_PASSWORD no configurados"
        return result

    token = await _iol_get_token()
    if not token:
        result["error"] = "No se pudo obtener token (verificar credenciales)"
        return result

    result["token_ok"] = True

    # Probar endpoint individual
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/bCBA/Titulos/{simbolo}/Cotizacion",
                headers={"Authorization": f"Bearer {token}"},
            )
            result["individual"] = {
                "status": r.status_code,
                "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500],
            }
    except Exception as e:
        result["individual"] = {"error": str(e)}

    # Probar endpoint batch (solo primeros 3 títulos para no saturar)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/Cotizaciones/acciones/cedears/bCBA",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            titulos = data.get("titulos", [])[:3] if isinstance(data, dict) else []
            result["batch_sample"] = {
                "status": r.status_code,
                "total_titulos": len(data.get("titulos", [])) if isinstance(data, dict) else 0,
                "primeros_3": titulos,
            }
    except Exception as e:
        result["batch_sample"] = {"error": str(e)}

    return result


async def fetch_iol_historico(simbolo: str, dias: int = 60) -> list[float]:
    """
    Retorna lista de precios de cierre históricos para calcular RSI/EMA.
    """
    token = await _iol_get_token()
    if not token:
        return []

    from datetime import date, timedelta
    hasta = date.today().isoformat()
    desde = (date.today() - timedelta(days=dias)).isoformat()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/bCBA/Titulos/{simbolo}/Cotizacion/seriehistorica/{desde}/{hasta}/ajustada",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = r.json()
            # Ordenar por fecha ASC y extraer cierres
            items = sorted(data, key=lambda x: x.get("fechaHora", ""))
            return [float(item["ultimoPrecio"]) for item in items if item.get("ultimoPrecio")]
    except Exception as e:
        logger.error(f"IOL historico {simbolo}: {e}")
    return []


# ============================================================
# Binance — crypto
# ============================================================

async def fetch_binance_precio(simbolo: str) -> dict | None:
    """
    Retorna precio actual de un par en Binance.
    simbolo: 'BTCUSDT', 'ETHUSDT'
    {precio, moneda}
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BINANCE_BASE}/ticker/price", params={"symbol": simbolo})
            r.raise_for_status()
            data = r.json()
            return {"precio": float(data["price"]), "moneda": "USD"}
    except Exception as e:
        logger.error(f"Binance precio {simbolo}: {e}")
    return None


async def fetch_binance_historico(simbolo: str, interval: str = "1h", limit: int = 60) -> list[float]:
    """
    Retorna lista de precios de cierre de velas para calcular RSI/EMA.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{BINANCE_BASE}/klines",
                params={"symbol": simbolo, "interval": interval, "limit": limit},
            )
            r.raise_for_status()
            # klines[i][4] = close price
            return [float(k[4]) for k in r.json()]
    except Exception as e:
        logger.error(f"Binance historico {simbolo}: {e}")
    return []


# ============================================================
# dolarapi — dólar / USDT
# ============================================================

async def fetch_dolar_precio(tipo: str = "usdt") -> dict | None:
    """
    Retorna precio del dólar/USDT en ARS.
    tipo: 'oficial', 'blue', 'usdt', 'cripto'
    {precio, moneda}
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{DOLAR_BASE}/dolares/{tipo}")
            r.raise_for_status()
            data = r.json()
            # Usar precio de venta (lo que pagás para comprar dólares)
            precio = data.get("venta") or data.get("compra")
            return {"precio": float(precio), "moneda": "ARS"}
    except Exception as e:
        logger.error(f"dolarapi {tipo}: {e}")
    return None


# ============================================================
# Dispatcher — elige fuente según activo
# ============================================================

async def fetch_precio_activo(activo: dict) -> dict | None:
    """
    Dado un registro de la tabla `activos`, fetchea el precio actual.
    Retorna {precio, precio_ars, moneda} o None si falla.
    """
    fuente = activo["fuente"]
    simbolo = activo["simbolo_fuente"]

    if fuente == "binance":
        return await fetch_binance_precio(simbolo)

    if fuente == "iol":
        return await fetch_iol_precio(simbolo)

    if fuente == "dolarapi":
        return await fetch_dolar_precio(simbolo)

    logger.warning(f"Fuente desconocida: {fuente}")
    return None


async def fetch_historico_activo(activo: dict, limite: int = 60) -> list[float]:
    """
    Dado un registro de la tabla `activos`, retorna historial de cierres.
    """
    fuente = activo["fuente"]
    simbolo = activo["simbolo_fuente"]

    if fuente == "binance":
        return await fetch_binance_historico(simbolo, limit=limite)

    if fuente == "iol":
        return await fetch_iol_historico(simbolo, dias=limite)

    # dolarapi no tiene histórico útil para indicadores
    return []
