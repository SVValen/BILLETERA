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

_CUOTA_RE = re.compile(r"\(cuota \d+/\d+\)")


@app.get("/api/stats")
async def get_stats(request: Request):
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    mes = request.query_params.get("mes", "")
    if not mes:
        return JSONResponse({"error": "Falta parámetro 'mes'"}, status_code=400)
    if not validate_mes(mes):
        return JSONResponse({"error": "Formato de mes inválido (YYYY-MM)"}, status_code=400)

    supabase = get_supabase()

    # ── resumen por tarjeta del mes de resumen (lo que corresponde pagar) ──
    if request.query_params.get("resource") == "tarjetas":
        rows = (
            supabase.table("movimientos")
            .select("monto, descripcion, tarjeta_id, tarjetas(nombre)")
            .eq("usuario_id", telegram_id)
            .eq("mes_resumen", mes)
            .eq("tipo", "gasto")
            .eq("es_pago_tarjeta", False)
            .neq("estado", "anulado")
            .not_.is_("tarjeta_id", "null")
            .execute()
        )
        por_tarjeta: dict[int, dict] = {}
        for r in (rows.data or []):
            tid = r["tarjeta_id"]
            if tid not in por_tarjeta:
                nombre = (r.get("tarjetas") or {}).get("nombre", "Tarjeta")
                por_tarjeta[tid] = {"tarjeta_id": tid, "nombre": nombre, "cuotas": 0.0, "un_pago": 0.0}
            if _CUOTA_RE.search(r.get("descripcion") or ""):
                por_tarjeta[tid]["cuotas"] += float(r["monto"])
            else:
                por_tarjeta[tid]["un_pago"] += float(r["monto"])

        pagos_r = (
            supabase.table("tarjeta_pagos")
            .select("tarjeta_id, monto_pagado, fecha_pago")
            .eq("usuario_id", telegram_id)
            .eq("mes_resumen", mes)
            .not_.is_("monto_pagado", "null")
            .execute()
        )
        pagados = {p["tarjeta_id"]: p for p in (pagos_r.data or [])}

        result = []
        for t in por_tarjeta.values():
            pago = pagados.get(t["tarjeta_id"])
            result.append({
                **t,
                "total": t["cuotas"] + t["un_pago"],
                "pagado": pago is not None,
                "monto_pagado": pago["monto_pagado"] if pago else None,
                "fecha_pago": pago["fecha_pago"] if pago else None,
            })
        result.sort(key=lambda x: -x["total"])
        return JSONResponse({"mes": mes, "tarjetas": result})

    start, end = mes_rango(mes)

    response = (
        supabase.table("movimientos")
        .select("monto, tipo, categorias(nombre, emoji)")
        .eq("usuario_id", telegram_id)
        .neq("estado", "anulado")
        .gte("fecha", start)
        .lt("fecha", end)
        .execute()
    )

    rows = response.data or []
    gastos = [r for r in rows if r["tipo"] == "gasto"]
    ingresos = [r for r in rows if r["tipo"] == "ingreso"]

    total_gastos = sum(r["monto"] for r in gastos)
    total_ingresos = sum(r["monto"] for r in ingresos)

    por_categoria: dict[str, dict] = {}
    for r in gastos:
        cat = r.get("categorias") or {}
        nombre = cat.get("nombre", "Otros")
        emoji = cat.get("emoji", "📌")
        if nombre not in por_categoria:
            por_categoria[nombre] = {"monto": 0, "emoji": emoji}
        por_categoria[nombre]["monto"] += r["monto"]

    return JSONResponse({
        "mes": mes,
        "total_gastos": total_gastos,
        "total_ingresos": total_ingresos,
        "saldo": total_ingresos - total_gastos,
        "por_categoria": por_categoria,
    })
