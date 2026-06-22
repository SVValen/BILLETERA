"""
Handler para tarjetas de crédito.
  /tarjeta_nueva  — wizard con botones (nombre → día de cierre)
  /tarjetas       — lista las tarjetas activas del usuario
  Callbacks: tnueva_nom:{nombre}, tnueva_cie:{tarjeta_id}:{dia}
"""
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message

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
