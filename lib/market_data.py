"""
Fetchers de precios de mercado.
Fuentes: CoinGecko (crypto), IOL (CEDEARs/acciones AR), dolarapi (dólar).
Nota: Binance bloquea IPs de Vercel (HTTP 451), se usa CoinGecko en su lugar.
"""
import os
import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

IOL_BASE       = "https://api.invertironline.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DOLAR_BASE     = "https://dolarapi.com/v1"

# Mapeo símbolo Binance → id CoinGecko
COINGECKO_IDS: dict[str, str] = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT":  "ethereum",
}

# Endpoints válidos de dolarapi (usdt no existe, se usa cripto)
DOLAR_TIPOS_VALIDOS = {"oficial", "blue", "bolsa", "contadoconliqui", "tarjeta", "mayorista", "cripto"}

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
                    return {"precio": float(precio), "moneda": "ARS", "variacion_pct": float(variacion)}
            logger.debug(f"IOL individual {simbolo} status={r.status_code}, intentando batch")
    except Exception as e:
        logger.debug(f"IOL individual {simbolo}: {e}, intentando batch")

    # Fallback: endpoint batch de CEDEARs
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/Cotizaciones/acciones/cedears/bCBA",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            data = r.json()
            for t in data.get("titulos", []):
                if t.get("simbolo", "").upper() == simbolo.upper():
                    return {
                        "precio": float(t.get("ultimoPrecio", 0)),
                        "moneda": "ARS",
                        "variacion_pct": float(t.get("variacionPorcentual", 0)),
                    }
    except Exception as e:
        logger.error(f"IOL batch {simbolo}: {e}")
    return None


async def fetch_iol_historico(simbolo: str, dias: int = 60) -> list[float]:
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
            items = sorted(data, key=lambda x: x.get("fechaHora", ""))
            return [float(item["ultimoPrecio"]) for item in items if item.get("ultimoPrecio")]
    except Exception as e:
        logger.error(f"IOL historico {simbolo}: {e}")
    return []


async def fetch_iol_debug(simbolo: str = "AAPL") -> dict:
    """Diagnóstico completo de IOL: estado del token + respuesta cruda."""
    result: dict = {"token_ok": False, "individual": None, "batch_sample": None, "error": None}

    user = os.getenv("IOL_USER")
    password = os.getenv("IOL_PASSWORD")
    if not user or not password:
        result["error"] = "IOL_USER / IOL_PASSWORD no configurados en variables de entorno"
        return result

    token = await _iol_get_token()
    if not token:
        result["error"] = "No se pudo obtener token — verificar credenciales IOL"
        return result

    result["token_ok"] = True

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/bCBA/Titulos/{simbolo}/Cotizacion",
                headers={"Authorization": f"Bearer {token}"},
            )
            ct = r.headers.get("content-type", "")
            result["individual"] = {
                "status": r.status_code,
                "body": r.json() if "json" in ct else r.text[:500],
            }
    except Exception as e:
        result["individual"] = {"error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{IOL_BASE}/api/v2/Cotizaciones/acciones/cedears/bCBA",
                headers={"Authorization": f"Bearer {token}"},
            )
            ct = r.headers.get("content-type", "")
            data = r.json() if "json" in ct else {}
            titulos = data.get("titulos", [])[:3] if isinstance(data, dict) else []
            result["batch_sample"] = {
                "status": r.status_code,
                "total_titulos": len(data.get("titulos", [])) if isinstance(data, dict) else 0,
                "primeros_3": titulos,
            }
    except Exception as e:
        result["batch_sample"] = {"error": str(e)}

    return result


# ============================================================
# CoinGecko — crypto (reemplaza Binance, sin bloqueos geo)
# ============================================================

async def fetch_coingecko_precio(simbolo: str) -> dict | None:
    """
    Retorna precio actual de crypto vía CoinGecko.
    simbolo: 'BTCUSDT', 'ETHUSDT' (mismo formato que Binance para compatibilidad)
    {precio, moneda}
    """
    coin_id = COINGECKO_IDS.get(simbolo.upper())
    if not coin_id:
        logger.warning(f"CoinGecko: símbolo {simbolo} no mapeado")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{COINGECKO_BASE}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
            precio = data.get(coin_id, {}).get("usd")
            if precio:
                return {"precio": float(precio), "moneda": "USD"}
    except Exception as e:
        logger.error(f"CoinGecko precio {simbolo}: {e}")
    return None


async def fetch_coingecko_historico(simbolo: str, limit: int = 60) -> list[float]:
    """
    Retorna lista de precios de cierre horarios para calcular RSI/EMA.
    CoinGecko devuelve hasta 90 días de datos horarios.
    """
    coin_id = COINGECKO_IDS.get(simbolo.upper())
    if not coin_id:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": 3, "interval": "hourly"},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            prices = r.json().get("prices", [])
            # [[timestamp_ms, price], ...] → tomar últimos `limit`
            return [float(p[1]) for p in prices[-limit:]]
    except Exception as e:
        logger.error(f"CoinGecko historico {simbolo}: {e}")
    return []


# ============================================================
# dolarapi — dólar
# ============================================================

async def fetch_dolar_precio(tipo: str = "oficial") -> dict | None:
    """
    Retorna precio del dólar en ARS.
    tipos válidos: oficial, blue, bolsa, contadoconliqui, tarjeta, mayorista, cripto
    Nota: 'usdt' no existe en dolarapi — usar 'cripto'
    """
    # Normalizar alias comunes
    if tipo == "usdt":
        tipo = "cripto"

    if tipo not in DOLAR_TIPOS_VALIDOS:
        logger.warning(f"dolarapi: tipo '{tipo}' no válido, usando 'oficial'")
        tipo = "oficial"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{DOLAR_BASE}/dolares/{tipo}")
            r.raise_for_status()
            data = r.json()
            precio = data.get("venta") or data.get("compra")
            return {"precio": float(precio), "moneda": "ARS"} if precio else None
    except Exception as e:
        logger.error(f"dolarapi {tipo}: {e}")
    return None


# ============================================================
# Dispatcher — elige fuente según activo
# ============================================================

async def fetch_precio_activo(activo: dict) -> dict | None:
    fuente = activo["fuente"]
    simbolo = activo["simbolo_fuente"]

    if fuente == "binance":
        # binance → usar CoinGecko (Binance bloquea Vercel)
        return await fetch_coingecko_precio(simbolo)

    if fuente == "iol":
        return await fetch_iol_precio(simbolo)

    if fuente == "dolarapi":
        return await fetch_dolar_precio(simbolo)

    logger.warning(f"Fuente desconocida: {fuente}")
    return None


async def fetch_historico_activo(activo: dict, limite: int = 60) -> list[float]:
    fuente = activo["fuente"]
    simbolo = activo["simbolo_fuente"]

    if fuente == "binance":
        return await fetch_coingecko_historico(simbolo, limit=limite)

    if fuente == "iol":
        return await fetch_iol_historico(simbolo, dias=limite)

    return []
