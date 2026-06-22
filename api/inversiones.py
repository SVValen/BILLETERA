import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()


@app.get("/api/inversiones")
async def inversiones_get(request: Request):
    resource = request.query_params.get("resource", "")
    supabase = get_supabase()

    if resource == "ping":
        try:
            r = supabase.table("activos").select("id").limit(1).execute()
            return JSONResponse({"ok": True, "activos_en_db": len(r.data or [])})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    # ── portafolios ──────────────────────────────────────────────────────────
    if resource == "portafolios":
        r = (
            supabase.table("portafolios")
            .select("*")
            .eq("usuario_id", telegram_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .order("id")
            .execute()
        )
        return JSONResponse(r.data or [])

    # ── perfil (compat dashboard — devuelve el portafolio de mayor capital) ──
    if resource == "perfil":
        r = (
            supabase.table("portafolios")
            .select("*")
            .eq("usuario_id", telegram_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .order("capital_usd", desc=True)
            .limit(1)
            .execute()
        )
        return JSONResponse(r.data[0] if r.data else {})

    # ── activos (catálogo global) ─────────────────────────────────────────────
    if resource == "activos":
        r = supabase.table("activos").select("*").eq("activo", True).order("tipo").execute()
        return JSONResponse(r.data or [])

    # ── recomendaciones ───────────────────────────────────────────────────────
    if resource == "recomendaciones":
        estado = request.query_params.get("estado", "")
        limit = min(50, int(request.query_params.get("limit", "20")))
        query = (
            supabase.table("recomendaciones")
            .select("*, activos(codigo, nombre, tipo, moneda), portafolios(nombre_personalizado, nombre_sugerido, tipo)")
            .eq("usuario_id", telegram_id)
            .order("generado_at", desc=True)
            .limit(limit)
        )
        if estado:
            query = query.eq("estado", estado)
        r = query.execute()
        return JSONResponse(r.data or [])

    # ── decisiones ────────────────────────────────────────────────────────────
    if resource == "decisiones":
        r = (
            supabase.table("decisiones_inversion")
            .select("*, recomendaciones(accion, activos(codigo, nombre))")
            .eq("usuario_id", telegram_id)
            .order("creado_at", desc=True)
            .limit(50)
            .execute()
        )
        decisiones = r.data or []
        aceptadas = [d for d in decisiones if d["accion"] == "aceptada"]
        exitosas = [d for d in aceptadas if d.get("resultado") == "exitoso"]
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

    # ── liquidez (RF) ─────────────────────────────────────────────────────────
    if resource == "liquidez":
        from lib.market_data import fetch_dolar_precio
        from lib.rf_analysis import analizar_carry_trade, calcular_rendimiento_usd, calcular_allocation

        portafolio_id = request.query_params.get("portafolio_id")
        pos_q = (
            supabase.table("posiciones_rf")
            .select("*, instrumentos_rf(nombre, tipo, tna_actual, codigo)")
            .eq("usuario_id", telegram_id)
            .eq("estado", "abierta")
        )
        if portafolio_id:
            pos_q = pos_q.eq("portafolio_id", portafolio_id)
        posiciones = (pos_q.execute()).data or []

        # Portafolio de referencia para capital y asignación
        port_r = (
            supabase.table("portafolios")
            .select("capital_usd, asignacion_rf_pct")
            .eq("usuario_id", telegram_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .order("capital_usd", desc=True)
            .limit(1)
            .execute()
        )
        port = port_r.data[0] if port_r.data else {}

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

        allocation = calcular_allocation(posiciones, port.get("capital_usd") or 0, dolar_mep or 1) if dolar_mep else {}

        return JSONResponse({
            "posiciones": posiciones_con_rdto,
            "carry": carry,
            "allocation": allocation,
            "dolar_mep": dolar_mep,
            "capital_usd": port.get("capital_usd"),
            "asignacion_rf_pct": port.get("asignacion_rf_pct", 30),
        })

    # ── allocation ────────────────────────────────────────────────────────────
    if resource == "allocation":
        from lib.market_data import fetch_dolar_precio
        from lib.rf_analysis import calcular_allocation

        dolar_data = await fetch_dolar_precio("bolsa")
        dolar_mep = dolar_data["precio"] if dolar_data else 1

        pos_rf_r = (
            supabase.table("posiciones_rf")
            .select("monto_ars, estado, monto_usd_entrada")
            .eq("usuario_id", telegram_id)
            .eq("estado", "abierta")
            .execute()
        )
        posiciones_rf = pos_rf_r.data or []

        pa_r = (
            supabase.table("portafolio_activos")
            .select("monto_usd")
            .eq("usuario_id", telegram_id)
            .execute()
        )
        total_usd_rv = sum(float(u.get("monto_usd") or 0) for u in (pa_r.data or []))

        port_r = (
            supabase.table("portafolios")
            .select("capital_usd, asignacion_rf_pct")
            .eq("usuario_id", telegram_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .order("capital_usd", desc=True)
            .limit(1)
            .execute()
        )
        port = port_r.data[0] if port_r.data else {}
        capital_usd = port.get("capital_usd") or 0

        alloc_rf = calcular_allocation(posiciones_rf, capital_usd, dolar_mep)

        return JSONResponse({
            "capital_usd": capital_usd,
            "dolar_mep": dolar_mep,
            "renta_fija": alloc_rf,
            "renta_variable_usd": round(total_usd_rv, 2),
            "pct_rv": round(total_usd_rv / capital_usd * 100, 1) if capital_usd else 0,
            "asignacion_rf_objetivo": port.get("asignacion_rf_pct", 30),
        })

    # ── instrumentos_rf ───────────────────────────────────────────────────────
    if resource == "instrumentos_rf":
        r = supabase.table("instrumentos_rf").select("*").eq("activo", True).order("tipo").execute()
        return JSONResponse(r.data or [])

    # ── prestamos ─────────────────────────────────────────────────────────────
    if resource == "prestamos":
        prest_r = (
            supabase.table("prestamos")
            .select("*")
            .eq("usuario_id", telegram_id)
            .eq("activo", True)
            .order("id")
            .execute()
        )
        prestamos = prest_r.data or []
        result = []
        for p in prestamos:
            cuotas_r = supabase.table("prestamo_cuotas").select("id, pagado").eq("prestamo_id", p["id"]).execute()
            cuotas = cuotas_r.data or []
            total = len(cuotas)
            pagadas = sum(1 for c in cuotas if c["pagado"])
            prox_r = (
                supabase.table("prestamo_cuotas")
                .select("numero_cuota, mes_previsto, monto_ordinario, capital")
                .eq("prestamo_id", p["id"])
                .eq("pagado", False)
                .order("numero_cuota")
                .limit(1)
                .execute()
            )
            result.append({
                **p,
                "total_cuotas_real": total,
                "cuotas_pagadas": pagadas,
                "cuotas_pendientes": total - pagadas,
                "proxima": prox_r.data[0] if prox_r.data else None,
            })
        return JSONResponse(result)

    # ── prestamo_cuotas ───────────────────────────────────────────────────────
    if resource == "prestamo_cuotas":
        prestamo_id = request.query_params.get("prestamo_id")
        if not prestamo_id:
            return JSONResponse({"error": "prestamo_id requerido"}, status_code=400)
        prest_r = (
            supabase.table("prestamos")
            .select("id")
            .eq("id", prestamo_id)
            .eq("usuario_id", telegram_id)
            .limit(1)
            .execute()
        )
        if not prest_r.data:
            return JSONResponse({"error": "Préstamo no encontrado"}, status_code=404)
        cuotas_r = (
            supabase.table("prestamo_cuotas")
            .select("*")
            .eq("prestamo_id", prestamo_id)
            .order("numero_cuota")
            .execute()
        )
        return JSONResponse(cuotas_r.data or [])

    return JSONResponse(
        {"error": "resource requerido: portafolios|perfil|activos|recomendaciones|decisiones|liquidez|allocation|instrumentos_rf|prestamos|prestamo_cuotas|ping"},
        status_code=400,
    )


@app.post("/api/inversiones")
async def inversiones_post(request: Request):
    body = await request.json()
    resource = body.get("resource", "")

    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()

    if resource == "decidir":
        rec_id = body.get("recomendacion_id")
        accion = body.get("accion")
        if not rec_id or accion not in ("aceptada", "rechazada"):
            return JSONResponse({"error": "Parámetros inválidos"}, status_code=400)

        rec_r = (
            supabase.table("recomendaciones")
            .select("id, estado, portafolio_id, activo_id")
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
            "portafolio_id": rec["portafolio_id"],
            "recomendacion_id": rec_id,
            "accion": accion,
        }).execute()

        return JSONResponse({"ok": True})

    # ── importar_prestamo ─────────────────────────────────────────────────────
    if resource == "importar_prestamo":
        nombre = body.get("nombre", "Préstamo")
        filas = body.get("cuotas", [])
        if not filas:
            return JSONResponse({"error": "No se enviaron cuotas"}, status_code=400)

        prest_r = supabase.table("prestamos").insert({
            "usuario_id": telegram_id,
            "nombre": nombre,
            "total_cuotas": len(filas),
        }).execute()
        if not prest_r.data:
            return JSONResponse({"error": "Error creando préstamo"}, status_code=500)
        prestamo_id = prest_r.data[0]["id"]

        rows = []
        for f in filas:
            pagado = f.get("pagado", False)
            if isinstance(pagado, str):
                pagado = pagado.lower() in ("true", "1", "si", "sí", "yes")
            capital = float(str(f.get("capital", 0)).replace(",", ""))
            monto_ord = f.get("monto_ordinario")
            monto_ord = float(str(monto_ord).replace(",", "")) if monto_ord else None
            monto_pagado = f.get("monto_pagado")
            monto_pagado = float(str(monto_pagado).replace(",", "")) if monto_pagado else None
            rows.append({
                "prestamo_id": prestamo_id,
                "usuario_id": telegram_id,
                "numero_cuota": int(f["numero_cuota"]),
                "mes_previsto": str(f["mes"])[:7],
                "capital": capital,
                "monto_ordinario": monto_ord,
                "monto_adelanto": round(capital * 1.25, 2),
                "pagado": pagado,
                "tipo_pago": f.get("tipo_pago") or None,
                "monto_pagado": monto_pagado,
                "fecha_pago": f.get("fecha_pago") or None,
            })
        supabase.table("prestamo_cuotas").insert(rows).execute()
        return JSONResponse({"ok": True, "prestamo_id": prestamo_id, "cuotas": len(rows)})

    return JSONResponse({"error": "resource requerido: decidir|importar_prestamo"}, status_code=400)
