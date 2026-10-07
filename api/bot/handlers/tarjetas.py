"""
Handler para tarjetas de crédito.
  /tarjeta_nueva  — wizard con botones (nombre → día de cierre)
  /tarjetas       — lista las tarjetas activas del usuario
  /pagar_tarjeta  — calcula lo que corresponde pagar este mes por tarjeta y registra el pago
  Callbacks: tnueva_nom:{nombre}, tnueva_cie:{tarjeta_id}:{dia}
             pagtar_confirmar:{tarjeta_id}:{mes}:{monto}, pagtar_editar:{tarjeta_id}:{mes}:{monto}
"""
import re
from datetime import date
from lib.supabase_client import get_supabase
from lib.tarjetas import mes_label
from ..tg import _send, _answer_callback, _edit_message

_CUOTA_RE = re.compile(r"\(cuota \d+/\d+\)")
_MES_ACTUAL = lambda: date.today().strftime("%Y-%m")

# Nombres comunes en Argentina
_NOMBRES_COMUNES = ["Naranja", "Santander", "BBVA", "Galicia", "Macro", "HSBC", "ICBC", "Visa", "Mastercard"]

# Días de cierre más comunes
_DIAS_CIERRE = [1, 3, 5, 8, 10, 13, 15, 18, 20, 22, 25, 28]


def _nombres_keyboard() -> dict:
    rows = []
    fila: list[dict] = []
    for nombre in _NOMBRES_COMUNES:
        fila.append({"text": nombre, "callback_data": f"tnueva_nom:{nombre}"})
        if len(fila) == 3:
            rows.append(fila)
            fila = []
    if fila:
        rows.append(fila)
    return {"inline_keyboard": rows}


def _dias_keyboard(tarjeta_id: int) -> dict:
    rows = []
    fila: list[dict] = []
    for dia in _DIAS_CIERRE:
        fila.append({"text": str(dia), "callback_data": f"tnueva_cie:{tarjeta_id}:{dia}"})
        if len(fila) == 4:
            rows.append(fila)
            fila = []
    if fila:
        rows.append(fila)
    return {"inline_keyboard": rows}


async def handle_tarjeta_nueva_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Muestra botones con nombres de tarjetas comunes."""
    await _send(
        chat_id,
        "💳 *Nueva tarjeta*\n\n¿Cómo se llama tu tarjeta?",
        token,
        reply_markup=_nombres_keyboard(),
    )


async def handle_tarjetas_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Lista las tarjetas activas del usuario."""
    supabase = get_supabase()
    rows = (
        supabase.table("tarjetas")
        .select("nombre, dia_cierre")
        .eq("usuario_id", user_id)
        .eq("activa", True)
        .order("nombre")
        .execute()
    )
    tarjetas = [r for r in (rows.data or []) if r.get("dia_cierre")]

    if not tarjetas:
        await _send(
            chat_id,
            "No tenés tarjetas configuradas.\n\nUsá /tarjeta_nueva para agregar una.",
            token,
            parse_mode="",
        )
        return

    lines = ["💳 *Tus tarjetas:*\n"]
    for t in tarjetas:
        lines.append(f"• {t['nombre']} — cierre día *{t['dia_cierre']}*")
    lines.append("\n_Los gastos con tarjeta se asignan automáticamente al mes de resumen._")
    await _send(chat_id, "\n".join(lines), token)


def get_tarjetas_activas(user_id: str) -> list[dict]:
    """Retorna las tarjetas activas del usuario con dia_cierre ya configurado."""
    supabase = get_supabase()
    rows = (
        supabase.table("tarjetas")
        .select("id, nombre, dia_cierre")
        .eq("usuario_id", user_id)
        .eq("activa", True)
        .order("nombre")
        .execute()
    )
    return [r for r in (rows.data or []) if r.get("dia_cierre")]


def pago_keyboard(tarjetas: list[dict], mov_id: int, incluir_efectivo: bool = True) -> dict:
    """
    Teclado de medio de pago para un movimiento.
    tarjetas: lista de {id, nombre} activas del usuario.
    """
    buttons: list[list[dict]] = []
    if incluir_efectivo:
        buttons.append([{"text": "💵 Efectivo", "callback_data": f"pago_tar:{mov_id}:0"}])
    for t in tarjetas:
        buttons.append([{"text": f"💳 {t['nombre']}", "callback_data": f"pago_tar:{mov_id}:{t['id']}"}])
    return {"inline_keyboard": buttons}


