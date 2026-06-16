import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()


# ============================================================
# Perfil de inversión
# ============================================================

@app.get("/api/inversiones/perfil")
async def get_perfil(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    r = supabase.table("perfiles_inversion").select("*").eq("usuario_id", telegram_id).maybe_single().execute()
    return JSONResponse(r.data or {})


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


# ============================================================
# Activos disponibles
# ============================================================

@app.get("/api/inversiones/activos")
async def get_activos(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()
    r = supabase.table("activos").select("*").eq("activo", True).order("tipo").execute()
    return JSONResponse(r.data or [])


# ============================================================
# Recomendaciones
# ============================================================

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


# ============================================================
# Decisiones (historial + winrate)
# ============================================================

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

    # Calcular winrate
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


# ============================================================
# Registrar decisión manual (desde dashboard)
# ============================================================

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

    # Verificar que la recomendación pertenece al usuario
    rec = (
        supabase.table("recomendaciones")
        .select("id, estado, precio_recomendacion, activo_id")
        .eq("id", rec_id)
        .eq("usuario_id", telegram_id)
        .maybe_single()
        .execute()
    )
    if not rec.data:
        return JSONResponse({"error": "Recomendación no encontrada"}, status_code=404)
    if rec.data["estado"] != "pendiente":
        return JSONResponse({"error": "Recomendación ya decidida"}, status_code=400)

    # Actualizar estado de la recomendación
    supabase.table("recomendaciones").update({
        "estado": accion,
        "decidido_at": "now()",
    }).eq("id", rec_id).execute()

    # Registrar decisión
    decision_data = {
        "usuario_id": telegram_id,
        "recomendacion_id": rec_id,
        "accion": accion,
        "monto": body.get("monto"),
        "precio_entrada": rec.data["precio_recomendacion"],
    }
    supabase.table("decisiones_inversion").insert(decision_data).execute()

    return JSONResponse({"ok": True})
