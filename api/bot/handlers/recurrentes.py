import re
from lib.supabase_client import get_supabase
from ..tg import _send, _get_dolar_oficial
from ..helpers import _detect_currency, _categorize


async def _registrar_recurrente(
    text: str, monto: float, descripcion: str, tipo: str,
    dia_mes: int, user_id: str, chat_id: int, token: str
) -> None:
    moneda = _detect_currency(text)
    if moneda == "USD":
        tasa = await _get_dolar_oficial()
        if not tasa:
            await _send(chat_id, "No pude obtener el tipo de cambio 😕 Intentá de nuevo.", token, parse_mode="")
            return
        desc_limpia = re.sub(r"^(?:usd|dolar|dólares?)\s+", "", descripcion, flags=re.IGNORECASE).strip()
        monto = round(monto * tasa)
        descripcion = f"{desc_limpia} (USD @ ${tasa:,.0f} oficial)"

    categoria_id = await _categorize(descripcion, user_id)
    supabase = get_supabase()
    supabase.table("recurrentes").insert({
        "usuario_id": user_id,
        "descripcion": descripcion,
        "monto": monto,
        "categoria_id": categoria_id,
        "tipo": tipo,
        "dia_del_mes": dia_mes,
        "activo": True,
    }).execute()
    sufijo = {1: "ro", 2: "do", 3: "ro"}.get(dia_mes, "to")
    await _send(chat_id,
        f"🔁 Recordatorio configurado:\n*{descripcion}* — ${monto:,.0f} — todos los *{dia_mes}{sufijo}* del mes",
        token)
