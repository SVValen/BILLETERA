import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()

PAGE_SIZE = 20


def _mes_rango(mes: str) -> tuple[str, str]:
    year, month = int(mes[:4]), int(mes[5:7])
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    return start, end


@app.get("/api/movements")
async def get_movements(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    mes = request.query_params.get("mes", "")
    q = request.query_params.get("q", "").strip()
    pagina = max(1, int(request.query_params.get("pagina", "1")))
    todos = request.query_params.get("todos", "")
    tipo = request.query_params.get("tipo", "").strip()
    categoria_id = request.query_params.get("categoria_id", "").strip()

    supabase = get_supabase()
    query = (
        supabase.table("movimientos")
        .select("id, fecha, descripcion, monto, tipo, origen, categorias(nombre, emoji)", count="exact")
        .eq("usuario_id", telegram_id)
        .order("fecha", desc=True)
        .order("id", desc=True)
    )

    if mes:
        start, end = _mes_rango(mes)
        query = query.gte("fecha", start).lt("fecha", end)

    if q:
        query = query.ilike("descripcion", f"%{q}%")

    if tipo in ("gasto", "ingreso"):
        query = query.eq("tipo", tipo)

    if categoria_id:
        try:
            query = query.eq("categoria_id", int(categoria_id))
        except ValueError:
            pass

    if not todos:
        offset = (pagina - 1) * PAGE_SIZE
        query = query.range(offset, offset + PAGE_SIZE - 1)

    response = query.execute()
    total = response.count or 0

    return JSONResponse({
        "data": response.data or [],
        "total": total,
        "pagina": pagina,
        "paginas": max(1, -(-total // PAGE_SIZE)),
        "page_size": PAGE_SIZE,
    })