def cuota_tarjeta_keyboard(tarjetas: list[dict], plan_id: int) -> dict:
    """Teclado de tarjeta para registrar una compra en cuotas (sin opción Efectivo)."""
    buttons = [
        [{"text": f"💳 {t['nombre']}", "callback_data": f"cuota_tar:{plan_id}:{t['id']}"}]
        for t in tarjetas
    ]
    return {"inline_keyboard": buttons}


async def handle_tarjeta_callback(
    parts: list[str],
    callback_id: str,
    chat_id: int,
    message_id: int,
    user_id: str,
    supabase,
    token: str,
) -> bool:
    """
    Maneja callbacks del wizard de tarjeta nueva.
    tnueva_nom:{nombre} → guarda tarjeta pendiente (dia_cierre=NULL), muestra días
    tnueva_cie:{tarjeta_id}:{dia} → actualiza dia_cierre, activa la tarjeta
    """
    if parts[0] == "tnueva_nom" and len(parts) >= 2:
        nombre = ":".join(parts[1:])  # por si el nombre tuviera ':', aunque no debería

        # Eliminar duplicado pendiente si existe
        supabase.table("tarjetas").delete().eq("usuario_id", user_id).eq("nombre", nombre).is_("dia_cierre", "null").execute()

        result = supabase.table("tarjetas").insert({
            "usuario_id": user_id,
            "nombre": nombre,
            "dia_cierre": None,
            "activa": False,
        }).execute()
        if not result.data:
            await _answer_callback(callback_id, token)
            return True

        tarjeta_id = result.data[0]["id"]
        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"💳 *{nombre}* — ¿cuál es el día de cierre?\n_(El día en que el resumen cierra cada mes)_",
            token,
            reply_markup=_dias_keyboard(tarjeta_id),
        )
        return True

    if parts[0] == "last4_tar" and len(parts) == 3:
        map_id = int(parts[1])
        tarjeta_id = int(parts[2])

        upd = (
            supabase.table("tarjeta_last4_map")
            .update({"tarjeta_id": tarjeta_id})
            .eq("id", map_id)
            .eq("usuario_id", user_id)
            .execute()
        )
        if not upd.data:
            await _answer_callback(callback_id, token)
            return True

        nombre = await _nombre_tarjeta(supabase, tarjeta_id)
        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"✅ Asociada a *{nombre}*. La próxima vez que vea esa tarjeta no voy a volver a preguntar.",
            token,
        )
        return True

    if parts[0] == "tnueva_cie" and len(parts) == 3:
        tarjeta_id = int(parts[1])
        dia = int(parts[2])

        upd = (
            supabase.table("tarjetas")
            .update({"dia_cierre": dia, "activa": True})
            .eq("id", tarjeta_id)
            .eq("usuario_id", user_id)
            .execute()
        )
        if not upd.data:
            await _answer_callback(callback_id, token)
            return True

        nombre = upd.data[0]["nombre"]
        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"✅ *{nombre}* guardada — cierre día *{dia}*.\n\n"
            f"Ahora cuando registres un gasto te preguntaré si lo pagaste con tarjeta.",
            token,
        )
        return True

    return False


def _calcular_total_tarjeta(supabase, user_id: str, tarjeta_id: int, mes: str) -> float:
    """Suma cuotas + compras en 1 pago de una tarjeta para un mes_resumen dado."""
    rows = (
        supabase.table("movimientos")
        .select("monto")
        .eq("usuario_id", user_id)
        .eq("tarjeta_id", tarjeta_id)
        .eq("mes_resumen", mes)
        .eq("tipo", "gasto")
        .eq("es_pago_tarjeta", False)
        .neq("estado", "anulado")
        .execute()
    )
    return sum(float(r["monto"]) for r in (rows.data or []))


