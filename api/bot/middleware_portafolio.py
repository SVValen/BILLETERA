from lib.supabase_client import get_supabase
from .tg import _send, _answer_callback

_TIPO_EMOJI = {
    "conservador": "🛡️",
    "pasivo": "💰",
    "crecimiento": "📈",
    "oportunista": "🎯",
}


async def resolver_portafolio(
    usuario_id: str,
    chat_id: int,
    token: str,
    accion: str = "portafolio",
) -> dict | str:
    """
    Resuelve qué portafolio usar para una acción de inversión.

    Retorna:
    - dict con datos del portafolio si hay exactamente 1 activo
    - "no_portafolios" si el usuario no tiene ninguno
    - "selection_sent" si hay 2+ (envía botones inline y espera selección)
    """
    supabase = get_supabase()
    result = (
        supabase.table("portafolios")
        .select("id, tipo, nombre_personalizado, nombre_sugerido, capital_usd, asignacion_rf_pct")
        .eq("usuario_id", usuario_id)
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .execute()
    )
    portafolios = result.data or []

    if not portafolios:
        return "no_portafolios"

    if len(portafolios) == 1:
        return portafolios[0]

    buttons = []
    for p in portafolios:
        nombre = p.get("nombre_personalizado") or p.get("nombre_sugerido") or p["tipo"].capitalize()
        emoji = _TIPO_EMOJI.get(p["tipo"], "📊")
        cb = f"psel:{p['id']}:{accion}"
        buttons.append([{"text": f"{emoji} {nombre}", "callback_data": cb}])

    await _send(chat_id, "¿Para qué portafolio?", token, reply_markup={"inline_keyboard": buttons})
    return "selection_sent"


async def handle_psel_callback(
    parts: list[str],
    callback_id: str,
    chat_id: int,
    message_id: int,
    user_id: str,
    token: str,
) -> bool:
    """Maneja el callback psel:{portafolio_id}:{accion} tras selección de portafolio."""
    if parts[0] != "psel" or len(parts) < 3:
        return False

    portafolio_id = int(parts[1])
    accion = parts[2]

    await _answer_callback(callback_id, token)

    supabase = get_supabase()
    result = (
        supabase.table("portafolios")
        .select("*")
        .eq("id", portafolio_id)
        .eq("usuario_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return True

    portafolio = result.data[0]

    if accion == "portafolio":
        from .handlers.comandos_inversion import _handle_portafolio_cmd
        await _handle_portafolio_cmd(user_id, chat_id, token, portafolio=portafolio)
    elif accion == "liquidez":
        from .handlers.comandos_inversion import _handle_liquidez_cmd
        await _handle_liquidez_cmd(user_id, chat_id, token, portafolio=portafolio)

    return True
