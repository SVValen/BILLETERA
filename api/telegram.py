import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.parser import parse_movement, categorize_from_keywords

app = FastAPI()

AYUDA = (
    "💡 *Cómo registrar:*\n\n"
    "*Gastos* — monto primero:\n"
    "  `5000 comida`\n"
    "  `1200 uber`\n"
    "  `gasté 3000 en nafta`\n\n"
    "*Ingresos* — palabra primero:\n"
    "  `sueldo 80000`\n"
    "  `ingreso 50000 freelance`\n\n"
    "*Dólares* — agregá 'dólares' o 'USD':\n"
    "  `100 dolares supermercado`\n"
    "  `gasté 50 usd en ropa`\n\n"
    "🎤 *También podés mandar un audio.*\n\n"
    "📋 *Comandos:*\n"
    "  /id — Tu Telegram ID\n"
    "  /ayuda — Esta ayuda"
)

CAT_BUTTONS = [
    (1,  "🛒 Super"),    (3,  "🍽️ Comida"),  (2,  "🚗 Trans."),  (4,  "💡 Servicios"),
    (5,  "🎬 Entret."),  (6,  "🏥 Salud"),   (8,  "👕 Ropa"),    (10, "🏠 Vivienda"),
    (9,  "📚 Educ."),    (11, "🐾 Mascotas"), (12, "✈️ Viajes"),  (13, "🛡️ Seguros"),
    (14, "💰 Invers."),  (15, "💳 Compras"),  (16, "✨ Belleza"), (7,  "📌 Otros"),
]

DOLLAR_KEYWORDS = {"dolar", "dolares", "dólares", "usd", "u$s", "us$", "dólar"}


# ── Helpers de Telegram ───────────────────────────────────────────────────────

def _category_keyboard(movement_id: int) -> dict:
    rows = []
    for i in range(0, len(CAT_BUTTONS), 4):
        row = [
            {"text": label, "callback_data": f"cat:{movement_id}:{cat_id}"}
            for cat_id, label in CAT_BUTTONS[i:i + 4]
        ]
        rows.append(row)
    return {"inline_keyboard": rows}


def _monto_keyboard(movement_id: int, monto: float) -> dict:
    monto_k = int(monto * 1000)
    return {"inline_keyboard": [[
        {"text": f"✓ Son ${monto:,.0f}", "callback_data": f"monto_ok:{movement_id}"},
        {"text": f"× Son ${monto_k:,}", "callback_data": f"monto_x1000:{movement_id}"},
    ]]}


async def _send(chat_id: int, text: str, token: str,
                parse_mode: str = "Markdown", reply_markup: dict | None = None) -> dict:
    import httpx
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json=payload
        )
        return r.json()


async def _answer_callback(callback_id: str, token: str) -> None:
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
        )


async def _edit_message(chat_id: int, message_id: int, text: str, token: str) -> None:
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={"chat_id": chat_id, "message_id": message_id, "text": text},
        )


# ── Servicios externos ────────────────────────────────────────────────────────

async def _transcribe_voice(file_id: str, token: str) -> str | None:
    import httpx
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
        )
        if r.status_code != 200:
            return None
        file_path = r.json()["result"]["file_path"]

        r = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
        if r.status_code != 200:
            return None

        r = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {groq_key}"},
            files={"file": ("audio.ogg", r.content, "audio/ogg")},
            data={"model": "whisper-large-v3-turbo", "language": "es"},
        )
        return r.json().get("text", "").strip() or None if r.status_code == 200 else None