async def handle_pagar_tarjeta_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Muestra, por cada tarjeta activa, lo que corresponde pagar este mes de resumen."""
    supabase = get_supabase()
    mes = _MES_ACTUAL()
    tarjetas = get_tarjetas_activas(user_id)

    if not tarjetas:
        await _send(chat_id, "No tenés tarjetas configuradas.\n\nUsá /tarjeta_nueva para agregar una.", token, parse_mode="")
        return

    pagos_r = (
        supabase.table("tarjeta_pagos")
        .select("tarjeta_id, monto_pagado, fecha_pago")
        .eq("usuario_id", user_id)
        .eq("mes_resumen", mes)
        .execute()
    )
    pagados = {p["tarjeta_id"]: p for p in (pagos_r.data or []) if p.get("monto_pagado") is not None}

    lines = [f"🧾 *Resumen a pagar — {mes_label(mes).capitalize()}*\n"]
    buttons: list[list[dict]] = []
    sin_gastos = True

    for t in tarjetas:
        total = _calcular_total_tarjeta(supabase, user_id, t["id"], mes)
        pago = pagados.get(t["id"])
        if pago:
            lines.append(f"💳 *{t['nombre']}* — ✅ pagado ${pago['monto_pagado']:,.0f} el {pago.get('fecha_pago', '')}")
            continue
        if total <= 0:
            continue
        sin_gastos = False
        lines.append(f"💳 *{t['nombre']}* — ${total:,.0f} a pagar")
        monto_int = int(round(total))
        buttons.append([
            {"text": f"✅ Pagar {t['nombre']} (${total:,.0f})", "callback_data": f"pagtar_confirmar:{t['id']}:{mes}:{monto_int}"},
        ])
        buttons.append([
            {"text": "✏️ Editar monto", "callback_data": f"pagtar_editar:{t['id']}:{mes}:{monto_int}"},
        ])

    if sin_gastos and len(lines) == 1:
        lines.append("_No tenés gastos con tarjeta en el resumen de este mes._")

    await _send(chat_id, "\n".join(lines), token, reply_markup={"inline_keyboard": buttons} if buttons else None)


async def handle_pagar_tarjeta_callback(
    parts: list[str],
    callback_id: str,
    chat_id: int,
    message_id: int,
    user_id: str,
    supabase,
    token: str,
) -> bool:
    """
    pagtar_confirmar:{tarjeta_id}:{mes}:{monto} → registra el pago con el monto calculado
    pagtar_editar:{tarjeta_id}:{mes}:{monto_calculado} → pide el monto real por texto
    """
    if parts[0] == "pagtar_confirmar" and len(parts) == 4:
        tarjeta_id, mes, monto = int(parts[1]), parts[2], float(parts[3])
        await _registrar_pago_tarjeta(supabase, user_id, tarjeta_id, mes, monto, monto)
        nombre = await _nombre_tarjeta(supabase, tarjeta_id)
        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"✅ Pago registrado: *{nombre}* — ${monto:,.0f} ({mes_label(mes)}).",
            token,
        )
        return True

    if parts[0] == "pagtar_editar" and len(parts) == 4:
        tarjeta_id, mes, monto_calc = int(parts[1]), parts[2], float(parts[3])
        supabase.table("tarjeta_pagos").upsert({
            "usuario_id": user_id,
            "tarjeta_id": tarjeta_id,
            "mes_resumen": mes,
            "monto_calculado": monto_calc,
            "monto_pagado": None,
        }, on_conflict="usuario_id,tarjeta_id,mes_resumen").execute()
        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"✏️ Calculé ${monto_calc:,.0f}.\n\n_Respondé con el monto que realmente pagaste._",
            token,
        )
        return True

    return False


async def handle_pagar_tarjeta_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    """Detecta si el usuario está respondiendo con el monto real de un pago de tarjeta pendiente."""
    num_m = re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
    if not num_m:
        return False

    supabase = get_supabase()
    pend_r = (
        supabase.table("tarjeta_pagos")
        .select("id, tarjeta_id, mes_resumen, monto_calculado")
        .eq("usuario_id", user_id)
        .is_("monto_pagado", "null")
        .order("creado_at", desc=True)
        .limit(1)
        .execute()
    )
    if not pend_r.data:
        return False

    pendiente = pend_r.data[0]
    monto = float(num_m.group().replace(",", "."))
    if monto <= 0:
        return False

    await _registrar_pago_tarjeta(
        supabase, user_id, pendiente["tarjeta_id"], pendiente["mes_resumen"],
        float(pendiente["monto_calculado"]), monto,
    )
    nombre = await _nombre_tarjeta(supabase, pendiente["tarjeta_id"])
    await _send(
        chat_id,
        f"✅ Pago registrado: *{nombre}* — ${monto:,.0f} ({mes_label(pendiente['mes_resumen'])}).",
        token,
    )
    return True


async def _nombre_tarjeta(supabase, tarjeta_id: int) -> str:
    r = supabase.table("tarjetas").select("nombre").eq("id", tarjeta_id).limit(1).execute()
    return r.data[0]["nombre"] if r.data else "Tarjeta"


async def _registrar_pago_tarjeta(
    supabase, user_id: str, tarjeta_id: int, mes: str, monto_calculado: float, monto_pagado: float,
) -> None:
    """Inserta el movimiento de pago de resumen y actualiza/crea tarjeta_pagos (lib/pagos.py)."""
    from lib.pagos import registrar_pago_tarjeta
    registrar_pago_tarjeta(user_id, tarjeta_id, mes, monto_calculado, monto_pagado)



# ── Cierre variable: /cierre y botones que manda el cron ──────────────────────

def teclado_cierre(tarjeta_id: int, mes_resumen: str) -> dict:
    from lib.tarjetas import opciones_cierre
    fechas = opciones_cierre(mes_resumen)
    fila1 = [{"text": f.strftime("%d/%m"), "callback_data": f"cierre:{tarjeta_id}:{mes_resumen}:{f.isoformat()}"} for f in fechas[:4]]
    fila2 = [{"text": f.strftime("%d/%m"), "callback_data": f"cierre:{tarjeta_id}:{mes_resumen}:{f.isoformat()}"} for f in fechas[4:]]
    return {"inline_keyboard": [fila1, fila2]}


async def handle_cierre_cmd(text: str, user_id: str, chat_id: int, token: str) -> None:
    """/cierre santander 30/10 → guarda el cierre real. Sin argumentos, muestra botones."""
    import re as _re
    from datetime import date as _date
    from lib.tarjetas import registrar_cierre, mes_siguiente
    tarjetas = get_tarjetas_activas(user_id)
    m = _re.match(r"^/cierre\s+(\w+)\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text.strip(), _re.IGNORECASE)
    if not m:
        if not tarjetas:
            await _send(chat_id, "No tenés tarjetas configuradas.", token, parse_mode="")
            return
        mes_pago = mes_siguiente(_date.today().strftime("%Y-%m"))
        for t in tarjetas:
            await _send(chat_id, f"📅 ¿Cuándo cierra *{t['nombre']}* el resumen que pagás en {mes_label(mes_pago)}?",
                        token, reply_markup=teclado_cierre(t["id"], mes_pago))
        return
    nombre, dd, mm, yy = m.group(1).lower(), int(m.group(2)), int(m.group(3)), m.group(4)
    tarjeta = next((t for t in tarjetas if t["nombre"].lower().startswith(nombre)), None)
    if not tarjeta:
        await _send(chat_id, f"No encontré la tarjeta \"{m.group(1)}\".", token, parse_mode="")
        return
    hoy = _date.today()
    anio = int(yy) + (2000 if yy and len(yy) == 2 else 0) if yy else hoy.year
    try:
        fecha = _date(anio, mm, dd)
    except ValueError:
        await _send(chat_id, "Fecha inválida. Ej: `/cierre santander 30/10`", token)
        return
    # El resumen que cierra el 29/10 o el 2/11 se paga en noviembre
    mes_pago = mes_siguiente(fecha.strftime("%Y-%m")) if fecha.day >= 15 else fecha.strftime("%Y-%m")
    n = registrar_cierre(tarjeta["id"], mes_pago, fecha)
    await _send(chat_id, f"✅ *{tarjeta['nombre']}* cierra el {fecha.strftime('%d/%m')} (resumen de {mes_label(mes_pago)})."
                + (f" Reubiqué {n} compra{'s' if n != 1 else ''}." if n else ""), token)


async def handle_cierre_callback(parts: list[str], callback_id: str, chat_id: int,
                                 message_id: int, user_id: str, token: str) -> bool:
    if parts[0] != "cierre" or len(parts) != 4:
        return False
    from datetime import date as _date
    from lib.tarjetas import registrar_cierre
    tarjeta_id, mes_pago, fecha = int(parts[1]), parts[2], _date.fromisoformat(parts[3])
    n = registrar_cierre(tarjeta_id, mes_pago, fecha)
    nombre = await _nombre_tarjeta(get_supabase(), tarjeta_id)
    await _answer_callback(callback_id, token, "Listo ✅")
    await _edit_message(chat_id, message_id,
        f"✅ *{nombre}* cierra el {fecha.strftime('%d/%m')} (resumen de {mes_label(mes_pago)})."
        + (f" Reubiqué {n} compra{'s' if n != 1 else ''}." if n else ""), token)
    return True
