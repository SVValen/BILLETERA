"""
Transferencias que salen del Santander (aviso por mail).

El sueldo entra al Santander y desde ahí se manda plata a las cuentas desde donde se
paga cada cosa (Naranja X, Mercado Pago, BBVA, Nación). Esas transferencias NO son
gastos: el gasto es el resumen de la tarjeta, la cuota del préstamo o el alquiler.

Por eso cada transferencia se guarda en la tabla `transferencias` (no en movimientos)
y el bot pregunta a qué corresponde:
  - pago de un resumen de tarjeta  → registra / completa el pago (sin duplicar si ya
    estaba marcado desde el dashboard)
  - cuota de préstamo              → marca la cuota pagada al monto de la cuota (la
    transferencia puede ser solo lo que faltaba, ej. el sueldo UTN ya entra al Nación)
  - alquiler del mes               → marca pagado lo pendiente
  - gasto real (a otra persona)    → sigue el flujo de siempre (descripción + categoría)
  - pase entre cuentas propias     → no se registra nada

Aprende por CBU: la próxima transferencia al mismo CBU sugiere primero lo mismo.
"""
from __future__ import annotations

from datetime import date

from lib.supabase_client import get_supabase
from lib.tarjetas import mes_siguiente

_MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

GASTO = "gasto"
PROPIA = "propia"


def _mes_corto(mes: str) -> str:
    return _MESES_CORTO[int(mes[5:]) - 1]


def fmt(n: float) -> str:
    return "$" + f"{n:,.0f}".replace(",", ".")


# ── registro ─────────────────────────────────────────────────────────────────

def registrar(usuario_id: str, monto: float, fecha: str, destinatario: str | None, cbu: str | None) -> dict | None:
    r = get_supabase().table("transferencias").insert({
        "usuario_id": int(usuario_id),
        "fecha": fecha,
        "monto": round(float(monto), 2),
        "destinatario": (destinatario or None) and destinatario[:120],
        "cbu": cbu or None,
        "estado": "pendiente",
    }).execute()
    return r.data[0] if r.data else None


def get(usuario_id: str, trf_id: int) -> dict | None:
    r = (
        get_supabase().table("transferencias").select("*")
        .eq("id", trf_id).eq("usuario_id", int(usuario_id)).limit(1).execute()
    )
    return r.data[0] if r.data else None


# ── opciones para preguntar ─────────────────────────────────────────────────

def _sugerencia(usuario_id: str, trf: dict) -> str | None:
    """Prefijo de lo que se eligió la última vez para el mismo CBU (o destinatario):
    'tarjeta:<id>', 'prestamo:<id>', 'alquiler', 'propia' o 'gasto'."""
    q = (
        get_supabase().table("transferencias").select("estado, aplicada_a")
        .eq("usuario_id", int(usuario_id)).neq("estado", "pendiente").neq("id", trf["id"])
    )
    if trf.get("cbu"):
        q = q.eq("cbu", trf["cbu"])
    elif trf.get("destinatario"):
        q = q.eq("destinatario", trf["destinatario"])
    else:
        return None
    r = q.order("id", desc=True).limit(1).execute()
    if not r.data:
        return None
    prev = r.data[0]
    if prev["estado"] != "pago":
        return prev["estado"]
    partes = (prev.get("aplicada_a") or "").split(":")
    if partes[0] in ("tarjeta", "prestamo") and len(partes) >= 2:
        return f"{partes[0]}:{partes[1]}"
    return partes[0] or None


