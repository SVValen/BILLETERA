import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()


@app.get("/api/prestamos")
async def prestamos_get(request: Request):
    resource = request.query_params.get("resource", "prestamos")
    supabase = get_supabase()

    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

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

    # ── cuota de préstamos que vence en un mes dado ────────────────────────────
    if resource == "prestamos_mes":
        from lib.date_utils import validate_mes
        mes = request.query_params.get("mes", "")
        if not validate_mes(mes):
            return JSONResponse({"error": "Formato de mes inválido (YYYY-MM)"}, status_code=400)

        prest_r = (
            supabase.table("prestamos")
            .select("id, nombre")
            .eq("usuario_id", telegram_id)
            .eq("activo", True)
            .execute()
        )
        result = []
        for p in (prest_r.data or []):
            cuota_r = (
                supabase.table("prestamo_cuotas")
                .select("monto_ordinario, capital, pagado")
                .eq("prestamo_id", p["id"])
                .eq("mes_previsto", mes)
                .limit(1)
                .execute()
            )
            if not cuota_r.data:
                continue
            c = cuota_r.data[0]
            monto = c.get("monto_ordinario") or c.get("capital") or 0
            result.append({
                "prestamo_id": p["id"], "nombre": p["nombre"],
                "monto": monto, "pagado": c["pagado"],
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
        {"error": "resource requerido: prestamos|prestamos_mes|prestamo_cuotas"},
        status_code=400,
    )


@app.post("/api/prestamos")
async def prestamos_post(request: Request):
    body = await request.json()
    resource = body.get("resource", "")

    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    supabase = get_supabase()

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
        for idx, f in enumerate(filas):
            try:
                numero_cuota = int(f["numero_cuota"])
            except (KeyError, ValueError, TypeError):
                supabase.table("prestamos").delete().eq("id", prestamo_id).execute()
                return JSONResponse({"error": f"Fila {idx}: 'numero_cuota' inválido ({f.get('numero_cuota')!r})"}, status_code=400)
            try:
                capital = float(str(f.get("capital", 0)).replace(",", ""))
            except (ValueError, TypeError):
                supabase.table("prestamos").delete().eq("id", prestamo_id).execute()
                return JSONResponse({"error": f"Fila {idx}: 'capital' inválido ({f.get('capital')!r})"}, status_code=400)
            pagado = f.get("pagado", False)
            if isinstance(pagado, str):
                pagado = pagado.lower() in ("true", "1", "si", "sí", "yes")
            monto_ord = f.get("monto_ordinario")
            try:
                monto_ord = float(str(monto_ord).replace(",", "")) if monto_ord else None
            except (ValueError, TypeError):
                monto_ord = None
            monto_pagado = f.get("monto_pagado")
            try:
                monto_pagado = float(str(monto_pagado).replace(",", "")) if monto_pagado else None
            except (ValueError, TypeError):
                monto_pagado = None
            rows.append({
                "prestamo_id": prestamo_id,
                "usuario_id": telegram_id,
                "numero_cuota": numero_cuota,
                "mes_previsto": str(f.get("mes", ""))[:7],
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

    return JSONResponse({"error": "resource requerido: importar_prestamo"}, status_code=400)
