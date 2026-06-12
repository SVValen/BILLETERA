import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase

app = FastAPI()


def _mes_rango(mes: str) -> tuple[str, str]:
    year, month = int(mes[:4]), int(mes[5:7])
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    return start, end


@app.get("/api/presupuestos")
async def get_presupuestos(request: Request):
    usuario = request.query_params.get("usuario", "")
    mes = request.query_params.get("mes", "")
    if not usuario or not mes:
        return JSONResponse({"error": "Faltan parámetros"}, status_code=400)

    supabase = get_supabase()
    start, end = _mes_rango(mes)

    pres_rows = (
        supabase.table("presupuestos")
        .select("id, categoria_id, monto, categorias(nombre, emoji)")
        .eq("usuario_id", usuario)
        .eq("mes", mes)
        .execute()
    )

    mov_rows = (
        supabase.table("movimientos")
        .select("categoria_id, monto")
        .eq("usuario_id", usuario)
        .eq("tipo", "gasto")
        .gte("fecha", start)
        .lt("fecha", end)
        .execute()
    )

    gastos_por_cat: dict[int, float] = {}
    for r in (mov_rows.data or []):
        cid = r["categoria_id"]
        gastos_por_cat[cid] = gastos_por_cat.get(cid, 0) + r["monto"]

    result = []
    for p in (pres_rows.data or []):
        cid = p["categoria_id"]
        cat = p.get("categorias") or {}
        presupuestado = p["monto"]
        gastado = gastos_por_cat.get(cid, 0)
        result.append({
            "id": p["id"],
            "categoria_id": cid,
            "categoria": cat.get("nombre", "?"),
            "emoji": cat.get("emoji", "📌"),
            "presupuestado": presupuestado,
            "gastado": gastado,
            "disponible": presupuestado - gastado,
            "porcentaje": round(gastado / presupuestado * 100, 1) if presupuestado else 0,
        })

    result.sort(key=lambda x: x["porcentaje"], reverse=True)
    return JSONResponse(result)


@app.post("/api/presupuestos")
async def upsert_presupuesto(request: Request):
    body = await request.json()
    usuario = body.get("usuario", "")
    categoria_id = body.get("categoria_id")
    monto = body.get("monto")
    mes = body.get("mes", "")
    if not all([usuario, categoria_id, monto, mes]):
        return JSONResponse({"error": "Faltan campos"}, status_code=400)

    supabase = get_supabase()
    existing = (
        supabase.table("presupuestos")
        .select("id")
        .eq("usuario_id", usuario)
        .eq("categoria_id", categoria_id)
        .eq("mes", mes)
        .execute()
    )

    if existing.data:
        r = supabase.table("presupuestos").update({"monto": monto}).eq("id", existing.data[0]["id"]).execute()
    else:
        r = supabase.table("presupuestos").insert({
            "usuario_id": usuario,
            "categoria_id": categoria_id,
            "monto": monto,
            "mes": mes,
        }).execute()

    return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})


@app.put("/api/presupuestos")
async def update_presupuesto(request: Request):
    id_ = request.query_params.get("id")
    body = await request.json()
    monto = body.get("monto")
    if not id_ or monto is None:
        return JSONResponse({"error": "Faltan parámetros"}, status_code=400)

    supabase = get_supabase()
    r = supabase.table("presupuestos").update({"monto": monto}).eq("id", int(id_)).execute()
    return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})


@app.delete("/api/presupuestos")
async def delete_presupuesto(request: Request):
    id_ = request.query_params.get("id")
    if not id_:
        return JSONResponse({"error": "Falta id"}, status_code=400)

    supabase = get_supabase()
    supabase.table("presupuestos").delete().eq("id", int(id_)).execute()
    return JSONResponse({"ok": True})
