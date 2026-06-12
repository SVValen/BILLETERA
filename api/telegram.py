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
    "🎤 *También podés mandar un audio:*\n"
    '  _"gasté cinco mil en el super"_\n\n'
    "📋 *Comandos:*\n"
    "  /id — Tu Telegram ID (para el dashboard)\n"
    "  /ayuda — Esta ayuda"
)

CAT_BUTTONS = [
    (1,  "🛒 Super"),    (3,  "🍽️ Comida"),  (2,  "🚗 Trans."),  (4,  "💡 Servicios"),
    (5,  "🎬 Entret."),  (6,  "🏥 Salud"),   (8,  "👕 Ropa"),    (10, "🏠 Vivienda"),
    (9,  "📚 Educ."),    (11, "🐾 Mascotas"), (12, "✈️ Viajes"),  (13, "🛡️ Seguros"),
    (14, "💰 Invers."),  (15, "💳 Compras"),  (16, "✨ Belleza"), (7,  "📌 Otros"),
]


def _category_keyboard(movement_id: int) -> dict:
    rows = []
    for i in range(0, len(CAT_BUTTONS), 4):
        row = [
            {"text": label, "callback_data": f"cat:{movement_id}:{cat_id}"}
            for cat_id, label in CAT_BUTTONS[i:i + 4]
        ]
        rows.append(row)
    return {"inline_keyboard": rows}


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


async def _transcribe_voice(file_id: str, token: str) -> str | None:
    """Descarga el audio de Telegram y lo transcribe con Groq Whisper (gratis)."""
    import httpx

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return None

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Obtener path del archivo en los servidores de Telegram
        r = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
        )
        if r.status_code != 200:
            return None
        file_path = r.json()["result"]["file_path"]

        # 2. Descargar el OGG
        r = await client.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}"
        )
        if r.status_code != 200:
            return None
        audio_bytes = r.content

        # 3. Transcribir con Groq Whisper
        r = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {groq_key}"},
            files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
            data={"model": "whisper-large-v3-turbo", "language": "es"},
        )
        if r.status_code != 200:
            return None

        return r.json().get("text", "").strip() or None


async def _process_text(text: str, user_id: str, chat_id: int, token: str) -> None:
    """Lógica compartida entre mensajes de texto y audios transcriptos."""
    parsed = parse_movement(text)
    if not parsed:
        await _send(chat_id, "No entendí 🤔\n\n" + AYUDA, token)
        return

    if parsed["tipo"] == "ingreso":
        categoria_id = 17
    else:
        categoria_id = categorize_from_keywords(parsed["descripcion"])

    supabase = get_supabase()
    result = supabase.table("movimientos").insert({
        "usuario_id": user_id,
        "fecha": date.today().isoformat(),
        "descripcion": parsed["descripcion"],
        "monto": parsed["monto"],
        "categoria_id": categoria_id,
        "tipo": parsed["tipo"],
        "origen": "telegram",
        "estado": "confirmado" if categoria_id != 7 else "pendiente_categoria",
    }).execute()

    movement_id = result.data[0]["id"] if result.data else None

    if categoria_id == 7 and parsed["tipo"] == "gasto" and movement_id:
        await _send(
            chat_id,
            f"📌 Guardé *${parsed['monto']:,.0f}* — ¿en qué categoría va *{parsed['descripcion']}*?",
            token,
            reply_markup=_category_keyboard(movement_id),
        )
        return

    cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", categoria_id).single().execute()
    cat_name = cat_row.data.get("nombre", "Otros") if cat_row.data else "Otros"
    cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"

    signo = "-" if parsed["tipo"] == "gasto" else "+"
    await _send(
        chat_id,
        f"✅ Registrado: {signo}${parsed['monto']:,.0f} · {cat_emoji} {cat_name}",
        token,
        parse_mode="",
    )


@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    token = os.environ.get("TELEGRAM_TOKEN", "")

    # ── Callback de botón inline ──────────────────────────────
    if "callback_query" in data:
        cq = data["callback_query"]
        callback_id = cq["id"]
        payload = cq.get("data", "")
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]

        parts = payload.split(":")
        if parts[0] == "cat" and len(parts) == 3:
            movement_id = int(parts[1])
            cat_id = int(parts[2])

            supabase = get_supabase()
            supabase.table("movimientos").update(
                {"categoria_id": cat_id, "estado": "confirmado"}
            ).eq("id", movement_id).execute()

            cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", cat_id).single().execute()
            cat_name = cat_row.data.get("nombre", "?") if cat_row.data else "?"
            cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"

            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(
                    chat_id, message_id,
                    f"✅ Guardado como {cat_emoji} {cat_name}",
                    token,
                )

        return JSONResponse({"ok": True})

    # ── Mensajes ──────────────────────────────────────────────
    if "message" not in data:
        return JSONResponse({"ok": True})

    message = data["message"]
    user_id = str(message["from"]["id"])
    chat_id = message["chat"]["id"]

    # ── Mensaje de voz 🎤 ──
    if "voice" in message or "audio" in message:
        if not token:
            return JSONResponse({"ok": True})

        file_id = message.get("voice", message.get("audio", {})).get("file_id")
        if not file_id:
            return JSONResponse({"ok": True})

        groq_key = os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            await _send(chat_id, "🎤 Los audios no están configurados aún (falta GROQ_API_KEY).", token)
            return JSONResponse({"ok": True})

        await _send(chat_id, "🎤 Transcribiendo...", token, parse_mode="")
        transcribed = await _transcribe_voice(file_id, token)

        if not transcribed:
            await _send(chat_id, "No pude entender el audio, intentá de nuevo 🙁", token, parse_mode="")
            return JSONResponse({"ok": True})

        await _send(chat_id, f'🗣 _"{transcribed}"_', token)
        await _process_text(transcribed, user_id, chat_id, token)
        return JSONResponse({"ok": True})

    # ── Mensaje de texto ──
    text = message.get("text", "").strip()
    if not text:
        return JSONResponse({"ok": True})

    if text.startswith("/id"):
        if token:
            await _send(chat_id,
                        f"🪪 Tu Telegram ID es: `{user_id}`\n"
                        "Usalo en *Configurar* del dashboard para vincular tu cuenta.",
                        token)
        return JSONResponse({"ok": True})

    if text.lower().startswith(("/ayuda", "/start", "/help")):
        if token:
            await _send(chat_id, AYUDA, token)
        return JSONResponse({"ok": True})

    if token:
        await _process_text(text, user_id, chat_id, token)

    return JSONResponse({"ok": True})
