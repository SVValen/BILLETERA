"""
Handler de aportes de capital a portafolios.
Detecta mensajes como "sumé 500 USD al conservador" y actualiza capital_usd / capital_ars.
Después de confirmar, sugiere instrumentos RF para el capital nuevo.
"""
from lib.supabase_client import get_supabase
from lib.market_data import fetch_dolar_precio
from ..tg import _send, _answer_callback, _edit_message

_TIPO_EMOJI = {"conservador": "🛡️", "pasivo": "💰", "crecimiento": "📈", "oportunista": "🎯"}


def _nombre_port(p: dict) -> str:
    return p.get("nombre_personalizado") or p.get("nombre_sugerido") or p.get("tipo", "Portafolio").capitalize()


def _capital_txt(p: dict) -> str:
    usd = p.get("capital_usd") or 0
    ars = p.get("capital_ars") or 0
    parts = []
    if usd:
        parts.append(f"${usd:,.0f} USD")
    if ars:
        parts.append(f"${ars:,.0f} ARS")
    return " + ".join(parts) if parts else "sin capital registrado"


async def handle_aporte(parsed: dict, user_id: str, chat_id: int, token: str) -> bool:
    """Procesa un aporte detectado. Retorna True si lo manejó."""
    supabase = get_supabase()

    ports = (
        supabase.table("portafolios")
        .select("id, tipo, nombre_personalizado, nombre_sugerido, capital_usd, capital_ars, asignacion_rf_pct")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .execute()
    )
    portafolios = ports.data or []

    if not portafolios:
        await _send(chat_id, "No tenés portafolios activos. Creá uno con /portafolio_nuevo.", token, parse_mode="")
        return True

    monto = parsed["monto"]
    moneda = parsed["moneda"]
    hint = parsed.get("hint")

    # Intentar matchear el portafolio destino por hint
    selected = None
    if len(portafolios) == 1:
        selected = portafolios[0]
    elif hint:
        for p in portafolios:
            nombre = _nombre_port(p).lower()
            tipo = p.get("tipo", "").lower()
            if hint in nombre or hint in tipo or tipo in hint:
                selected = p
                break

    if selected:
        await _show_aporte_confirm(selected, monto, moneda, chat_id, token)
    else:
        # Mostrar selección de portafolio
        buttons = []
        for p in portafolios:
            emoji = _TIPO_EMOJI.get(p.get("tipo", ""), "📊")
            nombre = _nombre_port(p)
            cap = _capital_txt(p)
            buttons.append([{
                "text": f"{emoji} {nombre} ({cap})",
                "callback_data": f"aporte_port:{p['id']}:{monto}:{moneda}",
            }])

        moneda_txt = "USD" if moneda == "USD" else "ARS"
        await _send(
            chat_id,
            f"¿A qué portafolio sumás ${monto:,.0f} {moneda_txt}?",
            token,
            reply_markup={"inline_keyboard": buttons},
        )

    return True


async def _show_aporte_confirm(portafolio: dict, monto: float, moneda: str, chat_id: int, token: str) -> None:
    nombre = _nombre_port(portafolio)
    emoji = _TIPO_EMOJI.get(portafolio.get("tipo", ""), "📊")
    cap_actual = _capital_txt(portafolio)

    if moneda == "USD":
        nuevo_usd = (portafolio.get("capital_usd") or 0) + monto
        nuevo_ars = portafolio.get("capital_ars") or 0
        aporte_txt = f"+${monto:,.0f} USD"
    else:
        nuevo_usd = portafolio.get("capital_usd") or 0
        nuevo_ars = (portafolio.get("capital_ars") or 0) + monto
        aporte_txt = f"+${monto:,.0f} ARS"

    partes_nuevo = []
    if nuevo_usd:
        partes_nuevo.append(f"${nuevo_usd:,.0f} USD")
    if nuevo_ars:
        partes_nuevo.append(f"${nuevo_ars:,.0f} ARS")
    nuevo_txt = " + ".join(partes_nuevo)

    await _send(
        chat_id,
        f"💰 *Aporte a {emoji} {nombre}*\n\n"
        f"Aporte: *{aporte_txt}*\n"
        f"Capital actual: {cap_actual}\n"
        f"Nuevo total: *{nuevo_txt}*\n\n"
        f"¿Confirmás?",
        token,
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"aporte_ok:{portafolio['id']}:{monto}:{moneda}"},
            {"text": "❌ Cancelar", "callback_data": "aporte_cancel"},
        ]]},
    )


