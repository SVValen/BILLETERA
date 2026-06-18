import re as _re
import json as _json
import urllib.parse
from datetime import date
from lib.supabase_client import get_supabase
from lib.market_data import fetch_dolar_precio
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

    # Resolver portafolio — usa el de mayor asignación RF como default
    ports = (
        supabase.table("portafolios")
        .select("id, asignacion_rf_pct, nombre_personalizado, nombre_sugerido")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .order("asignacion_rf_pct", desc=True)
        .limit(1)
        .execute()
    )
    if not ports.data:
        await _send(chat_id, "No tenés portafolios activos. Creá uno con /portafolio_nuevo.", token, parse_mode="")
        return
    portafolio = ports.data[0]
    portafolio_id = portafolio["id"]

    monto_ars = datos["monto_ars"]
    tipo = datos["tipo"]

    # Resolver instrumento
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

    if not instrumento:
        ticker_txt = datos.get("ticker") or tipo
        await _send(chat_id, f"No encontré *{ticker_txt}* en la base de instrumentos RF. Verificá el ticker.", token, parse_mode="")
        return

    # Requiere dólar para monto_usd_entrada (NOT NULL en schema)
    dolar = await _get_dolar_oficial()
    if not dolar:
        await _send(chat_id, "No pude obtener el tipo de cambio para calcular el equivalente USD. Intentá de nuevo.", token, parse_mode="")
        return

    monto_usd_entrada = round(monto_ars / dolar, 2)
    tna = instrumento.get("tna_actual")
    nombre = instrumento.get("nombre") or tipo
    port_nombre = portafolio.get("nombre_personalizado") or portafolio.get("nombre_sugerido") or "Portafolio"

    tna_txt = f" @ {tna:.1f}% TNA" if tna else ""
    payload = {
        "portafolio_id": portafolio_id,
        "instrumento_id": instrumento["id"],
        "monto_ars": monto_ars,
        "monto_usd_entrada": monto_usd_entrada,
        "tna_contratada": tna,
        "fecha_vencimiento": instrumento.get("fecha_vencimiento"),
    }
    payload_enc = urllib.parse.quote(_json.dumps(payload))

    await _send(chat_id,
        f"📄 *Confirmar posición RF*\n\n"
        f"Instrumento: *{nombre}*{tna_txt}\n"
        f"Monto: ${monto_ars:,.0f} ARS (≈${monto_usd_entrada:,.0f} USD)\n"
        f"Portafolio: {port_nombre}\n\n"
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
            supabase.table("posiciones_rf").insert({
                "usuario_id": user_id,
                "portafolio_id": datos["portafolio_id"],
                "instrumento_id": datos["instrumento_id"],
                "monto_ars": datos["monto_ars"],
                "monto_usd_entrada": datos["monto_usd_entrada"],
                "tna_contratada": datos.get("tna_contratada"),
                "fecha_vencimiento": datos.get("fecha_vencimiento"),
            }).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✅ *Posición registrada.*\n\nUsá /liquidez para ver el estado de tu renta fija.",
                    token)
        except Exception as e:
            if token:
                await _answer_callback(callback_id, token, text="Error al registrar posición")
        return True

    if parts[0] == "rf_cancelar":
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "Registro cancelado.", token)
        return True

    if parts[0] == "rf_elegir" and len(parts) == 2:
        instrumento_id = int(parts[1])
        inst_r = supabase.table("instrumentos_rf").select("*").eq("id", instrumento_id).limit(1).execute()
        if not inst_r.data:
            await _answer_callback(callback_id, token)
            return True
        instrumento = inst_r.data[0]

        ports = (
            supabase.table("portafolios")
            .select("id, capital_usd, asignacion_rf_pct, nombre_personalizado, nombre_sugerido")
            .eq("usuario_id", user_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .order("asignacion_rf_pct", desc=True)
            .limit(1)
            .execute()
        )
        if not ports.data:
            await _answer_callback(callback_id, token)
            await _send(chat_id, "No tenés portafolios activos. Creá uno con /portafolio_nuevo.", token, parse_mode="")
            return True
        portafolio = ports.data[0]

        dolar_data = await fetch_dolar_precio("bolsa")
        dolar_mep = dolar_data["precio"] if dolar_data else 1200

        capital_usd = portafolio.get("capital_usd") or 0
        rf_pct = portafolio.get("asignacion_rf_pct") or 30
        capital_rf_ars = capital_usd * rf_pct / 100 * dolar_mep

        nombre_inst = instrumento.get("nombre") or instrumento.get("codigo")
        tna = instrumento.get("tna_actual")
        tna_txt = f" · {tna:.1f}% TNA" if tna else ""

        porcentajes = [(25, 0.25), (50, 0.50), (75, 0.75), (100, 1.0)]
        buttons = [
            [{"text": f"{pct}% — ${capital_rf_ars * frac:,.0f} ARS",
              "callback_data": f"rf_monto:{instrumento_id}:{int(capital_rf_ars * frac)}"}]
            for pct, frac in porcentajes
            if int(capital_rf_ars * frac) > 0
        ]

        await _answer_callback(callback_id, token)
        await _send(
            chat_id,
            f"💰 *{nombre_inst}*{tna_txt}\n\n"
            f"¿Cuánto ARS querés asignar?\n"
            f"_(Capital RF disponible: ${capital_rf_ars:,.0f} ARS · MEP ${dolar_mep:,.0f})_",
            token,
            reply_markup={"inline_keyboard": buttons},
        )
        return True

    if parts[0] == "rf_monto" and len(parts) == 3:
        instrumento_id = int(parts[1])
        monto_ars = float(parts[2])

        inst_r = supabase.table("instrumentos_rf").select("*").eq("id", instrumento_id).limit(1).execute()
        if not inst_r.data:
            await _answer_callback(callback_id, token)
            return True
        instrumento = inst_r.data[0]

        ports = (
            supabase.table("portafolios")
            .select("id, capital_usd, asignacion_rf_pct, nombre_personalizado, nombre_sugerido")
            .eq("usuario_id", user_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .order("asignacion_rf_pct", desc=True)
            .limit(1)
            .execute()
        )
        portafolio = ports.data[0] if ports.data else {}
        portafolio_id = portafolio.get("id")

        dolar_data = await fetch_dolar_precio("bolsa")
        dolar_mep = dolar_data["precio"] if dolar_data else None
        if not dolar_mep:
            await _answer_callback(callback_id, token, text="No pude obtener tipo de cambio")
            return True

        monto_usd_entrada = round(monto_ars / dolar_mep, 2)
        tna = instrumento.get("tna_actual")
        nombre = instrumento.get("nombre") or instrumento.get("codigo")
        tna_txt = f" @ {tna:.1f}% TNA" if tna else ""
        port_nombre = portafolio.get("nombre_personalizado") or portafolio.get("nombre_sugerido") or "Portafolio"

        payload = {
            "portafolio_id": portafolio_id,
            "instrumento_id": instrumento_id,
            "monto_ars": monto_ars,
            "monto_usd_entrada": monto_usd_entrada,
            "tna_contratada": tna,
            "fecha_vencimiento": instrumento.get("fecha_vencimiento"),
        }
        payload_enc = urllib.parse.quote(_json.dumps(payload))

        await _answer_callback(callback_id, token)
        await _send(
            chat_id,
            f"📄 *Confirmar posición RF*\n\n"
            f"Instrumento: *{nombre}*{tna_txt}\n"
            f"Monto: ${monto_ars:,.0f} ARS (≈${monto_usd_entrada:,.0f} USD)\n"
            f"Portafolio: {port_nombre}\n\n"
            f"¿Registrar esta posición?",
            token,
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Confirmar", "callback_data": f"rf_confirmar:{payload_enc}"},
                {"text": "❌ Cancelar", "callback_data": "rf_cancelar"},
            ]]},
        )
        return True

    if parts[0] == "rf_rescatar" and len(parts) == 2:
        pos_id = int(parts[1])
        pos_r = supabase.table("posiciones_rf").select("id, usuario_id").eq("id", pos_id).eq("usuario_id", user_id).limit(1).execute()
        if pos_r.data:
            supabase.table("posiciones_rf").update({
                "estado": "cerrada",
                "fecha_cierre": date.today().isoformat(),
            }).eq("id", pos_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✅ Posición cerrada. Usá /liquidez para ver el estado actualizado.",
                    token)
        return True

    return False
