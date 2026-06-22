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

_TIPO_RF_RECOMENDADO = {
    "conservador": 75,
    "pasivo": 60,
    "crecimiento": 30,
    "oportunista": 15,
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
    recomendado = _TIPO_RF_RECOMENDADO.get(tipo, 50)
    opciones = [0, 25, 50, 75, 100]

    def _label(p: int) -> str:
        base = f"{p}% RF"
        if abs(p - recomendado) == min(abs(x - recomendado) for x in opciones):
            return f"{base} ✨"
        return base

    buttons = [
        [{"text": _label(p), "callback_data": f"wiz_rf_pct:{portafolio_id}:{p}"}]
        for p in opciones
    ]
    await _send(
        chat_id,
        "⚖️ ¿Qué porcentaje del portafolio querés en *Renta Fija*?\n"
        "(cauciones, letras, bonos, ONs)\n\n"
        f"_✨ = recomendado para perfil {tipo}_",
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

    if rf_pct > 0:
        await _sugerir_instrumentos_rf(chat_id, token, portafolio)

    rv_pct = 100 - rf_pct
    if rv_pct > 0:
        from .activos_rv import sugerir_activos_rv
        await sugerir_activos_rv(chat_id, token, portafolio)

    # Parte B: vincular objetivo si estaba esperando
    usuario_id = portafolio.get("usuario_id")
    portafolio_id_actual = portafolio.get("id")
    supabase_local = get_supabase()
    obj_r = (
        supabase_local.table("objetivos_ahorro")
        .select("id, nombre")
        .eq("usuario_id", str(usuario_id))
        .eq("esperando_portafolio", True)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    if obj_r.data:
        obj = obj_r.data[0]
        supabase_local.table("objetivos_ahorro").update({
            "portafolio_id": portafolio_id_actual,
            "esperando_portafolio": False,
        }).eq("id", obj["id"]).execute()
        await _send(chat_id, f"✅ Portafolio vinculado al objetivo *{obj['nombre']}*.", token)
    else:
        obj_unlinked = (
            supabase_local.table("objetivos_ahorro")
            .select("id")
            .eq("usuario_id", str(usuario_id))
            .eq("activo", True)
            .is_("portafolio_id", "null")
            .eq("esperando_portafolio", False)
            .limit(1)
            .execute()
        )
        if obj_unlinked.data:
            await _send(chat_id, "¿Vinculás este portafolio a un objetivo de ahorro?", token,
                reply_markup={"inline_keyboard": [[
                    {"text": "🎯 Sí, vincular", "callback_data": f"obj_link:{portafolio_id_actual}"},
                    {"text": "❌ No", "callback_data": "obj_nolink"},
                ]]}
            )


async def _sugerir_instrumentos_rf(
    chat_id: int,
    token: str,
    portafolio: dict,
    nuevo_capital_usd: float | None = None,
    nuevo_capital_ars: float | None = None,
    intro_override: str | None = None,
) -> None:
    """
    Sugiere instrumentos RF con botones para registrar posición directamente.
    Se usa al terminar el wizard y después de cada aporte.

    nuevo_capital_usd / nuevo_capital_ars: si se proveen, el mensaje se enfoca
    en ese monto nuevo en lugar del capital total del portafolio.
    """
    from lib.market_data import fetch_dolar_precio
    from lib.rf_analysis import analizar_carry_trade

    supabase = get_supabase()

    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_data["precio"] if dolar_data else None

    # Capital RF a mostrar: preferir el capital nuevo si viene de un aporte
    if nuevo_capital_ars and nuevo_capital_ars > 0:
        capital_rf_ars = nuevo_capital_ars
        capital_rf_usd = nuevo_capital_usd or (nuevo_capital_ars / (dolar_mep or 1200))
    else:
        rf_pct = portafolio.get("asignacion_rf_pct") or 0
        capital_usd = portafolio.get("capital_usd") or 0
        capital_ars = portafolio.get("capital_ars") or 0
        capital_total_usd = capital_usd + (capital_ars / (dolar_mep or 1200) if dolar_mep else 0)
        capital_rf_usd = capital_total_usd * rf_pct / 100
        capital_rf_ars = capital_rf_usd * (dolar_mep or 1200)

    if capital_rf_ars < 5_000:
        return

    # Carry trade
    caucion_r = supabase.table("instrumentos_rf").select("tna_actual").eq("codigo", "CAUCION_7D").limit(1).execute()
    tna_ref = caucion_r.data[0]["tna_actual"] if caucion_r.data and caucion_r.data[0].get("tna_actual") else None
    carry = analizar_carry_trade(tna_ref, dolar_mep, None) if (tna_ref and dolar_mep) else None

    # Prioridad de instrumentos según carry + tipo de portafolio
    tipo = portafolio.get("tipo", "conservador")
    if carry and carry["accion"] == "salir":
        tipos_prioridad = ["bono_soberano", "on", "letra", "caucion"]
    elif carry and carry["accion"] == "entrar":
        tipos_prioridad = ["caucion", "letra", "bono_soberano", "on"]
    elif tipo in ("conservador", "pasivo"):
        tipos_prioridad = ["caucion", "letra", "bono_soberano", "on"]
    else:
        tipos_prioridad = ["bono_soberano", "caucion", "letra", "on"]

    insts_r = (
        supabase.table("instrumentos_rf")
        .select("id, codigo, nombre, tipo, tna_actual, fecha_vencimiento")
        .eq("activo", True)
        .execute()
    )
    instrumentos = insts_r.data or []

    def _sort_key(inst):
        try:
            return tipos_prioridad.index(inst.get("tipo", ""))
        except ValueError:
            return len(tipos_prioridad)

    instrumentos.sort(key=_sort_key)
    top = instrumentos[:3]
    if not top:
        return

    _TIPO_LABEL = {
        "caucion": "liquidez máxima, renovable",
        "letra": "plazo fijo, tasa garantizada",
        "bono_soberano": "en USD, protección cambiaria",
        "on": "deuda corporativa, buen rendimiento",
    }

    # Header
    if intro_override:
        header = intro_override
    else:
        rf_pct = portafolio.get("asignacion_rf_pct") or 0
        header = f"💰 *Renta Fija — {rf_pct:.0f}% de tu portafolio*\nCapital RF: ~${capital_rf_usd:,.0f} USD (${capital_rf_ars:,.0f} ARS aprox)"

    carry_txt = ""
    if carry:
        icon = "🟢" if carry["accion"] == "entrar" else "🔴" if carry["accion"] == "salir" else "🟡"
        carry_txt = f"\n{icon} Carry: {carry['accion'].upper()} ({carry['carry_mensual']:+.1f}%/mes)"

    lines = [header + carry_txt, "\n*Instrumentos sugeridos:*"]

    buttons = []
    for inst in top:
        label = _TIPO_LABEL.get(inst.get("tipo", ""), "")
        tna = inst.get("tna_actual")
        tna_txt = f" · {tna:.1f}% TNA" if tna else ""
        nombre = inst.get("nombre") or inst.get("codigo")
        lines.append(f"• *{nombre}*{tna_txt} — _{label}_")
        buttons.append([{"text": f"📥 Registrar: {nombre}", "callback_data": f"rf_elegir:{inst['id']}"}])

    lines.append("\n_O escribí: `puse 500000 en caución 7 días`_")
    await _send(chat_id, "\n".join(lines), token, reply_markup={"inline_keyboard": buttons})


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

        # Eliminar wizard del mismo tipo que quedó incompleto (solo estados del wizard real,
        # nunca los de plan_renta que también usan tipo='conservador')
        _WIZARD_ESTADOS = (
            "configurando_objetivo", "configurando_renta", "configurando_plazo",
            "configurando_capital", "configurando_rf_pct", "configurando_nombre",
        )
        supabase.table("portafolios").delete().eq("usuario_id", user_id).eq("tipo", tipo).in_("estado_wizard", list(_WIZARD_ESTADOS)).execute()

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
