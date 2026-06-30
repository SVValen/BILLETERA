import os
from datetime import date
from lib.supabase_client import get_supabase
from .tg import _send, _transcribe_voice
from .constants import AYUDA
from .keyboards import _recent_movements_keyboard
from .callbacks.movimiento_callbacks import handle_movimiento_callback
from .callbacks.recomendacion_callbacks import handle_recomendacion_callback
from .handlers.wizard_inversion import handle_wizard_callback, handle_wizard_text, _send_tipo_keyboard
from .handlers.posiciones_rf import handle_rf_callback, _parse_posicion_rf, _handle_nueva_posicion_rf
from .handlers.movimientos import _process_text
from .handlers.presupuestos import _handle_presupuesto_cmd
from .handlers.comandos_inversion import _handle_inversiones_cmd, _handle_precios_cmd, _handle_liquidez_cmd, _handle_portafolio_cmd, _handle_opciones_rf_cmd
from .handlers.plan_renta import handle_plan_renta_text, handle_plan_renta_callback, _ask_capital_plan
from .handlers.aportes import handle_aporte, handle_aporte_callback
from .handlers.activos_rv import handle_rv_callback, handle_activos_cmd
from .handlers.tarjetas import (
    handle_tarjeta_nueva_cmd, handle_tarjetas_cmd, handle_tarjeta_callback,
    handle_pagar_tarjeta_cmd, handle_pagar_tarjeta_callback, handle_pagar_tarjeta_text,
)
from .handlers.colchon import handle_colchon_cmd, handle_colchon_nuevo_cmd, handle_colchon_callback, handle_colchon_text
from .handlers.recurrentes import handle_recurrente_text
from .handlers.prestamos import handle_prestamo_callback, handle_prestamos_cmd, detect_prestamo_text
from .handlers.objetivos import handle_objetivo_nuevo_cmd, handle_objetivos_cmd, handle_objetivo_conectar_cmd, handle_objetivo_callback
from lib.parser import parse_aporte
from .middleware_portafolio import resolver_portafolio, handle_psel_callback


async def dispatch_callback(cq: dict, token: str) -> None:
    callback_id = cq["id"]
    payload = cq.get("data", "")
    chat_id = cq["message"]["chat"]["id"]
    message_id = cq["message"]["message_id"]
    user_id = str(cq["from"]["id"])
    supabase = get_supabase()
    parts = payload.split(":")

    if await handle_movimiento_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_wizard_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_plan_renta_callback(parts, callback_id, chat_id, user_id, token):
        return
    if await handle_recomendacion_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_rf_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_aporte_callback(parts, callback_id, chat_id, message_id, user_id, token):
        return
    if await handle_rv_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_psel_callback(parts, callback_id, chat_id, message_id, user_id, token):
        return
    if await handle_tarjeta_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_pagar_tarjeta_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_colchon_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_prestamo_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_objetivo_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return


