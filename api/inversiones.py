import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()

# Vercel rutea /api/inversiones → este archivo.
# Sub-paths como /api/inversiones/perfil NO son ruteados — se usa ?resource=


@app.get("/api/inversiones")
async def inversiones_get(request: Request):
    resource = request.query_params.get("resource", "")
    supabase = get_supabase()

    # ping: sin auth, diagnóstico de disponibilidad
    if resource == "ping":
        try:
            r = supabase.table("activos").select("id").limit(1).execute()
            return JSONResponse({"ok": True, "activos_en_db": len(r.data or [])})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    if resource == "perfil":
        r = supabase.table("perfiles_inversion").select("*").eq("usuario_id", telegram_id).limit(1).execute()
        return JSONResponse(r.data[0] if r.data else {})

    if resource == "activos":
        r = supabase.table("activos").select("*").eq("activo", True).order("tipo").execute()
        return JSONResponse(r.data or [])

    if resource == "recomendaciones":
        estado = request.query_params.get("estado", "")
        limit = min(50, int(request.query_params.get("limit", "20")))
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

    if resource == "decisiones":
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

    if resource == "liquidez":
        from lib.market_data import fetch_dolar_precio
        from lib.rf_analysis import analizar_carry_trade, calcular_rendimiento_usd, calcular_allocation

        pos_r = (
            supabase.table("posiciones_rf")
            .select("*, instrumentos_rf(nombre, tipo, tna_actual, codigo)")
            .eq("usuario_id", telegram_id)
            .eq("estado", "activa")
            .execute()
        )
        posiciones = pos_r.data or []

        perfil_r = supabase.table("perfiles_inversion").select("capital_usd, asignacion_rf_pct").eq("usuario_id", telegram_id).limit(1).execute()
        perfil = perfil_r.data[0] if perfil_r.data else {}

        dolar_data = await fetch_dolar_precio("bolsa")
        dolar_mep = dolar_data["precio"] if dolar_data else None

        carry = None
        if dolar_mep:
            caucion_r = supabase.table("instrumentos_rf").select("tna_actual").eq("codigo", "CAUCION_7D").limit(1).execute()
            tna_ref = caucion_r.data[0]["tna_actual"] if caucion_r.data and caucion_r.data[0].get("tna_actual") else None
            if tna_ref:
                carry = analizar_carry_trade(tna_ref, dolar_mep, None)

        posiciones_con_rdto = []
        for p in posiciones:
            rdto = calcular_rendimiento_usd(p, dolar_mep) if dolar_mep else {}
            posiciones_con_rdto.append({**p, "rendimiento": rdto})

        allocation = calcular_allocation(posiciones, perfil.get("capital_usd") or 0, dolar_mep or 1) if dolar_mep else {}

        return JSONResponse({
            "posiciones": posiciones_con_rdto,
            "carry": carry,
            "allocation": allocation,
            "dolar_mep": dolar_mep,
            "capital_usd": perfil.get("capital_usd"),
            "asignacion_rf_pct": perfil.get("asignacion_rf_pct", 30),
        })

    if resource == "allocation":
        from lib.market_data import fetch_dolar_precio
        from lib.rf_analysis import calcular_allocation

        dolar_data = await fetch_dolar_precio("bolsa")
        dolar_mep = dolar_data["precio"] if dolar_data else 1

        pos_rf_r = supabase.table("posiciones_rf").select("monto_ars, estado").eq("usuario_id", telegram_id).execute()
        pos_rf = [p for p in (pos_rf_r.data or []) if p.get("estado") == "activa"]

        ua_r = supabase.table("usuario_activos").select("monto_ars").eq("usuario_id", telegram_id).execute()
        total_ars_rv = sum(u.get("monto_ars") or 0 for u in (ua_r.data or []))
        total_usd_rv = total_ars_rv / dolar_mep if dolar_mep else 0

        perfil_r = supabase.table("perfiles_inversion").select("capital_usd, asignacion_rf_pct").eq("usuario_id", telegram_id).limit(1).execute()
        perfil = perfil_r.data[0] if perfil_r.data else {}
        capital_usd = perfil.get("capital_usd") or 0

        alloc_rf = calcular_allocation(pos_rf, capital_usd, dolar_mep)

        return JSONResponse({
            "capital_usd": capital_usd,
            "dolar_mep": dolar_mep,
            "renta_fija": alloc_rf,
            "renta_variable_usd": round(total_usd_rv, 2),
            "pct_rv": round(total_usd_rv / capital_usd * 100, 1) if capital_usd else 0,
            "asignacion_rf_objetivo": perfil.get("asignacion_rf_pct", 30),
        })

    if resource == "instrumentos_rf":
        r = supabase.table("instrumentos_rf").select("*").eq("activo", True).order("tipo").execute()
        return JSONResponse(r.data or [])

    return JSONResponse({"error": "resource requerido: perfil|activos|recomendaciones|decisiones|liquidez|allocation|instrumentos_rf|ping"}, status_code=400)


@app.post("/api/inversiones")
async def inversiones_post(request: Request):
    body = await request.json()
    resource = body.get("resource", "")

    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()

    if resource == "perfil":
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
        supabase.table("perfiles_inversion").upsert(data, on_conflict="usuario_id").execute()
        return JSONResponse({"ok": True})

    if resource == "decidir":
        rec_id = body.get("recomendacion_id")
        accion = body.get("accion")
        if not rec_id or accion not in ("aceptada", "rechazada"):
            return JSONResponse({"error": "Parámetros inválidos"}, status_code=400)

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

    return JSONResponse({"error": "resource requerido: perfil|decidir"}, status_code=400)
