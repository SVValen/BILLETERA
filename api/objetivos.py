import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()


@app.get("/api/objetivos")
async def get_objetivos(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    rows = (
        supabase.table("objetivos_ahorro")
        .select("*")
        .eq("usuario_id", telegram_id)
        .eq("activo", True)
        .order("fecha_objetivo")
        .execute()
    )

    hoy = date.today()
    result = []
    for obj in (rows.data or []):
        fecha = date.fromisoformat(obj["fecha_objetivo"])
        dias = (fecha - hoy).days
        meses = max(1, dias // 30)
        falta = max(0, obj["monto_objetivo"] - obj["monto_actual"])
        pct = min(100, round(obj["monto_actual"] / obj["monto_objetivo"] * 100, 1)) if obj["monto_objetivo"] else 0
        result.append({
            "id": obj["id"],
            "nombre": obj["nombre"],
            "monto_objetivo": obj["monto_objetivo"],
            "monto_actual": obj["monto_actual"],
            "falta": falta,
            "porcentaje": pct,
            "fecha_objetivo": obj["fecha_objetivo"],
            "dias_faltan": dias,
            "meses_faltan": meses,
            "recomendado_mensual": round(falta / meses, 0) if dias > 0 else 0,
        })

    return JSONResponse(result)


@app.post("/api/objetivos")
async def create_objetivo(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    body = await request.json()
    nombre = body.get("nombre", "").strip()
    monto_objetivo = body.get("monto_objetivo")
    fecha_objetivo = body.get("fecha_objetivo", "")

    if not all([nombre, monto_objetivo, fecha_objetivo]):
        return JSONResponse({"error": "Faltan campos"}, status_code=400)

    if not isinstance(monto_objetivo, (int, float)) or monto_objetivo <= 0:
        return JSONResponse({"error": "El monto debe ser un número positivo"}, status_code=400)

    supabase = get_supabase()
    r = supabase.table("objetivos_ahorro").insert({
        "usuario_id": telegram_id,
        "nombre": nombre,
        "monto_objetivo": monto_objetivo,
        "fecha_objetivo": fecha_objetivo,
        "monto_actual": 0,
    }).execute()
    return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})


@app.put("/api/objetivos")
async def update_objetivo(request: Request):
    """Abonar o actualizar objetivo. ?id=X con body {aporte: N} o {monto_objetivo: N}."""
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    id_ = request.query_params.get("id")
    if not id_:
        return JSONResponse({"error": "Falta id"}, status_code=400)

    body = await request.json()
    supabase = get_supabase()

    if "aporte" in body:
        # RPC atómica: evita race condition del read-modify-write
        r = supabase.rpc("incrementar_objetivo", {
            "obj_id": int(id_),
            "p_usuario": telegram_id,
            "incremento": float(body["aporte"]),
        }).execute()
        if not r.data:
            return JSONResponse({"error": "No encontrado"}, status_code=404)
    else:
        update_data = {k: v for k, v in body.items() if k in ("nombre", "monto_objetivo", "fecha_objetivo")}
        r = supabase.table("objetivos_ahorro").update(update_data).eq("id", int(id_)).eq("usuario_id", telegram_id).execute()

    return JSONResponse({"ok": True, "data": r.data[0] if r.data else None})


@app.delete("/api/objetivos")
async def delete_objetivo(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    id_ = request.query_params.get("id")
    if not id_:
        return JSONResponse({"error": "Falta id"}, status_code=400)

    supabase = get_supabase()
    supabase.table("objetivos_ahorro").update({"activo": False}).eq("id", int(id_)).eq("usuario_id", telegram_id).execute()
    return JSONResponse({"ok": True})