async def dispatch_message(message: dict, token: str) -> None:
    user_id = str(message["from"]["id"])
    chat_id = message["chat"]["id"]
    text = ""

    # ── Audio / voz ──
    if "voice" in message or "audio" in message:
        if not token:
            return
        file_id = message.get("voice", message.get("audio", {})).get("file_id")
        if not file_id:
            return
        if not os.environ.get("GROQ_API_KEY"):
            await _send(chat_id, "🎤 Audios no configurados (falta GROQ_API_KEY).", token)
            return
        await _send(chat_id, "🎤 Transcribiendo...", token, parse_mode="")
        transcribed = await _transcribe_voice(file_id, token)
        if not transcribed:
            await _send(chat_id, "No pude entender el audio 🙁", token, parse_mode="")
            return
        await _send(chat_id, f'🗣 _"{transcribed}"_', token)
        # Si el usuario está en un paso de texto del wizard, el audio actúa como texto
        if await handle_wizard_text(transcribed, user_id, chat_id, token):
            return
        if await handle_plan_renta_text(transcribed, user_id, chat_id, token):
            return
        if await handle_colchon_text(transcribed, user_id, chat_id, token):
            return
        if await handle_pagar_tarjeta_text(transcribed, user_id, chat_id, token):
            return
        if await handle_recurrente_text(transcribed, user_id, chat_id, token):
            return
        aporte_parsed = parse_aporte(transcribed)
        if aporte_parsed:
            await handle_aporte(aporte_parsed, user_id, chat_id, token)
            return
        await _process_text(transcribed, user_id, chat_id, token)
        return
    else:
        text = message.get("text", "").strip() if "text" in message else ""

    if not text:
        return

    # ── Wizard: respuestas de texto a pasos del setup ──
    if token and not text.startswith("/"):
        if await handle_wizard_text(text, user_id, chat_id, token):
            return
        if await handle_plan_renta_text(text, user_id, chat_id, token):
            return
        if await handle_colchon_text(text, user_id, chat_id, token):
            return
        if await handle_pagar_tarjeta_text(text, user_id, chat_id, token):
            return
        if await handle_recurrente_text(text, user_id, chat_id, token):
            return
        aporte_parsed = parse_aporte(text)
        if aporte_parsed:
            await handle_aporte(aporte_parsed, user_id, chat_id, token)
            return

    # ── Comandos ──
    if text.startswith("/id"):
        if token:
            await _send(chat_id,
                f"🪪 Tu Telegram ID es: `{user_id}`\n"
                "Usalo en *Configurar* del dashboard para vincular tu cuenta.", token)
        return

    if text.lower().startswith(("/ayuda", "/start", "/help")):
        if token:
            await _send(chat_id, AYUDA, token)
        return

    if text.lower().startswith("/portafolio_nuevo"):
        if token:
            await _send_tipo_keyboard(chat_id, token)
        return

    if text.lower().startswith("/activos"):
        if token:
            await handle_activos_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/tarjeta_nueva"):
        if token:
            await handle_tarjeta_nueva_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/tarjetas"):
        if token:
            await handle_tarjetas_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/pagar_tarjeta"):
        if token:
            await handle_pagar_tarjeta_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/colchon_nuevo"):
        if token:
            await handle_colchon_nuevo_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/colchon"):
        if token:
            await handle_colchon_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/mis_portafolios"):
        if token:
            await _handle_mis_portafolios(user_id, chat_id, token)
        return

    if text.lower().startswith("/inversiones reset"):
        if token:
            supabase = get_supabase()
            deleted = (
                supabase.table("portafolios")
                .delete()
                .eq("usuario_id", user_id)
                .neq("estado_wizard", "activo")
                .execute()
            )
            n = len(deleted.data) if deleted.data else 0
            if n:
                await _send(chat_id, f"🔄 Wizard cancelado ({n} borrador{'s' if n > 1 else ''}). Usá /portafolio_nuevo para empezar.", token)
            else:
                await _send(chat_id, "No hay wizards en progreso.", token, parse_mode="")
        return

    if text.lower().startswith("/inversiones"):
        if token:
            await _handle_inversiones_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/portafolio"):
        if token:
            resultado = await resolver_portafolio(user_id, chat_id, token, accion="portafolio")
            if resultado == "no_portafolios":
                await _send(chat_id, "No tenés portafolios activos. Usá /portafolio_nuevo para crear uno.", token, parse_mode="")
            elif resultado != "selection_sent":
                await _handle_portafolio_cmd(user_id, chat_id, token, portafolio=resultado)
        return

    if text.lower().startswith("/como_funciona"):
        if token:
            await _send(chat_id,
                "🤖 *Cómo funciona el sistema de recomendaciones*\n\n"
                "*1. Actualización de precios* (cada ~30 min)\n"
                "El cron obtiene el precio actual de cada activo de tu portafolio "
                "y calcula dos indicadores técnicos:\n\n"
                "*RSI (Índice de Fuerza Relativa)*\n"
                "Mide si un activo está sobrecomprado o sobrevendido en base a los "
                "últimos 14 períodos de precio:\n"
                "  • RSI < 35 → sobreventa (posible oportunidad de compra)\n"
                "  • RSI > 65 → sobrecompra (posible señal de venta)\n"
                "  • Entre 35 y 65 → neutral, sin señal\n\n"
                "*EMA (Media Móvil Exponencial)*\n"
                "Compara la EMA de 20 períodos con la de 50 para detectar tendencia:\n"
                "  • EMA20 sube → tendencia alcista\n"
                "  • EMA20 baja → tendencia bajista\n"
                "  • Sin cambio → lateral\n\n"
                "*2. Generación de recomendación*\n"
                "Solo cuando hay señal (RSI extremo), Claude analiza el contexto completo:\n"
                "  • Tu perfil de riesgo (conservador/moderado/arriesgado)\n"
                "  • Tus objetivos y plazo\n"
                "  • El winrate de tus decisiones anteriores\n"
                "  • El contexto argentino (inflación, tipo de cambio)\n\n"
                "El resultado es: acción (comprar/vender/mantener) + razón + confianza del 1 al 10.\n\n"
                "*3. Anti-spam*\n"
                "Si ya tenés una recomendación pendiente para un activo, no genera otra hasta que la respondas.\n\n"
                "💡 La confianza baja (1-5) suele significar señal débil o contexto incierto. "
                "Confianza 7+ indica señal más clara.",
                token)
        return

    if text.lower().startswith("/precios"):
        if token:
            await _handle_precios_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/liquidez"):
        if token:
            resultado = await resolver_portafolio(user_id, chat_id, token, accion="liquidez")
            if resultado == "no_portafolios":
                await _send(chat_id, "No tenés portafolios activos. Usá /portafolio_nuevo para crear uno.", token, parse_mode="")
            elif resultado != "selection_sent":
                await _handle_liquidez_cmd(user_id, chat_id, token, portafolio=resultado)
        return

    if text.lower().startswith("/opciones_rf"):
        if token:
            await _handle_opciones_rf_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/plan_renta"):
        if token:
            await _ask_capital_plan(chat_id, token)
            supabase = get_supabase()
            supabase.table("portafolios").insert({
                "usuario_id": user_id,
                "tipo": "conservador",
                "estado_wizard": "pidiendo_capital",
                "activo": False,
            }).execute()
        return

    if text.lower().startswith("/iol_debug"):
        if token:
            from lib.market_data import fetch_iol_debug
            import json as _json
            simbolo = text.split()[-1].upper() if len(text.split()) > 1 else "AAPL"
            await _send(chat_id, f"🔍 Consultando IOL para *{simbolo}*...", token)
            result = await fetch_iol_debug(simbolo)
            txt = _json.dumps(result, indent=2, ensure_ascii=False)
            if len(txt) > 3800:
                txt = txt[:3800] + "\n...(truncado)"
            await _send(chat_id, f"```\n{txt}\n```", token)
        return

    if text.lower().startswith("/recurrentes"):
        if token:
            supabase = get_supabase()
            rows = supabase.table("recurrentes").select("*").eq("usuario_id", user_id).eq("activo", True).execute()
            if not rows.data:
                await _send(chat_id, "No tenés gastos recurrentes configurados.", token, parse_mode="")
            else:
                lines = ["🔁 *Tus gastos recurrentes:*\n"]
                for r in rows.data:
                    lines.append(f"• {r['descripcion']} — ${r['monto']:,.0f} — día {r['dia_del_mes']}")
                await _send(chat_id, "\n".join(lines), token)
        return

    if text.lower().startswith("/editar"):
        if token:
            q = text[len("/editar"):].strip()
            mes_actual = date.today().strftime("%Y-%m")
            if q:
                kb, total = await _recent_movements_keyboard(user_id, "edit", q=q, mes=mes_actual)
                if kb:
                    await _send(chat_id,
                        f"✏️ *{total}* movimiento{'s' if total != 1 else ''} con \"{q}\" en {mes_actual}:",
                        token, reply_markup=kb)
                else:
                    await _send(chat_id, f"No encontré movimientos con \"{q}\" este mes.", token, parse_mode="")
            else:
                kb, _ = await _recent_movements_keyboard(user_id, "edit")
                if kb:
                    await _send(chat_id, "✏️ ¿Qué movimiento querés editar?", token, reply_markup=kb)
                else:
                    await _send(chat_id, "No encontré movimientos recientes.", token, parse_mode="")
        return

    if text.lower().startswith("/borrar"):
        if token:
            q = text[len("/borrar"):].strip()
            mes_actual = date.today().strftime("%Y-%m")
            if q:
                kb, total = await _recent_movements_keyboard(user_id, "del", q=q, mes=mes_actual)
                if kb:
                    await _send(chat_id,
                        f"🗑️ *{total}* movimiento{'s' if total != 1 else ''} con \"{q}\" en {mes_actual}:",
                        token, reply_markup=kb)
                else:
                    await _send(chat_id, f"No encontré movimientos con \"{q}\" este mes.", token, parse_mode="")
            else:
                kb, _ = await _recent_movements_keyboard(user_id, "del")
                if kb:
                    await _send(chat_id, "🗑️ ¿Qué movimiento querés borrar?", token, reply_markup=kb)
                else:
                    await _send(chat_id, "No encontré movimientos recientes.", token, parse_mode="")
        return

    if text.lower().startswith("/presupuesto"):
        if token:
            args = text[len("/presupuesto"):].strip()
            await _handle_presupuesto_cmd(user_id, chat_id, args, token)
        return

    if text.lower().startswith("/prestamos"):
        if token:
            await handle_prestamos_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/objetivo_nuevo"):
        if token:
            await handle_objetivo_nuevo_cmd(text, user_id, chat_id, token)
        return

    if text.lower().startswith("/objetivo_conectar"):
        if token:
            await handle_objetivo_conectar_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/objetivos"):
        if token:
            await handle_objetivos_cmd(user_id, chat_id, token)
        return

    # ── Detección de texto de préstamo por keywords ──
    if token and detect_prestamo_text(text):
        await handle_prestamos_cmd(user_id, chat_id, token)
        return

    # ── Parser de posiciones RF ──
    if token:
        rf_match = _parse_posicion_rf(text)
        if rf_match:
            await _handle_nueva_posicion_rf(rf_match, user_id, chat_id, token)
            return

    # ── Fallback: parsear como movimiento ──
    if token:
        await _process_text(text, user_id, chat_id, token)


