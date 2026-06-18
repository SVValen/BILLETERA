"""
Wizard de creación de portafolios (Fase 3).
Soporta 4 tipos: conservador, pasivo, crecimiento, oportunista.

Estados de estado_wizard en tabla portafolios:
  configurando_objetivo → configurando_renta (pasivo) | configurando_plazo (cons/crec) | configurando_capital (oportunista)
  configurando_capital → configurando_rf_pct → configurando_nombre → activo
"""
import re
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message

_TIPO_EMOJI = {
    "conservador": "🛡️",
    "pasivo": "💰",
    "crecimiento": "📈",
    "oportunista": "🎯",
}

_TIPO_DESCRIPCION = {
    "conservador": "Preservar capital con baja volatilidad. Alta proporción en renta fija.",
    "pasivo": "Generar renta mensual en pesos o dólares de forma predecible.",
    "crecimiento": "Hacer crecer el capital a mediano/largo plazo asumiendo más riesgo.",
    "oportunista": "Aprovechar oportunidades puntuales de mercado con alta liquidez.",
}

_TIPO_RF_OPCIONES = {
    "conservador": [60, 70, 80],
    "pasivo": [40, 50, 60],
    "crecimiento": [20, 30, 40],
    "oportunista": [10, 20, 30],
}

_ESTADOS_SOLO_BOTONES = ("configurando_plazo", "configurando_rf_pct")


# ─── Pantallas del wizard ──────────────────────────────────────────────────

async def _send_tipo_keyboard(chat_id: int, token: str) -> None:
    buttons = [
        [
            {"text": "🛡️ Conservador", "callback_data": "nuevo_portafolio:conservador"},
            {"text": "💰 Pasivo", "callback_data": "nuevo_portafolio:pasivo"},
        ],
        [
            {"text": "📈 Crecimiento", "callback_data": "nuevo_portafolio:crecimiento"},
            {"text": "🎯 Oportunista", "callback_data": "nuevo_portafolio:oportunista"},
        ],
    ]
    await _send(
        chat_id,
        "📊 *Nuevo Portafolio*\n\n¿Qué tipo de portafolio querés crear?\n\n"
        "🛡️ *Conservador* — capital seguro, alta RF\n"
        "💰 *Pasivo* — generar renta mensual\n"
        "📈 *Crecimiento* — hacer crecer capital\n"
        "🎯 *Oportunista* — oportunidades puntuales",
        token,
        reply_markup={"inline_keyboard": buttons},
    )


async def _ask_objetivo(chat_id: int, token: str) -> None:
    await _send(
        chat_id,
        "✍️ ¿Cuál es tu objetivo con este portafolio?\n\n"
        "_Ej: ahorrar para el auto, generar ingresos mensuales, diversificar dólares..._",
        token,
    )


async def _ask_plazo(chat_id: int, token: str, portafolio_id: int, tipo: str) -> None:
    if tipo == "conservador":
        options = [
            ("⏱ Corto plazo (<1 año)", "corto"),
            ("📅 Mediano plazo (1-3 años)", "mediano"),
            ("📆 Largo plazo (+3 años)", "largo"),
        ]
    else:  # crecimiento
        options = [
            ("📅 Mediano plazo (1-3 años)", "mediano"),
            ("📆 Largo plazo (+3 años)", "largo"),
        ]
    buttons = [[{"text": t, "callback_data": f"wiz_plazo:{portafolio_id}:{v}"}] for t, v in options]
    await _send(chat_id, "📅 ¿A qué plazo?", token, reply_markup={"inline_keyboard": buttons})


async def _ask_renta_mensual(chat_id: int, token: str, portafolio_id: int) -> None:
    await _send(
        chat_id,
        "💵 ¿Cuánto querés generar por mes? (en USD o ARS)\n\n"
        "_Ej: 500 USD, 200.000 ARS_\n\n"
        "O presioná el botón si querés maximizar la renta:",
        token,
        reply_markup={"inline_keyboard": [
            [{"text": "📈 El máximo posible", "callback_data": f"wiz_renta_max:{portafolio_id}"}]
        ]},
    )


