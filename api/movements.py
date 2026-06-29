import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request
from lib.date_utils import mes_rango, validate_mes

app = FastAPI()

PAGE_SIZE = 20
_CUOTA_RE = re.compile(r"\(cuota (\d+)/(\d+)\)")


@app.get("/api/movements")
async def get_movements(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    mes = request.query_params.get("mes", "")
    q = request.query_params.get("q", "").strip()
    try:
        pagina = max(1, int(request.query_params.get("pagina", "1")))
    except ValueError:
        pagina = 1
    todos = request.query_params.get("todos", "")
    tipo = request.query_params.get("tipo", "").strip()
    categoria_id = request.query_params.get("categoria_id", "").strip()
    tarjeta_id = request.query_params.get("tarjeta_id", "").strip()

    supabase = get_supabase()
    query = (
        supabase.table("movimientos")
        .select("id, fecha, descripcion, monto, tipo, origen, categorias(nombre, emoji), tarjeta_id, es_pago_tarjeta, tarjetas(nombre)", count="exact")
        .eq("usuario_id", telegram_id)
        .neq("estado", "anulado")
        .order("fecha", desc=True)
        .order("id", desc=True)
    )

    if mes:
        if not validate_mes(mes):
            return JSONResponse({"error": "Formato de mes inválido (YYYY-MM)"}, status_code=400)
        start, end = mes_rango(mes)
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

    if tarjeta_id:
        try:
            query = query.eq("tarjeta_id", int(tarjeta_id))
        except ValueError:
            pass

    if not todos:
        offset = (pagina - 1) * PAGE_SIZE
        query = query.range(offset, offset + PAGE_SIZE - 1)

    response = query.execute()
    total = response.count or 0

    data = response.data or []
    for r in data:
        m = _CUOTA_RE.search(r.get("descripcion") or "")
        if r.get("es_pago_tarjeta"):
            r["forma_pago"] = "Pago resumen"
        elif m:
            r["forma_pago"] = f"Cuota {m.group(1)}/{m.group(2)}"
        elif r.get("tarjeta_id"):
            r["forma_pago"] = "1 pago"
        else:
            r["forma_pago"] = "—"

    return JSONResponse({
        "data": data,
        "total": total,
        "pagina": pagina,
        "paginas": max(1, -(-total // PAGE_SIZE)),
        "page_size": PAGE_SIZE,
    })