def opciones(usuario_id: str, trf: dict) -> list[dict]:
    """Lista de {clave, texto} para el teclado. La clave va en el callback_data."""
    from lib.pagos import total_resumen_tarjeta

    sb = get_supabase()
    mes = trf["fecha"][:7]
    # del 20 en adelante ya se puede estar pagando lo del mes que viene
    meses = [mes, mes_siguiente(mes)] if int(trf["fecha"][8:10]) >= 20 else [mes]
    monto_trf = float(trf["monto"])
    ops: list[dict] = []

    # Resúmenes de tarjeta del mes y del siguiente
    tarjetas = (
        sb.table("tarjetas").select("id, nombre").eq("usuario_id", int(usuario_id))
        .eq("activa", True).order("nombre").execute()
    ).data or []
    pagos = (
        sb.table("tarjeta_pagos").select("tarjeta_id, mes_resumen, monto_pagado")
        .eq("usuario_id", int(usuario_id)).in_("mes_resumen", meses).execute()
    ).data or []
    pagado = {(p["tarjeta_id"], p["mes_resumen"]): p for p in pagos if p.get("monto_pagado") is not None}
    for t in tarjetas:
        if "santander" in t["nombre"].lower():
            continue  # se debita de la misma cuenta: no hay transferencia
        for m in meses:
            p = pagado.get((t["id"], m))
            total = total_resumen_tarjeta(usuario_id, t["id"], m)
            if not p and total <= 0:
                continue
            if p:
                texto = f"💳 {t['nombre']} {_mes_corto(m)} · ya marcada {fmt(float(p['monto_pagado']))}"
            else:
                texto = f"💳 {t['nombre']} {_mes_corto(m)} · {fmt(total)}"
            ops.append({"clave": f"t{t['id']}-{m}", "texto": texto, "pref": f"tarjeta:{t['id']}", "pagado": bool(p),
                        "monto": float(p["monto_pagado"]) if p else total})

    # Cuotas de préstamo de esos meses
    prestamos = {
        p["id"]: p for p in (
            sb.table("prestamos").select("id, nombre, total_cuotas").eq("usuario_id", int(usuario_id)).execute()
        ).data or []
    }
    if prestamos:
        cuotas = (
            sb.table("prestamo_cuotas").select("id, prestamo_id, numero_cuota, mes_previsto, pagado, monto_ordinario, capital")
            .in_("prestamo_id", list(prestamos)).in_("mes_previsto", meses).order("mes_previsto").execute()
        ).data or []
        for c in cuotas:
            pr = prestamos[c["prestamo_id"]]
            nombre = pr["nombre"].replace("Préstamo ", "")
            monto = float(c.get("monto_ordinario") or c.get("capital") or 0)
            cuota = f"{c['numero_cuota']}/{pr['total_cuotas']}" if pr.get("total_cuotas") else f"cuota {c['numero_cuota']}"
            estado = "ya marcada" if c["pagado"] else fmt(monto)
            ops.append({
                "clave": f"p{c['id']}",
                "texto": f"🏦 {nombre} {cuota} · {estado}",
                "pref": f"prestamo:{c['prestamo_id']}",
                "pagado": bool(c["pagado"]),
                "monto": monto,
            })

    # Alquiler
    for m in meses:
        items = (
            sb.table("movimientos").select("monto, pagado")
            .eq("usuario_id", str(usuario_id)).eq("grupo", "Alquiler").eq("mes_resumen", m)
            .neq("estado", "anulado").execute()
        ).data or []
        if not items:
            continue
        pendiente = sum(float(i["monto"]) for i in items if not i["pagado"])
        texto = f"🏠 Alquiler {_mes_corto(m)} · " + (fmt(pendiente) if pendiente > 0 else "ya marcado")
        total_alq = sum(float(i["monto"]) for i in items)
        ops.append({"clave": f"a{m}", "texto": texto, "pref": "alquiler", "pagado": pendiente <= 0,
                    "monto": pendiente if pendiente > 0 else total_alq})

    def _cerca(o: dict) -> float:
        return abs(o["monto"] - monto_trf) / max(monto_trf, 1)

    sug = _sugerencia(usuario_id, trf)
    # Lo pendiente, el más parecido en monto primero; lo ya marcado solo si el monto coincide
    # (sirve para vincular la transferencia sin cargar el pago dos veces)
    pend = sorted((o for o in ops if not o["pagado"]), key=_cerca)
    marcadas = sorted((o for o in ops if o["pagado"] and (_cerca(o) <= 0.1 or o["pref"] == sug)), key=_cerca)
    ops = (pend + marcadas)[:8]

    ops.append({"clave": GASTO, "texto": "🧾 Fue un gasto (a otra persona)", "pref": GASTO, "pagado": False})
    ops.append({"clave": PROPIA, "texto": "🔁 Pase entre mis cuentas, no es gasto", "pref": PROPIA, "pagado": False})

    if sug:
        # lo sugerido arriba de todo (el primero que coincida), con estrella
        for i, o in enumerate(ops):
            if o["pref"] == sug:
                o = ops.pop(i)
                o["texto"] = "⭐ " + o["texto"]
                ops.insert(0, o)
                break
    return ops