async def _get_dolar_oficial() -> float | None:
    """Obtiene el tipo de cambio oficial de dolarapi.com (gratuito, sin auth)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://dolarapi.com/v1/dolares/oficial")
            if r.status_code == 200:
                return float(r.json()["venta"])
    except Exception:
        pass
    return None


# ── Lógica principal ──────────────────────────────────────────────────────────

def _detect_currency(text: str) -> str:
    words = set(text.lower().split())
    return "USD" if words & DOLLAR_KEYWORDS else "ARS"


async def _save_and_confirm(
    *,
    chat_id: int,
    token: str,
    user_id: str,
    descripcion: str,
    monto: float,
    tipo: str,
    estado: str = "confirmado",
    nota_monto_bajo: bool = False,
) -> None:
    """Guarda el movimiento y envía confirmación o pregunta de categoría/monto."""
    if tipo == "ingreso":
        categoria_id = 17
    else:
        categoria_id = categorize_from_keywords(descripcion)

    supabase = get_supabase()
    result = supabase.table("movimientos").insert({
        "usuario_id": user_id,
        "fecha": date.today().isoformat(),
        "descripcion": descripcion,
        "monto": monto,
        "categoria_id": categoria_id,
        "tipo": tipo,
        "origen": "telegram",
        "estado": estado,
    }).execute()

    movement_id = result.data[0]["id"] if result.data else None

    # Monto sospechosamente bajo: preguntar
    if nota_monto_bajo and movement_id:
        await _send(
            chat_id,
            f"🤔 Registré *${monto:,.0f}* — ¿está bien o querías decir *${monto * 1000:,.0f}*?",
            token,
            reply_markup=_monto_keyboard(movement_id, monto),
        )
        return

    # Sin categoría: preguntar
    if categoria_id == 7 and tipo == "gasto" and movement_id:
        await _send(
            chat_id,
            f"📌 Guardé *${monto:,.0f}* — ¿en qué categoría va *{descripcion}*?",
            token,
            reply_markup=_category_keyboard(movement_id),
        )
        return

    # Confirmación normal
    cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", categoria_id).single().execute()
    cat_name = cat_row.data.get("nombre", "Otros") if cat_row.data else "Otros"
    cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"
    signo = "-" if tipo == "gasto" else "+"
    await _send(
        chat_id,
        f"✅ Registrado: {signo}${monto:,.0f} · {cat_emoji} {cat_name}",
        token,
        parse_mode="",
    )


async def _process_text(text: str, user_id: str, chat_id: int, token: str) -> None:
    parsed = parse_movement(text)
    if not parsed:
        await _send(chat_id, "No entendí 🤔\n\n" + AYUDA, token)
        return

    monto = parsed["monto"]
    descripcion = parsed["descripcion"]
    tipo = parsed["tipo"]

    # ── Detección de moneda ──
    moneda = _detect_currency(text)

    if moneda == "USD":
        tasa = await _get_dolar_oficial()
        if not tasa:
            await _send(chat_id, "No pude obtener el tipo de cambio oficial 😕 Intentá de nuevo.", token, parse_mode="")
            return
        monto_ars = round(monto * tasa)
        descripcion = f"{descripcion} (USD {monto:,.0f} @ ${tasa:,.0f} oficial)"
        await _save_and_confirm(
            chat_id=chat_id, token=token, user_id=user_id,
            descripcion=descripcion, monto=monto_ars, tipo=tipo,
        )
        return

    # ── Monto sospechosamente bajo en ARS (< 1000) ──
    monto_bajo = monto < 1000

    await _save_and_confirm(
        chat_id=chat_id, token=token, user_id=user_id,
        descripcion=descripcion, monto=monto, tipo=tipo,
        estado="pendiente_confirmacion" if monto_bajo else "confirmado",
        nota_monto_bajo=monto_bajo,
    )


# ── Webhook ───────────────────────────────────────────────────────────────────

@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    token = os.environ.get("TELEGRAM_TOKEN", "")

    # ── Callbacks de botones ──────────────────────────────────
    if "callback_query" in data:
        cq = data["callback_query"]
        callback_id = cq["id"]
        payload = cq.get("data", "")
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        supabase = get_supabase()

        parts = payload.split(":")

        # Selección de categoría
        if parts[0] == "cat" and len(parts) == 3:
            movement_id, cat_id = int(parts[1]), int(parts[2])
            supabase.table("movimientos").update(
                {"categoria_id": cat_id, "estado": "confirmado"}
            ).eq("id", movement_id).execute()
            cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", cat_id).single().execute()
            cat_name = cat_row.data.get("nombre", "?") if cat_row.data else "?"
            cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id, f"✅ Guardado como {cat_emoji} {cat_name}", token)

        # Monto confirmado tal cual
        elif parts[0] == "monto_ok" and len(parts) == 2:
            movement_id = int(parts[1])
            supabase.table("movimientos").update({"estado": "confirmado"}).eq("id", movement_id).execute()
            row = supabase.table("movimientos").select("monto, categorias(nombre, emoji)").eq("id", movement_id).single().execute()
            monto = row.data["monto"] if row.data else 0
            cat = (row.data.get("categorias") or {}) if row.data else {}
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(
                    chat_id, message_id,
                    f"✅ Guardado: -${monto:,.0f} · {cat.get('emoji','📌')} {cat.get('nombre','?')}",
                    token,
                )

        # Monto × 1000
        elif parts[0] == "monto_x1000" and len(parts) == 2:
            movement_id = int(parts[1])
            row = supabase.table("movimientos").select("monto, tipo, descripcion, categorias(nombre, emoji)").eq("id", movement_id).single().execute()
            if row.data:
                nuevo_monto = row.data["monto"] * 1000
                tipo = row.data["tipo"]
                descripcion = row.data["descripcion"]
                cat = row.data.get("categorias") or {}

                # Si categoría es Otros, recategorizar con el monto correcto y volver a preguntar categoría
                categoria_id = categorize_from_keywords(descripcion)
                supabase.table("movimientos").update({
                    "monto": nuevo_monto,
                    "categoria_id": categoria_id,
                    "estado": "confirmado" if categoria_id != 7 else "pendiente_categoria",
                }).eq("id", movement_id).execute()

                if token:
                    await _answer_callback(callback_id, token)
                    if categoria_id == 7 and tipo == "gasto":
                        await _edit_message(chat_id, message_id,
                            f"💲 Actualizado a ${nuevo_monto:,.0f} — ¿categoría?", token)
                        # Mandar teclado de categorías como nuevo mensaje
                        await _send(chat_id, f"¿En qué categoría va *{descripcion}*?", token,
                                    reply_markup=_category_keyboard(movement_id))
                    else:
                        await _edit_message(
                            chat_id, message_id,
                            f"✅ Guardado: -${nuevo_monto:,.0f} · {cat.get('emoji','📌')} {cat.get('nombre','?')}",
                            token,
                        )

        return JSONResponse({"ok": True})

    # ── Mensajes ──────────────────────────────────────────────
    if "message" not in data:
        return JSONResponse({"ok": True})

    message = data["message"]
    user_id = str(message["from"]["id"])
    chat_id = message["chat"]["id"]

    # Voz / audio
    if "voice" in message or "audio" in message:
        if not token:
            return JSONResponse({"ok": True})
        file_id = message.get("voice", message.get("audio", {})).get("file_id")
        if not file_id:
            return JSONResponse({"ok": True})
        if not os.environ.get("GROQ_API_KEY"):
            await _send(chat_id, "🎤 Audios no configurados (falta GROQ_API_KEY).", token)
            return JSONResponse({"ok": True})
        await _send(chat_id, "🎤 Transcribiendo...", token, parse_mode="")
        transcribed = await _transcribe_voice(file_id, token)
        if not transcribed:
            await _send(chat_id, "No pude entender el audio, intentá de nuevo 🙁", token, parse_mode="")
            return JSONResponse({"ok": True})
        await _send(chat_id, f'🗣 _"{transcribed}"_', token)
        await _process_text(transcribed, user_id, chat_id, token)
        return JSONResponse({"ok": True})

    # Texto
    text = message.get("text", "").strip()
    if not text:
        return JSONResponse({"ok": True})

    if text.startswith("/id"):
        if token:
            await _send(chat_id,
                        f"🪪 Tu Telegram ID es: `{user_id}`\n"
                        "Usalo en *Configurar* del dashboard para vincular tu cuenta.", token)
        return JSONResponse({"ok": True})

    if text.lower().startswith(("/ayuda", "/start", "/help")):
        if token:
            await _send(chat_id, AYUDA, token)
        return JSONResponse({"ok": True})

    if token:
        await _process_text(text, user_id, chat_id, token)

    return JSONResponse({"ok": True})
