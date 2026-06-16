"""
Cron de inversiones — se ejecuta cada 30 minutos.
1. Actualiza precios + indicadores de todos los activos activos.
2. Para cada usuario con perfil de inversión, evalúa si hay señal.
3. Si hay señal → llama Claude → envía recomendación por Telegram.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lib.supabase_client import get_supabase
from lib.market_data import fetch_precio_activo, fetch_historico_activo
from lib.indicators import calcular_rsi, calcular_ema, detectar_tendencia, tiene_senal, interpretar_rsi
from lib.claude_invest import generar_recomendacion, formatear_mensaje_telegram

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")


async def _send_telegram(chat_id: str, text: str, reply_markup: dict | None = None) -> int | None:
    """Envía mensaje y retorna el message_id."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        import json
        payload["reply_markup"] = json.dumps(reply_markup)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload,
        )
        data = r.json()
        if data.get("ok"):
            return data["result"]["message_id"]
    return None


async def _actualizar_activo(activo: dict, supabase) -> dict | None:
    """Fetchea precio + calcula indicadores + guarda en BD. Retorna activo actualizado."""
    precio_data = await fetch_precio_activo(activo)
    if not precio_data:
        return None

    historico = await fetch_historico_activo(activo, limite=60)

    rsi = calcular_rsi(historico) if len(historico) >= 15 else None
    ema_20 = calcular_ema(historico, 20) if len(historico) >= 20 else None
    ema_50 = calcular_ema(historico, 50) if len(historico) >= 50 else None
    tendencia = detectar_tendencia(historico) if len(historico) >= 25 else "lateral"

    update_data = {
        "precio_actual": precio_data["precio"],
        "rsi": rsi,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "tendencia": tendencia,
        "ultimo_update": "now()",
    }
    # Para activos en ARS, precio_actual ya es ARS
    if precio_data.get("moneda") == "ARS":
        update_data["precio_ars"] = precio_data["precio"]

    supabase.table("activos").update(update_data).eq("id", activo["id"]).execute()

    # Guardar en historial de precios (para análisis futuro)
    supabase.table("precios_historicos").insert({
        "activo_id": activo["id"],
        "precio": precio_data["precio"],
    }).execute()

    return {**activo, **update_data, "moneda": activo["moneda"]}


async def _calcular_winrate(usuario_id: str, supabase) -> float | None:
    r = (
        supabase.table("decisiones_inversion")
        .select("resultado")
        .eq("usuario_id", usuario_id)
        .eq("accion", "aceptada")
        .execute()
    )
    decisiones = r.data or []
    if not decisiones:
        return None
    exitosas = sum(1 for d in decisiones if d["resultado"] == "exitoso")
    return round(exitosas / len(decisiones) * 100, 1)


async def _ya_tiene_recomendacion_pendiente(usuario_id: str, activo_id: int, supabase) -> bool:
    """Evita spam: no generar si ya hay una pendiente para este activo/usuario."""
    r = (
        supabase.table("recomendaciones")
        .select("id")
        .eq("usuario_id", usuario_id)
        .eq("activo_id", activo_id)
        .eq("estado", "pendiente")
        .execute()
    )
    return bool(r.data)


@app.get("/api/cron_inversiones")
@app.get("/")
async def cron_inversiones(request: Request):
    # Validar CRON_SECRET
    cron_secret = os.getenv("CRON_SECRET", "")
    if cron_secret and request.headers.get("authorization") != f"Bearer {cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    supabase = get_supabase()

    # 1. Actualizar todos los activos activos
    activos_r = supabase.table("activos").select("*").eq("activo", True).execute()
    activos = activos_r.data or []

    activos_actualizados = {}
    for activo in activos:
        actualizado = await _actualizar_activo(activo, supabase)
        if actualizado:
            activos_actualizados[activo["id"]] = actualizado

    # 2. Para cada usuario con perfil, evaluar señales
    perfiles_r = supabase.table("perfiles_inversion").select("*").execute()
    perfiles = perfiles_r.data or []

    recomendaciones_generadas = 0

    for perfil in perfiles:
        usuario_id = perfil["usuario_id"]
        winrate = await _calcular_winrate(usuario_id, supabase)

        for activo_id, activo in activos_actualizados.items():
            rsi = activo.get("rsi")
            tendencia = activo.get("tendencia", "lateral")

            if not tiene_senal(rsi, tendencia):
                continue

            if await _ya_tiene_recomendacion_pendiente(usuario_id, activo_id, supabase):
                continue

            interp = interpretar_rsi(rsi)
            rec = generar_recomendacion(
                perfil=perfil,
                activo=activo,
                rsi=rsi,
                ema_20=activo.get("ema_20"),
                ema_50=activo.get("ema_50"),
                tendencia=tendencia,
                interpretacion_rsi=interp,
                winrate=winrate,
            )
            if not rec:
                continue

            # Guardar recomendación en BD
            rec_insert = supabase.table("recomendaciones").insert({
                "usuario_id": usuario_id,
                "activo_id": activo_id,
                "accion": rec["accion"],
                "razon": rec["razon"],
                "precio_recomendacion": activo.get("precio_actual") or activo.get("precio_ars"),
                "rsi_momento": rsi,
                "confianza": rec["confianza"],
                "estado": "pendiente",
            }).execute()

            if not rec_insert.data:
                continue

            rec_id = rec_insert.data[0]["id"]

            # Enviar por Telegram
            texto, reply_markup = formatear_mensaje_telegram(activo, rec, rec_id)
            try:
                msg_id = await _send_telegram(usuario_id, texto, reply_markup)
                if msg_id:
                    supabase.table("recomendaciones").update({
                        "telegram_message_id": msg_id
                    }).eq("id", rec_id).execute()
                recomendaciones_generadas += 1
            except Exception:
                pass

    return JSONResponse({
        "ok": True,
        "activos_actualizados": len(activos_actualizados),
        "recomendaciones_generadas": recomendaciones_generadas,
    })


@app.get("/api/cron_inversiones/outcomes")
async def actualizar_outcomes(request: Request):
    """
    Job diario: actualiza el resultado de decisiones aceptadas
    comparando precio de entrada vs precio actual.
    """
    cron_secret = os.getenv("CRON_SECRET", "")
    if cron_secret and request.headers.get("authorization") != f"Bearer {cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    supabase = get_supabase()

    # Decisiones aceptadas con resultado pendiente
    r = (
        supabase.table("decisiones_inversion")
        .select("id, recomendacion_id, precio_entrada, recomendaciones(activo_id)")
        .eq("accion", "aceptada")
        .eq("resultado", "pendiente")
        .execute()
    )

    actualizados = 0
    for dec in (r.data or []):
        activo_id = dec["recomendaciones"]["activo_id"]
        activo_r = supabase.table("activos").select("precio_actual, precio_ars").eq("id", activo_id).limit(1).execute()
        if not activo_r.data:
            continue

        precio_actual = activo_r.data[0].get("precio_actual") or activo_r.data[0].get("precio_ars")
        precio_entrada = dec.get("precio_entrada")

        if not precio_actual or not precio_entrada:
            continue

        ganancia_pct = round((precio_actual - precio_entrada) / precio_entrada * 100, 2)
        resultado = "exitoso" if ganancia_pct > 2 else "fallido" if ganancia_pct < -2 else "neutral"

        supabase.table("decisiones_inversion").update({
            "precio_7d": precio_actual,
            "ganancia_pct": ganancia_pct,
            "resultado": resultado,
        }).eq("id", dec["id"]).execute()
        actualizados += 1

    return JSONResponse({"ok": True, "actualizados": actualizados})
