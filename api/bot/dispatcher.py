import os
from datetime import date
from lib.supabase_client import get_supabase
from .tg import _send, _transcribe_voice
from .constants import AYUDA
from .keyboards import _recent_movements_keyboard
from .callbacks.movimiento_callbacks import handle_movimiento_callback
from .callbacks.recomendacion_callbacks import handle_recomendacion_callback
from .handlers.wizard_inversion import handle_wizard_callback, handle_wizard_text, _send_objetivos_keyboard
from .handlers.posiciones_rf import handle_rf_callback, _parse_posicion_rf, _handle_nueva_posicion_rf
from .handlers.movimientos import _process_text
from .handlers.presupuestos import _handle_presupuesto_cmd
from .handlers.comandos_inversion import _handle_inversiones_cmd, _handle_precios_cmd, _handle_liquidez_cmd, _handle_portafolio_cmd


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
    if await handle_recomendacion_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_rf_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
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
        # Si el usuario está en paso de texto libre del wizard, el audio actúa como texto
        _perfil_estado_r = get_supabase().table("perfiles_inversion").select("estado").eq("usuario_id", user_id).limit(1).execute()
        _estado_inv = _perfil_estado_r.data[0].get("estado") if _perfil_estado_r.data else None
        if _estado_inv in ("configurando_capital", "configurando_descripcion", "configurando_activos"):
            text = transcribed
        else:
            await _process_text(transcribed, user_id, chat_id, token)
            return
    else:
        text = message.get("text", "").strip() if "text" in message else ""

    if not text:
        return

    # ── Wizard: respuestas de texto a pasos del setup ──
    if token and not text.startswith("/"):
        try:
            supabase = get_supabase()
            perfil_check = supabase.table("perfiles_inversion").select("*").eq("usuario_id", user_id).limit(1).execute()
            if await handle_wizard_text(text, user_id, chat_id, token, supabase, perfil_check):
                return
        except Exception:
            pass

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

    if text.lower().startswith("/inversiones reset"):
        if token:
            supabase = get_supabase()
            supabase.table("perfiles_inversion").update({
                "estado": "configurando_objetivos",
                "objetivos": None,
                "objetivo": None,
                "plazo": None,
                "moneda_preferida": None,
                "capital_usd": None,
                "asignacion_rf_pct": None,
                "descripcion": None,
            }).eq("usuario_id", user_id).execute()
            await _send(chat_id, "🔄 Perfil reseteado. Vamos a reconfigurarlo desde cero.")
            await _send_objetivos_keyboard(user_id, chat_id, token, supabase)
        return

    if text.lower().startswith("/inversiones"):
        if token:
            await _handle_inversiones_cmd(user_id, chat_id, token)
        return

    if text.lower().startswith("/portafolio"):
        if token:
            await _handle_portafolio_cmd(user_id, chat_id, token)
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
            await _handle_liquidez_cmd(user_id, chat_id, token)
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

    # ── Parser de posiciones RF ──
    if token:
        rf_match = _parse_posicion_rf(text)
        if rf_match:
            await _handle_nueva_posicion_rf(rf_match, user_id, chat_id, token)
            return

    # ── Fallback: parsear como movimiento ──
    if token:
        await _process_text(text, user_id, chat_id, token)
