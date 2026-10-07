import os
from datetime import date
from lib.supabase_client import get_supabase
from .tg import _send, _transcribe_voice
from .constants import AYUDA
from .keyboards import _recent_movements_keyboard
from .callbacks.movimiento_callbacks import handle_movimiento_callback
from .handlers.movimientos import _process_text
from .handlers.presupuestos import _handle_presupuesto_cmd
from .handlers.tarjetas import (
    handle_tarjeta_nueva_cmd, handle_tarjetas_cmd, handle_tarjeta_callback,
    handle_pagar_tarjeta_cmd, handle_pagar_tarjeta_callback, handle_pagar_tarjeta_text,
)
from .handlers.recurrentes import handle_recurrente_text
from .handlers.transferencias import handle_transferencia_text
from .handlers.alquiler import handle_alquiler_cmd, handle_alquiler_callback, handle_descuento_text
from .handlers.prestamos import handle_prestamo_callback, handle_prestamos_cmd, detect_prestamo_text


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
    if await handle_tarjeta_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_pagar_tarjeta_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_prestamo_callback(parts, callback_id, chat_id, message_id, user_id, supabase, token):
        return
    if await handle_alquiler_callback(parts, callback_id, chat_id, message_id, user_id, token):
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
        # Si el usuario está respondiendo un paso de texto, el audio actúa como texto
        if await handle_pagar_tarjeta_text(transcribed, user_id, chat_id, token):
            return
        if await handle_recurrente_text(transcribed, user_id, chat_id, token):
            return
        if await handle_transferencia_text(transcribed, user_id, chat_id, token):
            return
        if await handle_descuento_text(transcribed, user_id, chat_id, token):
            return
        await _process_text(transcribed, user_id, chat_id, token)
        return
    else:
        text = message.get("text", "").strip() if "text" in message else ""

    if not text:
        return

    # ── Respuestas de texto a pasos pendientes (pago tarjeta, recurrentes, transferencias) ──
    if token and not text.startswith("/"):
        if await handle_pagar_tarjeta_text(text, user_id, chat_id, token):
            return
        if await handle_recurrente_text(text, user_id, chat_id, token):
            return
        if await handle_transferencia_text(text, user_id, chat_id, token):
            return
        if await handle_descuento_text(text, user_id, chat_id, token):
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

    if text.lower().startswith("/alquiler"):
        if token:
            await handle_alquiler_cmd(text, user_id, chat_id, token)
        return

    if text.lower().startswith("/prestamos"):
        if token:
            await handle_prestamos_cmd(user_id, chat_id, token)
        return

    # ── Detección de texto de préstamo por keywords ──
    if token and detect_prestamo_text(text):
        await handle_prestamos_cmd(user_id, chat_id, token)
        return

    # ── Fallback: parsear como movimiento ──
    if token:
        await _process_text(text, user_id, chat_id, token)

