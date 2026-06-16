import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()

# Vercel strips "/api/inversiones" before passing to FastAPI, so routes use short paths.


@app.get("/ping")
@app.get("/api/inversiones/ping")
async def ping():
    """Diagnóstico sin auth: verifica que la función Python levantó correctamente."""
    supabase = get_supabase()
    try:
        r = supabase.table("activos").select("id", count="exact").execute()
        activos_count = r.count if hasattr(r, 'count') else len(r.data or [])
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
    return JSONResponse({"ok": True, "activos_en_db": activos_count})


@app.get("/perfil")
@app.get("/api/inversiones/perfil")
async def get_perfil(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    r = supabase.table("perfiles_inversion").select("*").eq("usuario_id", telegram_id).limit(1).execute()
    return JSONResponse(r.data[0] if r.data else {})


@app.post("/perfil")
@app.post("/api/inversiones/perfil")
async def upsert_perfil(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    body = await request.json()
    perfil = body.get("perfil", "moderado")
    if perfil not in ("conservador", "moderado", "arriesgado"):
        return JSONResponse({"error": "perfil inválido"}, status_code=400)

    data = {
        "usuario_id": telegram_id,
        "perfil": perfil,
        "objetivo": body.get("objetivo"),
        "capital_disponible": body.get("capital_disponible"),
        "notas": body.get("notas"),
        "actualizado_at": "now()",
    }

    supabase = get_supabase()
    supabase.table("perfiles_inversion").upsert(data, on_conflict="usuario_id").execute()
    return JSONResponse({"ok": True})


@app.get("/activos")
@app.get("/api/inversiones/activos")
async def get_activos(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    r = supabase.table("activos").select("*").eq("activo", True).order("tipo").execute()
    return JSONResponse(r.data or [])


@app.get("/recomendaciones")
@app.get("/api/inversiones/recomendaciones")
async def get_recomendaciones(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    estado = request.query_params.get("estado", "")
    limit = min(50, int(request.query_params.get("limit", "20")))

    supabase = get_supabase()
    query = (
        supabase.table("recomendaciones")
        .select("*, activos(codigo, nombre, tipo, moneda)")
        .eq("usuario_id", telegram_id)
        .order("generado_at", desc=True)
        .limit(limit)
    )
    if estado:
        query = query.eq("estado", estado)

    r = query.execute()
    return JSONResponse(r.data or [])


@app.get("/decisiones")
@app.get("/api/inversiones/decisiones")
async def get_decisiones(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    r = (
        supabase.table("decisiones_inversion")
        .select("*, recomendaciones(accion, activos(codigo, nombre))")
        .eq("usuario_id", telegram_id)
        .order("fecha_decision", desc=True)
        .limit(50)
        .execute()
    )

    decisiones = r.data or []
    aceptadas = [d for d in decisiones if d["accion"] == "aceptada"]
    exitosas = [d for d in aceptadas if d["resultado"] == "exitoso"]
    winrate = round(len(exitosas) / len(aceptadas) * 100, 1) if aceptadas else None

    return JSONResponse({
        "decisiones": decisiones,
        "stats": {
            "total": len(decisiones),
            "aceptadas": len(aceptadas),
            "exitosas": len(exitosas),
            "winrate": winrate,
        }
    })


@app.post("/decidir")
@app.post("/api/inversiones/decidir")
async def decidir(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    body = await request.json()
    rec_id = body.get("recomendacion_id")
    accion = body.get("accion")

    if not rec_id or accion not in ("aceptada", "rechazada"):
        return JSONResponse({"error": "Parámetros inválidos"}, status_code=400)

    supabase = get_supabase()

    rec_r = (
        supabase.table("recomendaciones")
        .select("id, estado, precio_recomendacion, activo_id")
        .eq("id", rec_id)
        .eq("usuario_id", telegram_id)
        .limit(1)
        .execute()
    )
    if not rec_r.data:
        return JSONResponse({"error": "Recomendación no encontrada"}, status_code=404)
    rec = rec_r.data[0]
    if rec["estado"] != "pendiente":
        return JSONResponse({"error": "Recomendación ya decidida"}, status_code=400)

    supabase.table("recomendaciones").update({
        "estado": accion,
        "decidido_at": "now()",
    }).eq("id", rec_id).execute()

    supabase.table("decisiones_inversion").insert({
        "usuario_id": telegram_id,
        "recomendacion_id": rec_id,
        "accion": accion,
        "monto": body.get("monto"),
        "precio_entrada": rec["precio_recomendacion"],
    }).execute()

    return JSONResponse({"ok": True})