async def _handle_mis_portafolios(user_id: str, chat_id: int, token: str) -> None:
    supabase = get_supabase()
    result = (
        supabase.table("portafolios")
        .select("tipo, nombre_personalizado, nombre_sugerido, capital_usd, capital_ars, asignacion_rf_pct, objetivo, plazo, estado_wizard")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .order("id")
        .execute()
    )
    portafolios = result.data or []

    if not portafolios:
        await _send(
            chat_id,
            "No tenés portafolios activos.\n\nUsá /portafolio_nuevo para crear uno.",
            token,
            parse_mode="",
        )
        return

    _TIPO_EMOJI = {"conservador": "🛡️", "pasivo": "💰", "crecimiento": "📈", "oportunista": "🎯"}
    lines = [f"📊 *Tus portafolios* ({len(portafolios)}):\n"]

    for p in portafolios:
        nombre = p.get("nombre_personalizado") or p.get("nombre_sugerido") or p["tipo"].capitalize()
        tipo = p["tipo"]
        emoji = _TIPO_EMOJI.get(tipo, "📊")
        capital_usd = p.get("capital_usd") or 0
        capital_ars = p.get("capital_ars") or 0
        rf_pct = p.get("asignacion_rf_pct") or 0
        objetivo = p.get("objetivo") or "—"
        plazo = p.get("plazo")
        estado = p.get("estado_wizard", "activo")

        cap_parts = []
        if capital_usd:
            cap_parts.append(f"${capital_usd:,.0f} USD")
        if capital_ars:
            cap_parts.append(f"${capital_ars:,.0f} ARS")
        cap_txt = " + ".join(cap_parts) if cap_parts else "sin capital"

        lines.append(f"{emoji} *{nombre}* ({tipo.capitalize()})")
        lines.append(f"   Capital: {cap_txt} | RF: {rf_pct:.0f}%")
        if plazo:
            lines.append(f"   Plazo: {plazo}")
        lines.append(f"   Objetivo: {objetivo}")
        if estado != "activo":
            lines.append(f"   ⚠️ En configuración ({estado})")
        lines.append("")

    lines.append("_Sumá capital: `sumé 500 USD al conservador`_")
    await _send(chat_id, "\n".join(lines).strip(), token)
