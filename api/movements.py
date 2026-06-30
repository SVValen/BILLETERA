import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request
from lib.date_utils import mes_rango, validate_mes
from api.bot.helpers import _save_learned_keywords

app = FastAPI()

PAGE_SIZE = 20
_CUOTA_RE = re.compile(r"\(cuota (\d+)/(\d+)\)")
_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    mes_resumen = request.query_params.get("mes_resumen", "").strip()
    fecha_desde = request.query_params.get("fecha_desde", "").strip()
    fecha_hasta = request.query_params.get("fecha_hasta", "").strip()

    supabase = get_supabase()

    # Main query (paginated, with count)
    query = (
        supabase.table("movimientos")
        .select("id, fecha, descripcion, monto, tipo, origen, categoria_id, categorias(nombre, emoji), tarjeta_id, es_pago_tarjeta, tarjetas(nombre)", count="exact")
        .eq("usuario_id", telegram_id)
        .neq("estado", "anulado")
        .order("fecha", desc=True)
        .order("id", desc=True)
    )
    # Totals query (lightweight, same filters, no pagination)
    tq = (
        supabase.table("movimientos")
        .select("monto, tipo")
        .eq("usuario_id", telegram_id)
        .neq("estado", "anulado")
    )

    if fecha_desde or fecha_hasta:
        if fecha_desde:
            if not _FECHA_RE.match(fecha_desde):
                return JSONResponse({"error": "Formato de fecha_desde inválido (YYYY-MM-DD)"}, status_code=400)
            query = query.gte("fecha", fecha_desde)
            tq = tq.gte("fecha", fecha_desde)
        if fecha_hasta:
            if not _FECHA_RE.match(fecha_hasta):
                return JSONResponse({"error": "Formato de fecha_hasta inválido (YYYY-MM-DD)"}, status_code=400)
            query = query.lte("fecha", fecha_hasta)
            tq = tq.lte("fecha", fecha_hasta)
    elif mes:
        if not validate_mes(mes):
            return JSONResponse({"error": "Formato de mes inválido (YYYY-MM)"}, status_code=400)
        start, end = mes_rango(mes)
        query = query.gte("fecha", start).lt("fecha", end)
        tq = tq.gte("fecha", start).lt("fecha", end)

    if q:
        query = query.ilike("descripcion", f"%{q}%")
        tq = tq.ilike("descripcion", f"%{q}%")

    if tipo in ("gasto", "ingreso"):
        query = query.eq("tipo", tipo)
        tq = tq.eq("tipo", tipo)

    if categoria_id:
        try:
            cid = int(categoria_id)
            query = query.eq("categoria_id", cid)
            tq = tq.eq("categoria_id", cid)
        except ValueError:
            pass

    if tarjeta_id:
        try:
            tid = int(tarjeta_id)
            query = query.eq("tarjeta_id", tid)
            tq = tq.eq("tarjeta_id", tid)
        except ValueError:
            pass

    if mes_resumen:
        if validate_mes(mes_resumen):
            query = query.eq("mes_resumen", mes_resumen)
            tq = tq.eq("mes_resumen", mes_resumen)

    if not todos:
        offset = (pagina - 1) * PAGE_SIZE
        query = query.range(offset, offset + PAGE_SIZE - 1)

    response = query.execute()
    total = response.count or 0

    if todos:
        # All data already fetched; compute totals from it directly
        all_rows = response.data or []
        total_monto_gasto = sum(r["monto"] for r in all_rows if r["tipo"] == "gasto")
        total_monto_ingreso = sum(r["monto"] for r in all_rows if r["tipo"] == "ingreso")
    else:
        t_resp = tq.execute()
        total_monto_gasto = sum(r["monto"] for r in (t_resp.data or []) if r["tipo"] == "gasto")
        total_monto_ingreso = sum(r["monto"] for r in (t_resp.data or []) if r["tipo"] == "ingreso")

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
        "total_monto_gasto": total_monto_gasto,
        "total_monto_ingreso": total_monto_ingreso,
    })


@app.patch("/api/movements")
async def patch_movement(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    id_ = request.query_params.get("id")
    if not id_:
        return JSONResponse({"error": "Falta id"}, status_code=400)

    body = await request.json()
    categoria_id = body.get("categoria_id")
    if categoria_id is None:
        return JSONResponse({"error": "Falta categoria_id"}, status_code=400)

    supabase = get_supabase()
    r = (
        supabase.table("movimientos")
        .update({"categoria_id": int(categoria_id)})
        .eq("id", int(id_))
        .eq("usuario_id", telegram_id)
        .execute()
    )
    if not r.data:
        return JSONResponse({"error": "Movimiento no encontrado"}, status_code=404)

    descripcion = r.data[0].get("descripcion", "")
    if descripcion:
        await _save_learned_keywords(descripcion, int(categoria_id), telegram_id)

    return JSONResponse({"ok": True, "data": r.data[0]})