async def _ask_capital(chat_id: int, token: str) -> None:
    await _send(
        chat_id,
        "💰 ¿Con cuánto capital contás? (en USD)\n\n_Ej: 5000_",
        token,
    )


async def _ask_rf_pct(chat_id: int, token: str, portafolio_id: int, tipo: str) -> None:
    pcts = _TIPO_RF_OPCIONES.get(tipo, [30, 50, 70])
    labels = {
        10: "10% RF", 20: "20% RF", 30: "30% RF",
        40: "40% RF", 50: "50% RF", 60: "60% RF",
        70: "70% RF", 80: "80% RF",
    }
    buttons = [[{"text": labels.get(p, f"{p}% RF"), "callback_data": f"wiz_rf_pct:{portafolio_id}:{p}"}] for p in pcts]
    await _send(
        chat_id,
        "⚖️ ¿Qué porcentaje querés en *Renta Fija* (cauciones, letras, bonos)?\n\n"
        f"_Rango recomendado para portafolio {tipo}: {pcts[0]}–{pcts[-1]}%_",
        token,
        reply_markup={"inline_keyboard": buttons},
    )


async def _sugerir_nombre(portafolio: dict) -> str:
    """Llama a Claude Haiku para sugerir un nombre corto al portafolio."""
    tipo = portafolio.get("tipo", "")
    objetivo = portafolio.get("objetivo") or ""
    capital = portafolio.get("capital_usd") or 0
    rf_pct = portafolio.get("asignacion_rf_pct") or 0
    renta = portafolio.get("renta_mensual_obj") or ""

    prompt = (
        f"Sugerí un nombre corto (2-4 palabras) para un portafolio de inversión:\n"
        f"Tipo: {tipo}\n"
        f"Objetivo: {objetivo}\n"
        f"Capital: ${capital:,.0f} USD\n"
        f"% Renta fija: {rf_pct}%\n"
    )
    if renta:
        prompt += f"Renta mensual objetivo: {renta}\n"
    prompt += (
        "\nRespondé SOLO con el nombre, sin comillas ni explicaciones. "
        "Ejemplos: Renta Mensual 2k / Capital Defensivo / Crecimiento Dólares"
    )

    try:
        import anthropic
        import os
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip().strip('"').strip("'")
    except Exception:
        return f"{tipo.capitalize()} {int(capital)}"


async def _finalizar_nombre(chat_id: int, token: str, portafolio: dict) -> None:
    """Llama a Claude, guarda nombre_sugerido y pregunta si confirma."""
    supabase = get_supabase()
    nombre = await _sugerir_nombre(portafolio)

    supabase.table("portafolios").update({
        "nombre_sugerido": nombre,
        "estado_wizard": "configurando_nombre",
    }).eq("id", portafolio["id"]).execute()

    await _send(
        chat_id,
        f"✨ ¿Lo llamamos *{nombre}*?\n\n"
        "Presioná para confirmar o escribí tu propio nombre:",
        token,
        reply_markup={"inline_keyboard": [
            [{"text": f"✅ Sí, usar «{nombre}»", "callback_data": f"wiz_nombre_ok:{portafolio['id']}"}]
        ]},
    )


async def _activar_portafolio(portafolio_id: int, nombre_personalizado: str | None) -> None:
    supabase = get_supabase()
    supabase.table("portafolios").update({
        "nombre_personalizado": nombre_personalizado,
        "estado_wizard": "activo",
        "activo": True,
    }).eq("id", portafolio_id).execute()


async def _send_portafolio_creado(chat_id: int, token: str, portafolio: dict, nombre: str) -> None:
    tipo = portafolio.get("tipo", "")
    capital = portafolio.get("capital_usd") or 0
    rf_pct = portafolio.get("asignacion_rf_pct") or 0
    emoji = _TIPO_EMOJI.get(tipo, "📊")

    await _send(
        chat_id,
        f"🎉 *¡Portafolio creado!*\n\n"
        f"{emoji} *{nombre}*\n"
        f"Tipo: {tipo.capitalize()}\n"
        f"Capital: ${capital:,.0f} USD\n"
        f"Renta fija: {rf_pct:.0f}% · Renta variable: {100 - rf_pct:.0f}%\n\n"
        "Usá /mis_portafolios para ver todos tus portafolios.",
        token,
    )