async def handle_aporte_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, token: str,
) -> bool:
    """Maneja aporte_port, aporte_ok, aporte_cancel. Retorna True si consumió el callback."""
    supabase = get_supabase()

    if parts[0] == "aporte_port" and len(parts) == 4:
        portafolio_id = int(parts[1])
        monto = float(parts[2])
        moneda = parts[3]

        p_r = supabase.table("portafolios").select("*").eq("id", portafolio_id).eq("usuario_id", user_id).limit(1).execute()
        if not p_r.data:
            await _answer_callback(callback_id, token)
            return True
        portafolio = p_r.data[0]

        await _answer_callback(callback_id, token)
        await _show_aporte_confirm(portafolio, monto, moneda, chat_id, token)
        return True

    if parts[0] == "aporte_ok" and len(parts) == 4:
        portafolio_id = int(parts[1])
        monto = float(parts[2])
        moneda = parts[3]

        p_r = supabase.table("portafolios").select("*").eq("id", portafolio_id).eq("usuario_id", user_id).limit(1).execute()
        if not p_r.data:
            await _answer_callback(callback_id, token)
            return True
        portafolio = p_r.data[0]

        # Obtener MEP para el registro
        dolar_data = await fetch_dolar_precio("bolsa")
        dolar_mep = dolar_data["precio"] if dolar_data else None

        # Actualizar capital en portafolio
        if moneda == "USD":
            nuevo_capital = (portafolio.get("capital_usd") or 0) + monto
            supabase.table("portafolios").update({"capital_usd": nuevo_capital}).eq("id", portafolio_id).execute()
            aporte_row = {"monto_usd": monto, "tipo_cambio_mep": dolar_mep}
        else:
            nuevo_capital = (portafolio.get("capital_ars") or 0) + monto
            supabase.table("portafolios").update({"capital_ars": nuevo_capital}).eq("id", portafolio_id).execute()
            monto_usd_equiv = round(monto / dolar_mep, 2) if dolar_mep else None
            aporte_row = {"monto_ars": monto, "monto_usd": monto_usd_equiv, "tipo_cambio_mep": dolar_mep}

        # Guardar historial de aporte
        supabase.table("aportes_portafolio").insert({
            "portafolio_id": portafolio_id,
            "usuario_id": user_id,
            "fecha": __import__("datetime").date.today().isoformat(),
            **aporte_row,
        }).execute()

        nombre = _nombre_port(portafolio)
        emoji = _TIPO_EMOJI.get(portafolio.get("tipo", ""), "📊")
        aporte_txt = f"${monto:,.0f} {moneda}"

        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"✅ *Aporte registrado*\n\n{emoji} {nombre}: +{aporte_txt}",
            token,
        )

        # Sugerir instrumentos RF para el capital nuevo
        portafolio_actualizado = {**portafolio}
        if moneda == "USD":
            portafolio_actualizado["capital_usd"] = nuevo_capital
        else:
            portafolio_actualizado["capital_ars"] = nuevo_capital

        await _sugerir_rf_para_aporte(
            chat_id, token, portafolio_actualizado,
            nuevo_usd=monto if moneda == "USD" else None,
            nuevo_ars=monto if moneda == "ARS" else None,
            dolar_mep=dolar_mep,
        )
        return True

    if parts[0] == "aporte_cancel":
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "✕ Aporte cancelado.", token)
        return True

    return False


async def _sugerir_rf_para_aporte(
    chat_id: int, token: str, portafolio: dict,
    nuevo_usd: float | None, nuevo_ars: float | None,
    dolar_mep: float | None,
) -> None:
    """Sugiere instrumentos RF específicamente para el capital recién sumado."""
    from .wizard_inversion import _sugerir_instrumentos_rf

    rf_pct = portafolio.get("asignacion_rf_pct") or 0
    if rf_pct <= 0:
        return

    # Calcular cuánto del aporte debería ir a RF según el % objetivo
    if nuevo_usd:
        capital_rf_nuevo_usd = nuevo_usd * rf_pct / 100
        capital_rf_nuevo_ars = capital_rf_nuevo_usd * (dolar_mep or 1200)
        intro = f"Del aporte de ${nuevo_usd:,.0f} USD, ~${capital_rf_nuevo_usd:,.0f} USD iría a RF ({rf_pct:.0f}% objetivo).\n"
    elif nuevo_ars:
        capital_rf_nuevo_ars = nuevo_ars * rf_pct / 100
        capital_rf_nuevo_usd = capital_rf_nuevo_ars / (dolar_mep or 1200) if dolar_mep else 0
        intro = f"Del aporte de ${nuevo_ars:,.0f} ARS, ~${capital_rf_nuevo_ars:,.0f} ARS iría a RF ({rf_pct:.0f}% objetivo).\n"
    else:
        return

    if capital_rf_nuevo_ars < 10_000:
        return

    await _sugerir_instrumentos_rf(
        chat_id, token, portafolio,
        nuevo_capital_usd=capital_rf_nuevo_usd,
        nuevo_capital_ars=capital_rf_nuevo_ars,
        intro_override=intro,
    )
