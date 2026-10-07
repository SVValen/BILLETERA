import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.auth import get_telegram_id_from_request
from lib.date_utils import validate_mes

app = FastAPI()

CAT_COMPRAS_FAMILIA = 15


def _monto(asig: dict, mov: dict) -> float:
    return float(asig["monto_mensual"]) if asig.get("monto_mensual") is not None else float(mov["monto"])


@app.get("/api/familia")
async def familia_get(request: Request):
    """GET ?mes=YYYY-MM → por familiar, lo que le corresponde pagar ese mes (cuotas y compras
    asignadas), y las compras con tarjeta del mes que todavía no están asignadas."""
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err
    mes = request.query_params.get("mes", "")
    if not validate_mes(mes):
        return JSONResponse({"error": "mes inválido (YYYY-MM)"}, status_code=400)

    sb = get_supabase()
    fam_r = sb.table("familiares").select("id, nombre, telefono").eq("usuario_id", telegram_id).eq("activo", True).order("id").execute()
    familiares = fam_r.data or []
    fam_ids = [f["id"] for f in familiares]

    movs_r = (
        sb.table("movimientos")
        .select("id, descripcion, monto, cuota_plan_id, cuota_nro, cuota_total, grupo, categoria_id")
        .eq("usuario_id", telegram_id).eq("mes_resumen", mes).eq("tipo", "gasto")
        .neq("estado", "anulado").neq("es_pago_tarjeta", True)
        .not_.is_("tarjeta_id", "null")
        .order("monto", desc=True).execute()
    )
    movs = movs_r.data or []

    asigs = []
    if fam_ids:
        asigs = (
            sb.table("familia_asignaciones").select("id, familiar_id, cuota_plan_id, movimiento_id, monto_mensual, nota")
            .in_("familiar_id", fam_ids).execute()
        ).data or []
    por_plan: dict[int, list[dict]] = {}
    por_mov: dict[int, list[dict]] = {}
    for a in asigs:
        if a.get("cuota_plan_id"):
            por_plan.setdefault(a["cuota_plan_id"], []).append(a)
        if a.get("movimiento_id"):
            por_mov.setdefault(a["movimiento_id"], []).append(a)

    items: dict[int, list[dict]] = {f["id"]: [] for f in familiares}
    asignados: set[int] = set()
    for m in movs:
        aplicables = por_mov.get(m["id"], []) + (por_plan.get(m["cuota_plan_id"], []) if m.get("cuota_plan_id") else [])
        for a in aplicables:
            if a["familiar_id"] not in items:
                continue
            asignados.add(m["id"])
            items[a["familiar_id"]].append({
                "asignacion_id": a["id"],
                "movimiento_id": m["id"],
                "descripcion": m["descripcion"].split(" (cuota ")[0],
                "cuota_nro": m.get("cuota_nro"),
                "cuota_total": m.get("cuota_total"),
                "tarjeta": (m.get("grupo") or "").replace("Tarjeta ", ""),
                "monto": round(_monto(a, m), 2),
                "parcial": a.get("monto_mensual") is not None,
                "nota": a.get("nota"),
            })

    resultado = [
        {**f, "items": items[f["id"]], "total": round(sum(i["monto"] for i in items[f["id"]]), 2)}
        for f in familiares
    ]
    sin_asignar = [
        {"id": m["id"], "descripcion": m["descripcion"], "monto": float(m["monto"]),
         "cuota_plan_id": m.get("cuota_plan_id"), "tarjeta": (m.get("grupo") or "").replace("Tarjeta ", ""),
         "sugerido": m.get("categoria_id") == CAT_COMPRAS_FAMILIA}
        for m in movs if m["id"] not in asignados
    ]
    sin_asignar.sort(key=lambda x: (not x["sugerido"], -x["monto"]))
    return JSONResponse({"mes": mes, "familiares": resultado, "sin_asignar": sin_asignar})


@app.post("/api/familia")
async def familia_post(request: Request):
    """{resource: 'familiar', id?, nombre, telefono}
       {resource: 'asignar', familiar_id, movimiento_id, por_plan (bool), monto_mensual?, nota?}
       {resource: 'desasignar', id}"""
    telegram_id, err = await get_telegram_id_from_request(request)
    if err:
        return err
    body = await request.json()
    resource = body.get("resource", "")
    sb = get_supabase()

    def _es_mio(familiar_id) -> bool:
        r = sb.table("familiares").select("id").eq("id", int(familiar_id)).eq("usuario_id", telegram_id).limit(1).execute()
        return bool(r.data)

    if resource == "familiar":
        nombre = (body.get("nombre") or "").strip()[:60]
        telefono = "".join(ch for ch in str(body.get("telefono") or "") if ch.isdigit())[:20] or None
        if not nombre:
            return JSONResponse({"error": "Falta el nombre"}, status_code=400)
        if body.get("id"):
            if not _es_mio(body["id"]):
                return JSONResponse({"error": "Familiar no encontrado"}, status_code=404)
            r = sb.table("familiares").update({"nombre": nombre, "telefono": telefono}).eq("id", int(body["id"])).execute()
        else:
            r = sb.table("familiares").insert({"usuario_id": telegram_id, "nombre": nombre, "telefono": telefono}).execute()
        return JSONResponse({"ok": True, "familiar": r.data[0] if r.data else None})

    if resource == "asignar":
        familiar_id = body.get("familiar_id")
        if not familiar_id or not _es_mio(familiar_id):
            return JSONResponse({"error": "Familiar no encontrado"}, status_code=404)
        mov = (
            sb.table("movimientos").select("id, cuota_plan_id")
            .eq("id", int(body.get("movimiento_id") or 0)).eq("usuario_id", telegram_id).limit(1).execute()
        )
        if not mov.data:
            return JSONResponse({"error": "Compra no encontrada"}, status_code=404)
        monto = body.get("monto_mensual")
        try:
            monto = round(float(monto), 2) if monto not in (None, "") else None
        except (TypeError, ValueError):
            return JSONResponse({"error": "monto inválido"}, status_code=400)
        fila = {"familiar_id": int(familiar_id), "monto_mensual": monto, "nota": (body.get("nota") or None)}
        if body.get("por_plan", True) and mov.data[0].get("cuota_plan_id"):
            fila["cuota_plan_id"] = mov.data[0]["cuota_plan_id"]
        else:
            fila["movimiento_id"] = mov.data[0]["id"]
        r = sb.table("familia_asignaciones").insert(fila).execute()
        return JSONResponse({"ok": True, "asignacion": r.data[0] if r.data else None})

    if resource == "desasignar":
        a = sb.table("familia_asignaciones").select("id, familiar_id").eq("id", int(body.get("id") or 0)).limit(1).execute()
        if not a.data or not _es_mio(a.data[0]["familiar_id"]):
            return JSONResponse({"error": "Asignación no encontrada"}, status_code=404)
        sb.table("familia_asignaciones").delete().eq("id", a.data[0]["id"]).execute()
        return JSONResponse({"ok": True})

    return JSONResponse({"error": "resource requerido: familiar|asignar|desasignar"}, status_code=400)
