import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import calendar
from datetime import date, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()


def _next_occurrence(dia: int, desde: date) -> date:
    """Próxima fecha en que ocurre el día 'dia' del mes."""
    if desde.day <= dia:
        try:
            return desde.replace(day=dia)
        except ValueError:
            pass
    year = desde.year + (1 if desde.month == 12 else 0)
    month = 1 if desde.month == 12 else desde.month + 1
    day = min(dia, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@app.get("/api/recurrentes")
async def get_recurrentes_proximos(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    dias = int(request.query_params.get("dias", "35"))
    supabase = get_supabase()
    rows = (
        supabase.table("recurrentes")
        .select("id, descripcion, monto, dia_del_mes, categoria_id, categorias(nombre, emoji)")
        .eq("usuario_id", telegram_id)
        .eq("activo", True)
        .execute()
    )

    hoy = date.today()
    horizonte = hoy + timedelta(days=dias)

    result = []
    for r in (rows.data or []):
        prox = _next_occurrence(r["dia_del_mes"], hoy)
        cat = r.get("categorias") or {}
        result.append({
            "id": r["id"],
            "descripcion": r["descripcion"],
            "monto": r["monto"],
            "dia_del_mes": r["dia_del_mes"],
            "categoria": cat.get("nombre", "Otros"),
            "emoji": cat.get("emoji", "📌"),
            "proxima_fecha": prox.isoformat(),
            "dias_faltan": (prox - hoy).days,
        })

    result.sort(key=lambda x: x["proxima_fecha"])
    return JSONResponse(result)


@app.delete("/api/recurrentes")
async def delete_recurrente(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    id_ = request.query_params.get("id")
    if not id_:
        return JSONResponse({"error": "Falta parámetro 'id'"}, status_code=400)

    supabase = get_supabase()
    supabase.table("recurrentes").update({"activo": False}).eq("id", int(id_)).eq("usuario_id", telegram_id).execute()
    return JSONResponse({"ok": True})
