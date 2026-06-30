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

    # ── métricas comparativas vs. mes anterior ──
    if request.query_params.get("resource") == "metricas":
        anio, m = (int(x) for x in mes.split("-"))
        anio_ant, m_ant = (anio - 1, 12) if m == 1 else (anio, m - 1)
        mes_ant = f"{anio_ant:04d}-{m_ant:02d}"

        def _fetch(mes_q: str):
            s, e = mes_rango(mes_q)
            r = (
                supabase.table("movimientos")
                .select("monto, tipo, tarjeta_id, es_pago_tarjeta, categorias(nombre, emoji)")
                .eq("usuario_id", telegram_id)
                .neq("estado", "anulado")
                .gte("fecha", s)
                .lt("fecha", e)
                .execute()
            )
            return r.data or []

        actual = _fetch(mes)
        anterior = _fetch(mes_ant)

        def _totales(rows):
            g = sum(r["monto"] for r in rows if r["tipo"] == "gasto")
            i = sum(r["monto"] for r in rows if r["tipo"] == "ingreso")
            return g, i

        g_act, i_act = _totales(actual)
        g_ant, i_ant = _totales(anterior)
        tasa_ahorro_actual = (i_act - g_act) / i_act * 100 if i_act > 0 else None
        tasa_ahorro_anterior = (i_ant - g_ant) / i_ant * 100 if i_ant > 0 else None

        def _medio_pago(rows):
            gastos = [r for r in rows if r["tipo"] == "gasto" and not r.get("es_pago_tarjeta")]
            total = sum(r["monto"] for r in gastos)
            if total == 0:
                return None
            tarjeta = sum(r["monto"] for r in gastos if r.get("tarjeta_id"))
            efectivo = total - tarjeta
            return {"efectivo_pct": round(efectivo / total * 100), "tarjeta_pct": round(tarjeta / total * 100)}

        def _por_categoria(rows):
            cats: dict[str, dict] = {}
            for r in rows:
                if r["tipo"] != "gasto" or r.get("es_pago_tarjeta"):
                    continue
                cat = r.get("categorias") or {}
                nombre = cat.get("nombre", "Otros")
                emoji = cat.get("emoji", "📌")
                if nombre not in cats:
                    cats[nombre] = {"nombre": nombre, "emoji": emoji, "monto": 0.0}
                cats[nombre]["monto"] += r["monto"]
            return cats

        cats_act = _por_categoria(actual)
        cats_ant = _por_categoria(anterior)
        cambios = []
        for nombre, c in cats_act.items():
            ant = cats_ant.get(nombre)
            if ant and ant["monto"] > 0:
                pct = (c["monto"] - ant["monto"]) / ant["monto"] * 100
                cambios.append({"nombre": nombre, "emoji": c["emoji"], "monto": c["monto"], "monto_anterior": ant["monto"], "pct_cambio": round(pct)})
        cambios.sort(key=lambda x: -abs(x["pct_cambio"]))

        return JSONResponse({
            "mes": mes,
            "mes_anterior": mes_ant,
            "tasa_ahorro": {"actual": tasa_ahorro_actual, "anterior": tasa_ahorro_anterior},
            "medio_pago": {"actual": _medio_pago(actual), "anterior": _medio_pago(anterior)},
            "categorias_cambio": cambios[:4],
        })

    start, end = mes_rango(mes)

    response = (
        supabase.table("movimientos")
        .select("monto, tipo, tarjeta_id, es_pago_tarjeta, categorias(nombre, emoji)")
        .eq("usuario_id", telegram_id)
        .neq("estado", "anulado")
        .gte("fecha", start)
        .lt("fecha", end)
        .execute()
    )

    rows = response.data or []
    ingresos = [r for r in rows if r["tipo"] == "ingreso"]
    # Consumo: lo que se gastó por categoría, sin contar el pago de resumen
    # (que ya representa, en otro mes, compras que acá se cuentan una sola vez).
    consumo = [r for r in rows if r["tipo"] == "gasto" and not r.get("es_pago_tarjeta")]
    # Flujo de caja: lo que efectivamente salió del banco — efectivo + pagos de
    # resumen de tarjeta, excluyendo las compras con tarjeta todavía no pagadas.
    flujo_caja = [
        r for r in rows
        if r["tipo"] == "gasto" and (r.get("es_pago_tarjeta") or not r.get("tarjeta_id"))
    ]

    total_gastos = sum(r["monto"] for r in consumo)
    total_pagado = sum(r["monto"] for r in flujo_caja)
    total_ingresos = sum(r["monto"] for r in ingresos)

    por_categoria: dict[str, dict] = {}
    for r in consumo:
        cat = r.get("categorias") or {}
        nombre = cat.get("nombre", "Otros")
        emoji = cat.get("emoji", "📌")
        if nombre not in por_categoria:
            por_categoria[nombre] = {"monto": 0, "emoji": emoji}
        por_categoria[nombre]["monto"] += r["monto"]

    return JSONResponse({
        "mes": mes,
        "total_gastos": total_gastos,
        "total_pagado": total_pagado,
        "total_ingresos": total_ingresos,
        "saldo": total_ingresos - total_pagado,
        "por_categoria": por_categoria,
    })