# ─── Callbacks del wizard ──────────────────────────────────────────────────

async def handle_wizard_callback(
    parts: list[str],
    callback_id: str,
    chat_id: int,
    message_id: int,
    user_id: str,
    supabase,
    token: str,
) -> bool:
    """Maneja los callbacks del wizard de portafolios. Retorna True si consumió el callback."""

    # ── Selección de tipo → crea la fila y pide objetivo ──
    if parts[0] == "nuevo_portafolio" and len(parts) == 2:
        tipo = parts[1]
        if tipo not in _TIPO_EMOJI:
            await _answer_callback(callback_id, token)
            return True

        existing = (
            supabase.table("portafolios")
            .select("id")
            .eq("usuario_id", user_id)
            .eq("tipo", tipo)
            .eq("activo", True)
            .execute()
        )
        if existing.data:
            await _answer_callback(callback_id, token)
            emoji = _TIPO_EMOJI[tipo]
            await _edit_message(
                chat_id, message_id,
                f"⚠️ Ya tenés un portafolio *{tipo}* activo ({emoji}). "
                "Solo puede haber uno por tipo.\n\nUsá /mis_portafolios para verlo.",
                token,
            )
            return True

        # Eliminar wizard del mismo tipo que quedó incompleto
        supabase.table("portafolios").delete().eq("usuario_id", user_id).eq("tipo", tipo).neq("estado_wizard", "activo").execute()

        result = supabase.table("portafolios").insert({
            "usuario_id": user_id,
            "tipo": tipo,
            "estado_wizard": "configurando_objetivo",
            "activo": False,
        }).execute()

        if not result.data:
            await _answer_callback(callback_id, token)
            return True

        portafolio_id = result.data[0]["id"]
        await _answer_callback(callback_id, token)
        emoji = _TIPO_EMOJI[tipo]
        desc = _TIPO_DESCRIPCION[tipo]
        await _edit_message(
            chat_id, message_id,
            f"{emoji} *Portafolio {tipo.capitalize()}*\n_{desc}_",
            token,
        )
        await _ask_objetivo(chat_id, token)
        return True

    # ── Plazo (botón) ──
    if parts[0] == "wiz_plazo" and len(parts) == 3:
        portafolio_id = int(parts[1])
        valor = parts[2]

        portafolio = _get_portafolio_wizard(supabase, portafolio_id, user_id)
        if not portafolio:
            await _answer_callback(callback_id, token)
            return True

        supabase.table("portafolios").update({
            "plazo": valor,
            "estado_wizard": "configurando_capital",
        }).eq("id", portafolio_id).execute()

        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, f"📅 Plazo: *{valor}*", token)
        await _ask_capital(chat_id, token)
        return True

    # ── Renta mensual máxima (botón) ──
    if parts[0] == "wiz_renta_max" and len(parts) == 2:
        portafolio_id = int(parts[1])

        portafolio = _get_portafolio_wizard(supabase, portafolio_id, user_id)
        if not portafolio:
            await _answer_callback(callback_id, token)
            return True

        supabase.table("portafolios").update({
            "renta_mensual_obj": "max",
            "estado_wizard": "configurando_capital",
        }).eq("id", portafolio_id).execute()

        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "📈 Renta mensual: *máximo posible*", token)
        await _ask_capital(chat_id, token)
        return True

    # ── % Renta fija (botón) ──
    if parts[0] == "wiz_rf_pct" and len(parts) == 3:
        portafolio_id = int(parts[1])
        pct = int(parts[2])

        portafolio = _get_portafolio_wizard(supabase, portafolio_id, user_id)
        if not portafolio:
            await _answer_callback(callback_id, token)
            return True

        supabase.table("portafolios").update({
            "asignacion_rf_pct": pct,
        }).eq("id", portafolio_id).execute()
        portafolio["asignacion_rf_pct"] = pct

        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, f"⚖️ Renta fija: *{pct}%* · Renta variable: *{100 - pct}%*", token)
        await _finalizar_nombre(chat_id, token, portafolio)
        return True

    # ── Confirmar nombre sugerido por Claude ──
    if parts[0] == "wiz_nombre_ok" and len(parts) == 2:
        portafolio_id = int(parts[1])

        portafolio = _get_portafolio_wizard(supabase, portafolio_id, user_id, estado="configurando_nombre")
        if not portafolio:
            await _answer_callback(callback_id, token)
            return True

        nombre = portafolio.get("nombre_sugerido") or portafolio.get("tipo", "Portafolio").capitalize()
        await _activar_portafolio(portafolio_id, None)

        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, f"✅ *{nombre}*", token)
        await _send_portafolio_creado(chat_id, token, portafolio, nombre)
        return True

    return False


