"""
Resumen del mes de pago: una sola cuenta para todo el dashboard.

  Entra     = ingresos con mes_resumen = mes
  Sale      = lo que se paga ese mes:
                · tarjetas: si el resumen ya está pagado, lo que realmente se pagó
                  (la diferencia con lo cargado es "sin detallar"); si no, lo cargado
                · préstamo, alquiler y demás: la suma de sus filas
  Te queda  = Entra − Sale

Cada grupo de "Sale" dice si ya está pagado, y con qué se paga lo que falta
(tarjeta → pago de resumen, préstamo → cuota, alquiler → mes).
"""
from __future__ import annotations

import re

from lib.supabase_client import get_supabase

_ESTADOS_EXCLUIDOS = ["anulado", "pendiente_moneda", "pendiente_tarjeta", "pendiente_descripcion_transferencia"]
_CUOTA_SUFIJO = re.compile(r"\s*\(cuota \d+/\d+\)$")

ORDEN_INGRESOS = ["Sueldo", "Cuotas familia", "Otros ingresos"]
ORDEN_GASTOS = ["Tarjeta Naranja", "Tarjeta Santander", "Préstamo", "Alquiler", "Tarjeta BBVA", "Tarjeta MP", "Efectivo"]
_NOMBRE_GRUPO = {"Alquiler": "Alquiler y servicios", "Préstamo": "Préstamos", "Tarjeta MP": "Tarjeta Mercado Pago"}


def _pos(orden: list[str], g: str) -> int:
    return orden.index(g) if g in orden else len(orden)


def _filas(usuario_id: str, mes: str) -> list[dict]:
    r = (
        get_supabase().table("movimientos")
        .select("id, descripcion, monto, tipo, grupo, concepto, moneda, monto_original, cuota_nro, cuota_total, "
                "debito_automatico, pagado, estimado, tarjeta_id, prestamo_id, categoria_id, categorias(nombre)")
        .eq("usuario_id", str(usuario_id)).eq("mes_resumen", mes)
        .neq("es_pago_tarjeta", True).not_.in_("estado", _ESTADOS_EXCLUIDOS)
        .order("monto", desc=True).execute()
    )
    out = []
    for f in r.data or []:
        cat = f.pop("categorias", None) or {}
        f["rubro"] = cat.get("nombre")
        f["monto"] = float(f["monto"])
        f["descripcion"] = _CUOTA_SUFIJO.sub("", f.get("descripcion") or "")
        out.append(f)
    return out


def _item(f: dict) -> dict:
    return {
        "id": f["id"],
        "descripcion": f["descripcion"],
        "monto": round(f["monto"], 2),
        "cuota_nro": f.get("cuota_nro"),
        "cuota_total": f.get("cuota_total"),
        "moneda": f.get("moneda") or "ARS",
        "monto_original": float(f["monto_original"]) if f.get("monto_original") is not None else None,
        "debito_automatico": bool(f.get("debito_automatico")),
        "estimado": bool(f.get("estimado")),
        "pagado": bool(f.get("pagado")),
        "concepto": f.get("concepto"),
        "rubro": f.get("rubro"),
        "proyectado": bool(f.get("proyectado")),
        "prestamo_id": f.get("prestamo_id"),
    }


def _proyecciones(usuario_id: str, mes: str, filas: list[dict]) -> list[dict]:
    """Filas virtuales (no están en la base) para que los meses futuros muestren lo que ya se
    sabe que viene: el alquiler de meses sin filas cargadas y las cuotas de préstamo que
    todavía no tienen movimiento. Ids negativos; todas estimadas y pendientes."""
    from lib.alquiler import mes_actual, proyectar_mes

    out: list[dict] = []
    if mes > mes_actual() and not any(f.get("grupo") == "Alquiler" for f in filas):
        for k, a in enumerate(proyectar_mes(usuario_id, mes)):
            out.append({
                "id": -(1000 + k), "descripcion": a["descripcion"], "monto": float(a["monto"]),
                "tipo": "gasto", "grupo": "Alquiler", "concepto": a["concepto"], "moneda": "ARS",
                "monto_original": None, "cuota_nro": None, "cuota_total": None, "debito_automatico": False,
                "pagado": False, "estimado": True, "tarjeta_id": None, "prestamo_id": None,
                "rubro": "Departamento", "proyectado": True,
            })

    sb = get_supabase()
    prestamos = {
        p["id"]: p for p in (
            sb.table("prestamos").select("id, nombre, total_cuotas").eq("usuario_id", int(usuario_id)).execute()
        ).data or []
    }
    if prestamos:
        cuotas = (
            sb.table("prestamo_cuotas").select("id, prestamo_id, numero_cuota, pagado, monto_ordinario, capital, movimiento_id")
            .in_("prestamo_id", list(prestamos)).eq("mes_previsto", mes).execute()
        ).data or []
        for c in cuotas:
            if c.get("movimiento_id") or c.get("pagado"):
                continue
            pr = prestamos[c["prestamo_id"]]
            out.append({
                "id": -(2000 + int(c["id"])), "descripcion": pr["nombre"],
                "monto": float(c.get("monto_ordinario") or c.get("capital") or 0),
                "tipo": "gasto", "grupo": "Préstamo", "concepto": None, "moneda": "ARS",
                "monto_original": None, "cuota_nro": c["numero_cuota"], "cuota_total": pr.get("total_cuotas"),
                "debito_automatico": True, "pagado": False, "estimado": False, "tarjeta_id": None,
                "prestamo_id": c["prestamo_id"], "rubro": "Préstamos", "cuota_id": c["id"],
            })
    return out


