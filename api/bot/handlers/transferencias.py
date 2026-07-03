from lib.supabase_client import get_supabase
from ..tg import _send
from ..keyboards import _category_keyboard
from ..helpers import _categorize


async def handle_transferencia_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    """
    Captura la descripción de una transferencia detectada por mail que quedó en
    estado 'pendiente_descripcion_transferencia' (mismo patrón que
    esperando_edicion_monto / tope_variable IS NULL). Si el texto categoriza a
    'Otros' pide categoría con botones; si no, confirma directo.
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
    categoria_id = await _categorize(descripcion, user_id)

    if categoria_id == 7:
        supabase.table("movimientos").update({
            "descripcion": descripcion,
            "categoria_id": categoria_id,
            "estado": "pendiente_categoria",
        }).eq("id", mov["id"]).execute()
        await _send(
            chat_id,
            f"📌 Guardé *${mov['monto']:,.0f}* — ¿en qué categoría va *{descripcion}*?",
            token,
            reply_markup=_category_keyboard(mov["id"]),
        )
        return True

    supabase.table("movimientos").update({
        "descripcion": descripcion,
        "categoria_id": categoria_id,
        "estado": "confirmado",
    }).eq("id", mov["id"]).execute()

    cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", categoria_id).single().execute()
    cat_name = cat_row.data.get("nombre", "Otros") if cat_row.data else "Otros"
    cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"
    await _send(
        chat_id,
        f"✅ Registrado: -${mov['monto']:,.0f} · {cat_emoji} {cat_name} · {descripcion}",
        token,
        parse_mode="",
    )
    return True
