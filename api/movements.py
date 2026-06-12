import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase

app = FastAPI()


@app.get("/api/movements")
async def get_movements(request: Request):
    """Retorna movimientos de un mes.

    Query param: mes=YYYY-MM  (ej. 2025-01)
    """
    mes = request.query_params.get("mes", "")
    if not mes:
        return JSONResponse({"error": "Falta parámetro 'mes' (ej. ?mes=2025-01)"}, status_code=400)

    supabase = get_supabase()

    response = (
        supabase.table("movimientos")
        .select("id, fecha, descripcion, monto, tipo, origen, categorias(nombre, emoji)")
        .like("fecha", f"{mes}%")
        .order("fecha", desc=True)
        .execute()
    )

    return JSONResponse(response.data)