def teclado(usuario_id: str, trf: dict) -> dict:
    return {"inline_keyboard": [
        [{"text": o["texto"][:60], "callback_data": f"trf:{trf['id']}:{o['clave']}"}]
        for o in opciones(usuario_id, trf)
    ]}


def texto_pregunta(trf: dict) -> str:
    nombre = "".join(ch for ch in (trf.get("destinatario") or "") if ch not in "*_`[]")
    dest = f" a *{nombre}*" if nombre else ""
    return (
        f"💸 Transferiste *{fmt(float(trf['monto']))}*{dest} desde el Santander.\n"
        "¿Qué pagaste con eso?"
    )


# ── aplicar la respuesta ─────────────────────────────────────────────────────

def _cerrar(trf_id: int, estado: str, aplicada_a: str | None = None, movimiento_id: int | None = None) -> None:
    get_supabase().table("transferencias").update({
        "estado": estado, "aplicada_a": aplicada_a, "movimiento_id": movimiento_id,
    }).eq("id", trf_id).execute()


def _aplicar_tarjeta(usuario_id: str, trf: dict, tarjeta_id: int, mes: str) -> str:
    from lib.pagos import nombre_tarjeta, registrar_pago_tarjeta, total_resumen_tarjeta

    sb = get_supabase()
    monto = float(trf["monto"])
    nombre = nombre_tarjeta(tarjeta_id)
    clave = f"tarjeta:{tarjeta_id}:{mes}"
    calculado = total_resumen_tarjeta(usuario_id, tarjeta_id, mes)

    previo = (
        sb.table("tarjeta_pagos").select("monto_pagado, movimiento_id")
        .eq("usuario_id", int(usuario_id)).eq("tarjeta_id", tarjeta_id).eq("mes_resumen", mes)
        .limit(1).execute()
    ).data
    vinculadas = (
        sb.table("transferencias").select("monto")
        .eq("usuario_id", int(usuario_id)).eq("estado", "pago").eq("aplicada_a", clave)
        .neq("id", trf["id"]).execute()
    ).data or []

    if previo and previo[0].get("monto_pagado") is not None:
        ya = float(previo[0]["monto_pagado"])
        if vinculadas:
            # pago en partes: esta transferencia se suma a las anteriores
            nuevo = round(sum(float(v["monto"]) for v in vinculadas) + monto, 2)
            mov_id = registrar_pago_tarjeta(usuario_id, tarjeta_id, mes, calculado, nuevo)
            _cerrar(trf["id"], "pago", clave, mov_id)
            return f"✅ Sumé {fmt(monto)} al pago de *{nombre}* ({_mes_corto(mes)}): ahora van {fmt(nuevo)}."
        # ya la habías marcado pagada a mano: solo se vincula, no se carga de nuevo
        _cerrar(trf["id"], "pago", clave, previo[0].get("movimiento_id"))
        msg = f"✅ *{nombre}* ({_mes_corto(mes)}) ya estaba marcada pagada ({fmt(ya)}). No la cargo de nuevo."
        if abs(ya - monto) > 1:
            msg += f"\nOjo: marcaste {fmt(ya)} y transferiste {fmt(monto)}."
        return msg

    mov_id = registrar_pago_tarjeta(usuario_id, tarjeta_id, mes, calculado, monto)
    _cerrar(trf["id"], "pago", clave, mov_id)
    msg = f"✅ Marqué pagada *{nombre}* ({_mes_corto(mes)}) con {fmt(monto)}."
    if calculado > 0 and monto + 1 < calculado:
        msg += f"\nEl resumen cargado da {fmt(calculado)}: si mandás el resto, elegí la misma tarjeta y se suma."
    return msg


