import csv
import io
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request

app = FastAPI()


@app.post("/api/prestamos_import")
async def importar_prestamo(request: Request):
    telegram_id = await get_telegram_id_from_request(request)
    if not telegram_id:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    body = await request.json()
    nombre = body.get("nombre", "Préstamo")
    filas = body.get("cuotas", [])  # list of dicts

    if not filas:
        return JSONResponse({"error": "No se enviaron cuotas"}, status_code=400)

    supabase = get_supabase()
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
