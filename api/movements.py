import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase


app = FastAPI()


def _mes_rango(mes: str) -> tuple[str, str]:
    """Dado 'YYYY-MM', retorna (primer_dia, primer_dia_mes_siguiente)."""
    year, month = int(mes[:4]), int(mes[5:7])
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"
    return start, end


@app.get("/api/movements")
async def get_movements(request: Request):
    mes = request.query_params.get("mes", "")
    if not mes:
        return JSONResponse({"error": "Falta parámetro 'mes' (ej. ?mes=2025-01)"}, status_code=400)

    start, end = _mes_rango(mes)
    supabase = get_supabase()

    response = (
        supabase.table("movimientos")
        .select("id, fecha, descripcion, monto, tipo, origen, categorias(nombre, emoji)")
        .gte("fecha", start)
        .lt("fecha", end)
        .order("fecha", desc=True)
        .execute()
    )

    return JSONResponse(response.data)
