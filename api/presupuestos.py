import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request
from lib.date_utils import mes_rango, validate_mes

app = FastAPI()


@app.get("/api/presupuestos")
async def get_presupuestos(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    if request.query_params.get("resource") == "categorias":
        supabase = get_supabase()
        r = supabase.table("categorias").select("id, nombre, emoji").order("nombre").execute()
        return JSONResponse(r.data or [])

    mes = request.query_params.get("mes", "")
    if not mes:
        return JSONResponse({"error": "Falta parámetro 'mes'"}, status_code=400)
    if not validate_mes(mes):
        return JSONResponse({"error": "Formato de mes inválido (YYYY-MM)"}, status_code=400)

    supabase = get_supabase()
    start, end = mes_rango(mes)

    pres_rows = (
        supabase.table("presupuestos")
        .select("id, categoria_id, monto, categorias(nombre, emoji)")
        .eq("usuario_id", telegram_id)
        .eq("mes", mes)
        .execute()
    )

    mov_rows = (
        supabase.table("movimientos")
        .select("categoria_id, monto")
        .eq("usuario_id", telegram_id)
        .eq("tipo", "gasto")
        .neq("estado", "anulado")
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
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    body = await request.json()

    if body.get("resource") == "categorias":
        nombre = (body.get("nombre") or "").strip()
        emoji = (body.get("emoji") or "📌").strip()
        if not nombre:
            return JSONResponse({"error": "Falta nombre"}, status_code=400)
        supabase = get_supabase()
        r = supabase.table("categorias").insert({"nombre": nombre, "emoji": emoji}).execute()
        return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})

    categoria_id = body.get("categoria_id")
    monto = body.get("monto")
    mes = body.get("mes", "")

    if not all([categoria_id, monto is not None, mes]):
        return JSONResponse({"error": "Faltan campos"}, status_code=400)

    if not isinstance(monto, (int, float)) or monto <= 0:
        return JSONResponse({"error": "El monto debe ser un número positivo"}, status_code=400)

    supabase = get_supabase()
    existing = (
        supabase.table("presupuestos")
        .select("id")
        .eq("usuario_id", telegram_id)
        .eq("categoria_id", categoria_id)
        .eq("mes", mes)
        .execute()
    )

    if existing.data:
        r = supabase.table("presupuestos").update({"monto": monto}).eq("id", existing.data[0]["id"]).execute()
    else:
        r = supabase.table("presupuestos").insert({
            "usuario_id": telegram_id,
            "categoria_id": categoria_id,
            "monto": monto,
            "mes": mes,
        }).execute()

    return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})


@app.put("/api/presupuestos")
async def update_presupuesto(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    id_ = request.query_params.get("id")
    body = await request.json()

    if body.get("resource") == "categorias":
        if not id_:
            return JSONResponse({"error": "Falta id"}, status_code=400)
        updates = {}
        if body.get("nombre"):
            updates["nombre"] = body["nombre"].strip()
        if body.get("emoji"):
            updates["emoji"] = body["emoji"].strip()
        if not updates:
            return JSONResponse({"error": "Nada para actualizar"}, status_code=400)
        supabase = get_supabase()
        r = supabase.table("categorias").update(updates).eq("id", int(id_)).execute()
        return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})

    monto = body.get("monto")

    if not id_ or monto is None:
        return JSONResponse({"error": "Faltan parámetros"}, status_code=400)

    if not isinstance(monto, (int, float)) or monto <= 0:
        return JSONResponse({"error": "El monto debe ser un número positivo"}, status_code=400)

    supabase = get_supabase()
    r = (
        supabase.table("presupuestos")
        .update({"monto": monto})
        .eq("id", int(id_))
        .eq("usuario_id", telegram_id)
        .execute()
    )
    return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})


@app.delete("/api/presupuestos")
async def delete_presupuesto(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    id_ = request.query_params.get("id")
    if not id_:
        return JSONResponse({"error": "Falta id"}, status_code=400)

    supabase = get_supabase()
    supabase.table("presupuestos").delete().eq("id", int(id_)).eq("usuario_id", telegram_id).execute()
    return JSONResponse({"ok": True})
