import re as _re
import json as _json
import urllib.parse
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message, _get_dolar_oficial


_RF_PATRONES = [
    _re.compile(r"(?:puse|coloqué|coloque|meti|metí|ingresé|ingrese)\s+\$?([\d.,]+)\s+(?:en\s+)?cauc[ií]on?(?:\s+(\d+)\s*d[íi]as?)?", _re.IGNORECASE),
    _re.compile(r"(?:lecap|letra)\s+\$?([\d.,]+)(?:\s+([A-Z0-9]+))?", _re.IGNORECASE),
    _re.compile(r"\b(AL\d+|GD\d+|AE\d+)\s+\$?([\d.,]+)", _re.IGNORECASE),
]


def _parse_posicion_rf(text: str) -> dict | None:
    """Detecta si el usuario está registrando una posición de RF. Retorna datos básicos o None."""
    t = text.strip()

    m = _RF_PATRONES[0].search(t)
    if m:
        monto_raw = m.group(1).replace(".", "").replace(",", "")
        plazo = int(m.group(2)) if m.group(2) else 7
        try:
            return {"tipo": "caucion", "monto_ars": float(monto_raw), "plazo_dias": plazo, "ticker": None}
        except ValueError:
            pass

    m = _RF_PATRONES[1].search(t)
    if m:
        monto_raw = m.group(1).replace(".", "").replace(",", "")
        ticker = m.group(2)
        try:
            return {"tipo": "letra", "monto_ars": float(monto_raw), "ticker": ticker}
        except ValueError:
            pass

    m = _RF_PATRONES[2].search(t)
    if m:
        ticker = m.group(1).upper()
        monto_raw = m.group(2).replace(".", "").replace(",", "")
        try:
            return {"tipo": "bono_soberano", "monto_ars": float(monto_raw), "ticker": ticker}
        except ValueError:
            pass

    return None


async def _handle_nueva_posicion_rf(datos: dict, user_id: str, chat_id: int, token: str) -> None:
    """Confirma con el usuario antes de registrar una posición de RF."""
    supabase = get_supabase()
    monto_ars = datos["monto_ars"]
    tipo = datos["tipo"]

    instrumento = None
    if tipo == "caucion":
        plazo = datos.get("plazo_dias", 7)
        codigo = f"CAUCION_{plazo}D"
        inst_r = supabase.table("instrumentos_rf").select("*").eq("codigo", codigo).limit(1).execute()
        instrumento = inst_r.data[0] if inst_r.data else None
    elif datos.get("ticker"):
        inst_r = supabase.table("instrumentos_rf").select("*").eq("ticker_iol", datos["ticker"].upper()).limit(1).execute()
        if not inst_r.data:
            inst_r = supabase.table("instrumentos_rf").select("*").eq("codigo", datos["ticker"].upper()).limit(1).execute()
        instrumento = inst_r.data[0] if inst_r.data else None

    monto_usd = None
    tipo_cambio = None
    dolar = await _get_dolar_oficial()
    if dolar:
        tipo_cambio = dolar
        monto_usd = round(monto_ars / tipo_cambio, 2)

    tna = instrumento.get("tna_actual") if instrumento else None
    nombre = instrumento.get("nombre") if instrumento else (datos.get("ticker") or tipo)
    instrumento_id = instrumento["id"] if instrumento else None

    usd_txt = f" (≈${monto_usd:,.0f} USD)" if monto_usd else ""
    tna_txt = f" @ {tna:.1f}% TNA" if tna else ""

    payload = {
        "instrumento_id": instrumento_id,
        "tipo": tipo,
        "monto_ars": monto_ars,
        "monto_usd": monto_usd,
        "tipo_cambio": tipo_cambio,
        "tna": tna,
        "notas": datos.get("ticker"),
    }
    payload_enc = urllib.parse.quote(_json.dumps(payload))

    await _send(chat_id,
        f"📄 *Confirmar posición RF*\n\n"
        f"Instrumento: *{nombre}*\n"
        f"Monto: ${monto_ars:,.0f} ARS{usd_txt}\n"
        f"Tipo: {tipo}{tna_txt}\n\n"
        f"¿Registrar esta posición?",
        token,
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"rf_confirmar:{payload_enc}"},
            {"text": "❌ Cancelar",  "callback_data": "rf_cancelar"},
        ]]})


async def handle_rf_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:
    """Maneja rf_confirmar, rf_cancelar, rf_rescatar. Retorna True si consumió el callback."""
    if parts[0] == "rf_confirmar" and len(parts) >= 2:
        try:
            datos = _json.loads(urllib.parse.unquote(":".join(parts[1:])))
            instrumento_id = datos.get("instrumento_id")
            supabase.table("posiciones_rf").insert({
                "usuario_id": user_id,
                "instrumento_id": instrumento_id,
                "tipo": datos.get("tipo"),
                "monto_ars": datos["monto_ars"],
                "monto_usd": datos.get("monto_usd"),
                "tipo_cambio_entrada": datos.get("tipo_cambio"),
                "tna_contratada": datos.get("tna"),
                "fecha_vencimiento": datos.get("fecha_vencimiento"),
                "notas": datos.get("notas"),
            }).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✅ *Posición registrada.*\n\nUsá /liquidez para ver el estado de tu renta fija.",
                    token)
        except Exception:
            if token:
                await _answer_callback(callback_id, token, text="Error al registrar posición")
        return True

    if parts[0] == "rf_cancelar":
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "Registro cancelado.", token)
        return True

    if parts[0] == "rf_rescatar" and len(parts) == 2:
        pos_id = int(parts[1])
        pos_r = supabase.table("posiciones_rf").select("id, usuario_id").eq("id", pos_id).eq("usuario_id", user_id).limit(1).execute()
        if pos_r.data:
            supabase.table("posiciones_rf").update({"estado": "rescatada"}).eq("id", pos_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✅ Posición marcada como rescatada. Usá /liquidez para ver el estado actualizado.",
                    token)
        return True

    return False