def resumen(usuario_id: str, mes: str, con_items: bool = True) -> dict:
    sb = get_supabase()
    filas = _filas(usuario_id, mes)
    filas += _proyecciones(usuario_id, mes, filas)

    # ── Entra ──
    ing: dict[str, list[dict]] = {}
    for f in filas:
        if f["tipo"] != "ingreso":
            continue
        g = f.get("grupo") if f.get("grupo") in ("Sueldo", "Cuotas familia") else "Otros ingresos"
        ing.setdefault(g, []).append(f)
    entra_grupos = [
        {"grupo": g, "total": round(sum(i["monto"] for i in items), 2),
         "items": [_item(i) for i in items] if con_items else []}
        for g, items in sorted(ing.items(), key=lambda kv: _pos(ORDEN_INGRESOS, kv[0]))
    ]
    entra = round(sum(g["total"] for g in entra_grupos), 2)

    # ── Sale ──
    pagos = {
        p["tarjeta_id"]: p for p in (
            sb.table("tarjeta_pagos").select("tarjeta_id, monto_pagado, monto_calculado, fecha_pago")
            .eq("usuario_id", int(usuario_id)).eq("mes_resumen", mes).execute()
        ).data or [] if p.get("monto_pagado") is not None
    }
    tarjetas = {
        t["id"]: t for t in (
            sb.table("tarjetas").select("id, nombre").eq("usuario_id", int(usuario_id)).execute()
        ).data or []
    }
    # estado real de las cuotas de préstamo (la tabla de cuotas manda)
    cuotas_por_mov: dict[int, dict] = {}
    mov_prestamo = [f["id"] for f in filas if f.get("prestamo_id")]
    if mov_prestamo:
        for c in (
            sb.table("prestamo_cuotas").select("id, movimiento_id, pagado")
            .in_("movimiento_id", mov_prestamo).execute()
        ).data or []:
            cuotas_por_mov[c["movimiento_id"]] = c

    gas: dict[str, list[dict]] = {}
    for f in filas:
        if f["tipo"] != "gasto":
            continue
        g = f.get("grupo") or "Efectivo"
        if f.get("tarjeta_id") and f["tarjeta_id"] in tarjetas:
            g = "Tarjeta " + tarjetas[f["tarjeta_id"]]["nombre"]
        gas.setdefault(g, []).append(f)

    # tarjetas pagadas sin nada cargado en el mes (igual salen)
    for tid, p in pagos.items():
        g = "Tarjeta " + tarjetas.get(tid, {}).get("nombre", "")
        gas.setdefault(g, [])

    sale_grupos = []
    for g, items in gas.items():
        cargado = round(sum(i["monto"] for i in items), 2)
        grupo: dict = {"grupo": g, "nombre": _NOMBRE_GRUPO.get(g, g), "cargado": cargado}
        tid = next((i["tarjeta_id"] for i in items if i.get("tarjeta_id")), None)
        if tid is None and g.startswith("Tarjeta "):
            tid = next((k for k, t in tarjetas.items() if "Tarjeta " + t["nombre"] == g), None)

        if tid is not None:
            p = pagos.get(tid)
            grupo.update({"tipo": "tarjeta", "tarjeta_id": tid})
            if p:
                pagado = round(float(p["monto_pagado"]), 2)
                grupo.update({
                    "total": pagado, "estado": "pagado", "monto_pagado": pagado, "fecha_pago": p.get("fecha_pago"),
                    "sin_detallar": round(pagado - cargado, 2) if abs(pagado - cargado) > 1 else 0,
                })
            else:
                grupo.update({"total": cargado, "estado": "pendiente", "monto_pagado": None, "sin_detallar": 0})
            pagado_monto = grupo["total"] if p else 0.0
        else:
            tipo = "prestamo" if g == "Préstamo" else "alquiler" if g == "Alquiler" else "otro"
            if any(i.get("proyectado") for i in items):
                grupo["proyectado"] = True
            for i in items:
                c = cuotas_por_mov.get(i["id"])
                if c is not None:
                    i["pagado"] = bool(c["pagado"])
                    i["cuota_id"] = c["id"]
            pend = [i for i in items if not i.get("pagado") and i.get("concepto") != "descuento"]
            pagado_monto = round(sum(i["monto"] for i in items if i.get("pagado") or i.get("concepto") == "descuento"), 2)
            grupo.update({
                "tipo": tipo, "total": cargado,
                "estado": "pagado" if not pend else ("pendiente" if len(pend) == len(items) else "parcial"),
                "falta": round(sum(i["monto"] for i in pend), 2),
            })
        grupo["pagado_monto"] = round(pagado_monto, 2)
        if con_items:
            grupo["items"] = []
            for i in items:
                it = _item(i)
                if i.get("cuota_id"):
                    it["cuota_id"] = i["cuota_id"]
                elif i.get("id", 0) > 0 and cuotas_por_mov.get(i["id"]):
                    it["cuota_id"] = cuotas_por_mov[i["id"]]["id"]
                grupo["items"].append(it)
        sale_grupos.append(grupo)

    sale_grupos.sort(key=lambda x: (_pos(ORDEN_GASTOS, x["grupo"]), -x["total"]))
    sale = round(sum(g["total"] for g in sale_grupos), 2)
    ya_pagado = round(sum(g["pagado_monto"] for g in sale_grupos), 2)
    return {
        "mes": mes,
        "entra": entra,
        "sale": sale,
        "te_queda": round(entra - sale, 2),
        "ya_pagado": ya_pagado,
        "falta_pagar": round(sale - ya_pagado, 2),
        "pendientes": sum(1 for g in sale_grupos if g["estado"] != "pagado"),
        "hay_estimados": any(i.get("estimado") for i in filas),
        "entra_grupos": entra_grupos,
        "sale_grupos": sale_grupos,
    }


