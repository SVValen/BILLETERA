from lib.supabase_client import get_supabase
from ..tg import _send
from ..keyboards import _category_keyboard


async def handle_transferencia_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    """
    Captura la descripción de una transferencia detectada por mail que quedó en
    estado 'pendiente_descripcion_transferencia' (mismo patrón que
    esperando_edicion_monto / tope_variable IS NULL). Guarda la descripción y
    siempre pide la categoría con botones — no auto-categoriza en silencio,
    porque el usuario pidió confirmar categoría + descripción en cada transferencia.

    Si llegaron varias transferencias antes de que el usuario respondiera (ej. el
    cron detectó 3 en una corrida), se resuelven en orden de llegada (más vieja
    primero) — antes tomaba siempre la más reciente y las anteriores quedaban
    huérfanas para siempre esperando una descripción que nunca llegaba.
    """
    supabase = get_supabase()
    pending = (
        supabase.table("movimientos")
        .select("id, monto")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente_descripcion_transferencia")
        .order("id")
        .limit(1)
        .execute()
    )
    if not pending.data:
        return False

    mov = pending.data[0]
    descripcion = text.strip()

    supabase.table("movimientos").update({
        "descripcion": descripcion,
        "estado": "pendiente_categoria",
    }).eq("id", mov["id"]).execute()

    await _send(
        chat_id,
        f"📌 Guardé *${mov['monto']:,.0f}* — ¿en qué categoría va *{descripcion}*?",
        token,
        reply_markup=_category_keyboard(mov["id"]),
    )

    # Si queda otra transferencia pendiente de descripción, avisar de una para
    # que el usuario sepa que tiene que responder de nuevo (si no, queda huérfana).
    otra = (
        supabase.table("movimientos")
        .select("id, monto")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente_descripcion_transferencia")
        .order("id")
        .limit(1)
        .execute()
    )
    if otra.data:
        siguiente = otra.data[0]
        await _send(
            chat_id,
            f"💸 También tenés otra transferencia pendiente de *${siguiente['monto']:,.0f}* — ¿qué descripción le pongo?",
            token,
        )

    return True


async def handle_transferencia_callback(parts: list[str], callback_id: str, chat_id: int,
                                        message_id: int, user_id: str, token: str) -> bool:
    """trf:<id>:<clave> — respuesta a "¿Qué pagaste con esta transferencia?"."""
    if not parts or parts[0] != "trf" or len(parts) < 3:
        return False
    from lib import transferencias as trf_lib
    from ..tg import _answer_callback, _edit_message

    try:
        trf_id = int(parts[1])
    except ValueError:
        await _answer_callback(callback_id, token, "Opción inválida")
        return True
    clave = ":".join(parts[2:])
    trf = trf_lib.get(user_id, trf_id)
    mensaje, _ = trf_lib.aplicar(user_id, trf_id, clave)
    await _answer_callback(callback_id, token)
    encabezado = trf_lib.texto_pregunta(trf).split("\n")[0] if trf else ""
    await _edit_message(chat_id, message_id, f"{encabezado}\n{mensaje}".strip(), token)
    return True


async def handle_transferencias_cmd(user_id: str, chat_id: int, token: str) -> None:
    """/transferencias — vuelve a preguntar por las transferencias sin resolver."""
    from lib import transferencias as trf_lib

    pend = trf_lib.pendientes(user_id)
    if not pend:
        await _send(chat_id, "No tenés transferencias pendientes de clasificar.", token, parse_mode="")
        return
    if len(pend) > 1:
        await _send(chat_id, f"Tenés {len(pend)} transferencias sin clasificar. Vamos de a una:", token, parse_mode="")
    await _send(chat_id, trf_lib.texto_pregunta(pend[0]), token, reply_markup=trf_lib.teclado(user_id, pend[0]))
