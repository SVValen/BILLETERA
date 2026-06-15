import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request
from lib.date_utils import mes_rango, validate_mes

app = FastAPI()


@app.get("/api/stats")
async def get_stats(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    mes = request.query_params.get("mes", "")
    if not mes:
        return JSONResponse({"error": "Falta parámetro 'mes'"}, status_code=400)
    if not validate_mes(mes):
        return JSONResponse({"error": "Formato de mes inválido (YYYY-MM)"}, status_code=400)

    start, end = mes_rango(mes)
    supabase = get_supabase()

    response = (
        supabase.table("movimientos")
        .select("monto, tipo, categorias(nombre, emoji)")
        .eq("usuario_id", telegram_id)
        .neq("estado", "anulado")
        .gte("fecha", start)
        .lt("fecha", end)
        .execute()
    )

    rows = response.data or []
    gastos = [r for r in rows if r["tipo"] == "gasto"]
    ingresos = [r for r in rows if r["tipo"] == "ingreso"]

    total_gastos = sum(r["monto"] for r in gastos)
    total_ingresos = sum(r["monto"] for r in ingresos)

    por_categoria: dict[str, dict] = {}
    for r in gastos:
        cat = r.get("categorias") or {}
        nombre = cat.get("nombre", "Otros")
        emoji = cat.get("emoji", "📌")
        if nombre not in por_categoria:
            por_categoria[nombre] = {"monto": 0, "emoji": emoji}
        por_categoria[nombre]["monto"] += r["monto"]

    return JSONResponse({
        "mes": mes,
        "total_gastos": total_gastos,
        "total_ingresos": total_ingresos,
        "saldo": total_ingresos - total_gastos,
        "por_categoria": por_categoria,
    })