# ─── Texto del wizard ──────────────────────────────────────────────────────

async def handle_wizard_text(
    text: str,
    user_id: str,
    chat_id: int,
    token: str,
) -> bool:
    """
    Procesa texto cuando el usuario está en medio de un wizard de portafolio.
    Retorna True si el texto fue consumido por el wizard.
    """
    supabase = get_supabase()

    result = (
        supabase.table("portafolios")
        .select("*")
        .eq("usuario_id", user_id)
        .neq("estado_wizard", "activo")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return False

    portafolio = result.data[0]
    estado = portafolio["estado_wizard"]
    portafolio_id = portafolio["id"]

    # ── Objetivo libre ──
    if estado == "configurando_objetivo":
        objetivo = text.strip()[:50]
        supabase.table("portafolios").update({"objetivo": objetivo}).eq("id", portafolio_id).execute()
        portafolio["objetivo"] = objetivo
        await _next_step_after_objetivo(portafolio, chat_id, token, supabase)
        return True

    # ── Renta mensual (pasivo) ──
    if estado == "configurando_renta":
        supabase.table("portafolios").update({
            "renta_mensual_obj": text.strip(),
            "estado_wizard": "configurando_capital",
        }).eq("id", portafolio_id).execute()
        await _ask_capital(chat_id, token)
        return True

    # ── Capital en USD ──
    if estado == "configurando_capital":
        m = re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
        if not m:
            await _send(chat_id, "No entendí el monto 🤔 Escribí un número en USD, ej: _5000_", token)
            return True
        capital = float(m.group().replace(",", "."))
        supabase.table("portafolios").update({
            "capital_usd": capital,
            "estado_wizard": "configurando_rf_pct",
        }).eq("id", portafolio_id).execute()
        portafolio["capital_usd"] = capital
        await _ask_rf_pct(chat_id, token, portafolio_id, portafolio["tipo"])
        return True

    # ── Nombre personalizado ──
    if estado == "configurando_nombre":
        nombre = text.strip()[:100]
        await _activar_portafolio(portafolio_id, nombre)
        await _send_portafolio_creado(chat_id, token, portafolio, nombre)
        return True

    # ── Estados que solo aceptan botones ──
    if estado in _ESTADOS_SOLO_BOTONES:
        await _send(chat_id, "📋 Usá los botones del mensaje anterior para continuar.", token, parse_mode="")
        return True

    return False


# ─── Utilidades ───────────────────────────────────────────────────────────

def _get_portafolio_wizard(supabase, portafolio_id: int, user_id: str, estado: str | None = None) -> dict | None:
    q = supabase.table("portafolios").select("*").eq("id", portafolio_id).eq("usuario_id", user_id)
    if estado:
        q = q.eq("estado_wizard", estado)
    result = q.limit(1).execute()
    return result.data[0] if result.data else None


async def _next_step_after_objetivo(portafolio: dict, chat_id: int, token: str, supabase) -> None:
    tipo = portafolio["tipo"]
    portafolio_id = portafolio["id"]

    if tipo == "pasivo":
        supabase.table("portafolios").update({"estado_wizard": "configurando_renta"}).eq("id", portafolio_id).execute()
        await _ask_renta_mensual(chat_id, token, portafolio_id)
    elif tipo in ("conservador", "crecimiento"):
        supabase.table("portafolios").update({"estado_wizard": "configurando_plazo"}).eq("id", portafolio_id).execute()
        await _ask_plazo(chat_id, token, portafolio_id, tipo)
    else:  # oportunista
        supabase.table("portafolios").update({"estado_wizard": "configurando_capital"}).eq("id", portafolio_id).execute()
        await _ask_capital(chat_id, token)
