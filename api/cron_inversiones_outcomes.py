"""
Cron diario 03:00 UTC: actualiza resultado de decisiones aceptadas.
Vercel no rutea sub-paths (/api/cron_inversiones/outcomes → 404),
por eso este job vive en su propio archivo.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase

app = FastAPI()


@app.get("/api/cron_inversiones_outcomes")
@app.get("/")
async def actualizar_outcomes(request: Request):
    """Actualiza el resultado de decisiones aceptadas comparando precio entrada vs precio actual."""
    cron_secret = os.getenv("CRON_SECRET", "")
    if cron_secret and request.headers.get("authorization") != f"Bearer {cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    supabase = get_supabase()

    r = (
        supabase.table("decisiones_inversion")
        .select("id, recomendacion_id, precio_entrada, recomendaciones(activo_id)")
        .eq("accion", "aceptada")
        .eq("resultado", "pendiente")
        .execute()
    )

    actualizados = 0
    for dec in (r.data or []):
        activo_id = (dec.get("recomendaciones") or {}).get("activo_id")
        if not activo_id:
            continue

        activo_r = supabase.table("activos").select("precio_actual, precio_ars").eq("id", activo_id).limit(1).execute()
        if not activo_r.data:
            continue

        precio_actual = activo_r.data[0].get("precio_actual") or activo_r.data[0].get("precio_ars")
        precio_entrada = dec.get("precio_entrada")

        if not precio_actual or not precio_entrada:
            continue

        ganancia_pct = round((float(precio_actual) - float(precio_entrada)) / float(precio_entrada) * 100, 2)
        resultado = "exitoso" if ganancia_pct > 2 else "fallido" if ganancia_pct < -2 else "neutral"

        supabase.table("decisiones_inversion").update({
            "precio_7d": precio_actual,
            "ganancia_pct": ganancia_pct,
            "resultado": resultado,
        }).eq("id", dec["id"]).execute()
        actualizados += 1

    return JSONResponse({"ok": True, "actualizados": actualizados})
