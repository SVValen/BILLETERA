import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request
from lib.date_utils import add_months

app = FastAPI()


@app.get("/api/cuotas")
async def get_cuotas(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    rows = (
        supabase.table("cuotas_plan")
        .select("*, categorias(nombre, emoji)")
        .eq("usuario_id", telegram_id)
        .eq("activo", True)
        .not_.is_("fecha_primera_cuota", "null")
        .order("created_at", desc=True)
        .execute()
    )

    hoy = date.today()
    result = []
    for p in (rows.data or []):
        primera = date.fromisoformat(p["fecha_primera_cuota"])
        n = p["num_cuotas"]

        meses_transcurridos = (hoy.year - primera.year) * 12 + (hoy.month - primera.month)
        pagadas = min(meses_transcurridos + 1, n)
        restantes = n - pagadas

        prox = add_months(primera, pagadas) if restantes > 0 else None

        cat = p.get("categorias") or {}
        result.append({
            "id": p["id"],
            "descripcion": p["descripcion"],
            "categoria": cat.get("nombre", "Otros"),
            "emoji": cat.get("emoji", "📌"),
            "monto_total": p["monto_total"],
            "monto_cuota": p["monto_cuota"],
            "num_cuotas": n,
            "pagadas": pagadas,
            "restantes": restantes,
            "porcentaje": round(pagadas / n * 100, 0),
            "proxima_cuota": prox.isoformat() if prox else None,
            "fecha_primera": p["fecha_primera_cuota"],
        })

    result = [r for r in result if r["restantes"] > 0]
    result.sort(key=lambda x: x["proxima_cuota"] or "")
    return JSONResponse(result)
