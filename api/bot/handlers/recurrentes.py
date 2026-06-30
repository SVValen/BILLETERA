import re
from datetime import date
from lib.supabase_client import get_supabase
from ..tg import _send, _get_dolar_oficial
from ..helpers import _detect_currency, _categorize
from .presupuestos import _check_presupuesto_alert


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


async def handle_recurrente_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    """
    Detecta si el usuario está respondiendo con el nuevo monto de un recurrente
    (callback "Editar monto" tocado previamente). Actualiza el monto base del
    recurrente y registra la ocurrencia de hoy con el monto nuevo.
    Retorna True si consumió el mensaje.
    """
    supabase = get_supabase()
    pending = (
        supabase.table("recurrentes")
        .select("*")
        .eq("usuario_id", user_id)
        .eq("esperando_edicion_monto", True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not pending.data:
        return False

    rec = pending.data[0]
    num_match = re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
    if not num_match:
        await _send(chat_id, "No entendí el monto 🤔 Enviá solo el número.", token)
        return True

    nuevo_monto = float(num_match.group().replace(",", "."))
    supabase.table("recurrentes").update(
        {"monto": nuevo_monto, "esperando_edicion_monto": False}
    ).eq("id", rec["id"]).execute()

    supabase.table("movimientos").insert({
        "usuario_id": rec["usuario_id"],
        "fecha": date.today().isoformat(),
        "descripcion": rec["descripcion"],
        "monto": nuevo_monto,
        "categoria_id": rec["categoria_id"],
        "tipo": rec["tipo"],
        "origen": "telegram",
        "estado": "confirmado",
    }).execute()
    supabase.table("recurrentes").update(
        {"ultimo_recordatorio": date.today().isoformat()}
    ).eq("id", rec["id"]).execute()

    await _send(chat_id,
        f"✅ Monto actualizado y registrado: *{rec['descripcion']}* ${nuevo_monto:,.0f}", token)

    if rec["tipo"] == "gasto":
        await _check_presupuesto_alert(
            usuario_id=rec["usuario_id"], categoria_id=rec["categoria_id"],
            chat_id=chat_id, token=token,
        )

    return True
