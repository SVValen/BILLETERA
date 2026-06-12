import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.parser import parse_movement, categorize_from_keywords

app = FastAPI()


@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return JSONResponse({"ok": True})

    message = data["message"]
    text = message.get("text", "").strip()
    user_id = str(message["from"]["id"])

    if not text:
        return JSONResponse({"ok": True, "message": "Mensaje vacío"})

    parsed = parse_movement(text)
    if not parsed:
        return JSONResponse({
            "ok": False,
            "message": (
                "No entendí 🤔\n"
                "Usá alguno de estos formatos:\n"
                "• Gasté 25000 en supermercado\n"
                "• Ingreso 50000 sueldo\n"
                "• 10000 transporte"
            )
        })

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

    # Enviar respuesta al chat de Telegram
    telegram_token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = message["chat"]["id"]
    if telegram_token:
        import httpx
        await httpx.AsyncClient().post(
            f"https://api.telegram.org/bot{telegram_token}/sendMessage",
            json={"chat_id": chat_id, "text": respuesta},
        )

    return JSONResponse({"ok": True, "message": respuesta})