def _aplicar_prestamo(usuario_id: str, trf: dict, cuota_id: int) -> str:
    from lib.pagos import pagar_cuota_prestamo

    sb = get_supabase()
    c = (
        sb.table("prestamo_cuotas").select("id, prestamo_id, numero_cuota, pagado, monto_ordinario, capital")
        .eq("id", cuota_id).eq("usuario_id", int(usuario_id)).limit(1).execute()
    ).data
    if not c:
        return "No encontré esa cuota."
    c = c[0]
    pr = sb.table("prestamos").select("nombre, total_cuotas").eq("id", c["prestamo_id"]).limit(1).execute().data
    nombre = pr[0]["nombre"] if pr else "Préstamo"
    total = f"/{pr[0]['total_cuotas']}" if pr and pr[0].get("total_cuotas") else ""
    ya_estaba = bool(c["pagado"])
    actual = pagar_cuota_prestamo(usuario_id, cuota_id) or c
    monto_cuota = float(actual.get("monto_pagado") or c.get("monto_ordinario") or c.get("capital") or 0)
    _cerrar(trf["id"], "pago", f"prestamo:{c['prestamo_id']}:{cuota_id}", actual.get("movimiento_id"))

    if ya_estaba:
        return f"✅ La cuota {c['numero_cuota']}{total} de *{nombre}* ya estaba marcada pagada. No la cargo de nuevo."
    msg = f"✅ Marqué pagada la cuota {c['numero_cuota']}{total} de *{nombre}* ({fmt(monto_cuota)})."
    if float(trf["monto"]) + 1 < monto_cuota:
        msg += f"\nLa transferencia de {fmt(float(trf['monto']))} la tomo como lo que faltaba en esa cuenta."
    return msg


def _aplicar_alquiler(usuario_id: str, trf: dict, mes: str) -> str:
    from lib.alquiler import marcar_pagado

    n = marcar_pagado(usuario_id, mes=mes)
    _cerrar(trf["id"], "pago", f"alquiler:{mes}")
    if n == 0:
        return f"✅ El alquiler de {_mes_corto(mes)} ya estaba marcado pagado. No lo cargo de nuevo."
    return f"✅ Marqué pagado el alquiler de {_mes_corto(mes)} ({n} concepto{'s' if n != 1 else ''})."


def _como_gasto(usuario_id: str, trf: dict) -> int | None:
    r = get_supabase().table("movimientos").insert({
        "usuario_id": str(usuario_id),
        "fecha": trf["fecha"],
        "monto": float(trf["monto"]),
        "tipo": "gasto",
        "origen": "email",
        "estado": "pendiente_descripcion_transferencia",
        "mes_resumen": trf["fecha"][:7],
        "grupo": "Efectivo",
    }).execute()
    mov_id = r.data[0]["id"] if r.data else None
    _cerrar(trf["id"], "gasto", None, mov_id)
    return mov_id


def aplicar(usuario_id: str, trf_id: int, clave: str) -> tuple[str, bool]:
    """Aplica la opción elegida. Devuelve (mensaje, pedir_descripcion)."""
    trf = get(usuario_id, trf_id)
    if not trf:
        return "No encontré esa transferencia.", False
    if trf["estado"] != "pendiente":
        return "Esa transferencia ya estaba resuelta.", False

    if clave == PROPIA:
        _cerrar(trf_id, PROPIA)
        return f"🔁 Listo, {fmt(float(trf['monto']))} queda como pase entre tus cuentas (no suma como gasto).", False
    if clave == GASTO:
        _como_gasto(usuario_id, trf)
        return f"🧾 Lo cargo como gasto de {fmt(float(trf['monto']))}. ¿Qué descripción le pongo?", True
    if clave.startswith("t") and "-" in clave:
        tid, mes = clave[1:].split("-", 1)
        return _aplicar_tarjeta(usuario_id, trf, int(tid), mes), False
    if clave.startswith("p"):
        return _aplicar_prestamo(usuario_id, trf, int(clave[1:])), False
    if clave.startswith("a"):
        return _aplicar_alquiler(usuario_id, trf, clave[1:]), False
    return "Opción inválida.", False


def pendientes(usuario_id: str) -> list[dict]:
    r = (
        get_supabase().table("transferencias").select("*")
        .eq("usuario_id", int(usuario_id)).eq("estado", "pendiente").order("id").execute()
    )
    return r.data or []


def fecha_hoy() -> str:
    return date.today().isoformat()