def proximos(usuario_id: str, desde: str, n: int = 6) -> list[dict]:
    from lib.tarjetas import mes_siguiente

    out, mes = [], desde
    for _ in range(n):
        r = resumen(usuario_id, mes, con_items=False)
        out.append({
            "mes": mes, "entra": r["entra"], "sale": r["sale"], "te_queda": r["te_queda"],
            "hay_estimados": r["hay_estimados"],
            "entra_grupos": [{"grupo": g["grupo"], "total": g["total"]} for g in r["entra_grupos"]],
            "sale_grupos": [{"grupo": g["grupo"], "nombre": g["nombre"], "total": g["total"]} for g in r["sale_grupos"]],
        })
        mes = mes_siguiente(mes)
    return out


def por_rubro(usuario_id: str, mes: str) -> dict:
    """En qué se va la plata del mes: gastos por rubro, más lo pagado de tarjetas sin detallar."""
    from lib.alquiler import sumar_meses

    def _calc(m: str) -> dict[str, float]:
        r = resumen(usuario_id, m)
        out: dict[str, float] = {}
        for g in r["sale_grupos"]:
            for i in g.get("items", []):
                rubro = i.get("rubro") or "Otros"
                if g["grupo"] == "Alquiler":
                    rubro = "Departamento"
                elif g["grupo"] == "Préstamo":
                    rubro = "Préstamos"
                out[rubro] = out.get(rubro, 0) + i["monto"]
            if g.get("sin_detallar", 0) > 0:
                out["Tarjetas sin detallar"] = out.get("Tarjetas sin detallar", 0) + g["sin_detallar"]
        return out

    actual = _calc(mes)
    anterior = _calc(sumar_meses(mes, -1))
    total = sum(v for v in actual.values() if v > 0)
    rubros = [
        {"rubro": k, "monto": round(v, 2), "anterior": round(anterior.get(k, 0), 2),
         "pct": round(v / total * 100, 1) if total else 0}
        for k, v in actual.items() if abs(v) > 0.5
    ]
    rubros.sort(key=lambda x: -x["monto"])
    return {"mes": mes, "total": round(total, 2), "total_anterior": round(sum(v for v in anterior.values() if v > 0), 2),
            "rubros": rubros}
