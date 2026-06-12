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
    "💡 *Formatos aceptados:*\n"
    "• `Gasté 25000 en supermercado`\n"
    "• `10000 uber`\n"
    "• `Ingreso 50000 sueldo`\n"
    "• `sueldo 80000`\n\n"
    "📋 *Comandos:*\n"
    "• `/id` — Ver tu ID de Telegram (para vincular el dashboard)\n"
    "• `/ayuda` — Ver esta ayuda"
)


async def _send(chat_id: int, text: str, token: str, parse_mode: str = "Markdown") -> None:
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        )


@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return JSONResponse({"ok": True})

    message = data["message"]
    text = message.get("text", "").strip()
    user_id = str(message["from"]["id"])
    chat_id = message["chat"]["id"]
    token = os.environ.get("TELEGRAM_TOKEN", "")

    if not text:
        return JSONResponse({"ok": True})

    # ── Comandos ──
    if text.startswith("/id"):
        respuesta = f"🪪 Tu Telegram ID es: `{user_id}`\nUsalo en la sección *Configurar* del dashboard para vincular tu cuenta."
        if token:
            await _send(chat_id, respuesta, token)
        return JSONResponse({"ok": True})

    if text.startswith("/ayuda") or text.startswith("/start") or text.startswith("/help"):
        if token:
            await _send(chat_id, AYUDA, token)
        return JSONResponse({"ok": True})

    # ── Registrar movimiento ──
    parsed = parse_movement(text)
    if not parsed:
        if token:
            await _send(chat_id, "No entendí 🤔\n\n" + AYUDA, token)
        return JSONResponse({"ok": False})

    categoria_id = categorize_from_keywords(parsed["descripcion"])

    supabase = get_supabase()
    supabase.table("movimientos").insert({
        "usuario_id": user_id,
        "fecha": date.today().isoformat(),
        "descripcion": parsed["descripcion"],
        "monto": parsed["monto"],
        "categoria_id": categoria_id,
        "tipo": parsed["tipo"],
        "origen": "telegram",
        "estado": "confirmado",
    }).execute()

    cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", categoria_id).single().execute()
    cat_name = cat_row.data.get("nombre", "Otros") if cat_row.data else "Otros"
    cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"

    signo = "-" if parsed["tipo"] == "gasto" else "+"
    respuesta = f"✅ Registrado: {signo}${parsed['monto']:,.0f} · {cat_emoji} {cat_name}"

    if token:
        await _send(chat_id, respuesta, token, parse_mode="")

    return JSONResponse({"ok": True, "message": respuesta})
