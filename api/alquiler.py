import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.auth import get_telegram_id_from_request
from lib.date_utils import validate_mes
from lib import alquiler as alq

app = FastAPI()


@app.get("/api/alquiler")
async def alquiler_get(request: Request):
    """GET ?mes=YYYY-MM → conceptos del mes (alquiler, expensas, agua, gas, luz, descuentos),
    total, pendiente y canon vigente."""
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    mes = request.query_params.get("mes") or alq.mes_actual()
    if not validate_mes(mes):
        return JSONResponse({"error": "mes inválido (YYYY-MM)"}, status_code=400)

    contrato = alq.get_contrato(telegram_id)
    if not contrato:
        return JSONResponse({"contrato": None, "items": [], "total": 0, "pendiente": 0})

    # Si es el mes en curso o el próximo, aseguramos que existan los pendientes
    if alq.mes_actual() <= mes <= alq.sumar_meses(alq.mes_actual(), 1):
        alq.asegurar_mes(telegram_id, mes)

    resumen = alq.resumen_mes(telegram_id, mes)
    canon = alq.canon_para_mes(contrato, mes)
    return JSONResponse({
        "contrato": {
            "direccion": contrato.get("direccion"),
            "inicio": contrato["inicio"],
            "dia_vencimiento": contrato.get("dia_vencimiento", 10),
        },
        "canon": canon,
        **resumen,
    })


@app.post("/api/alquiler")
async def alquiler_post(request: Request):
    """{resource: 'pagar', id} | {resource: 'pagar_mes', mes} | {resource: 'descuento', mes, monto, detalle}"""
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err

    body = await request.json()
    resource = body.get("resource", "")

    if resource == "pagar":
        n = alq.marcar_pagado(telegram_id, mov_id=int(body["id"]))
        return JSONResponse({"ok": True, "actualizados": n})

    if resource == "pagar_mes":
        mes = body.get("mes", "")
        if not validate_mes(mes):
            return JSONResponse({"error": "mes inválido"}, status_code=400)
        n = alq.marcar_pagado(telegram_id, mes=mes)
        return JSONResponse({"ok": True, "actualizados": n})

    if resource == "descuento":
        mes = body.get("mes", "")
        detalle = (body.get("detalle") or "").strip()
        try:
            monto = float(body.get("monto"))
        except (TypeError, ValueError):
            return JSONResponse({"error": "monto inválido"}, status_code=400)
        if not validate_mes(mes) or not detalle or monto == 0:
            return JSONResponse({"error": "faltan mes/monto/detalle"}, status_code=400)
        row = alq.agregar_descuento(telegram_id, mes, monto, detalle)
        return JSONResponse({"ok": True, "movimiento": row})

    return JSONResponse({"error": "resource requerido: pagar|pagar_mes|descuento"}, status_code=400)
