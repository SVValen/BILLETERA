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
    """
    supabase = get_supabase()
    pending = (
        supabase.table("movimientos")
        .select("id, monto")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente_descripcion_transferencia")
        .order("id", desc=True)
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
    return True
