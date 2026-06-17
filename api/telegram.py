import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from api.bot.dispatcher import dispatch_callback, dispatch_message

app = FastAPI()


@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return JSONResponse({"error": "TELEGRAM_WEBHOOK_SECRET no configurado"}, status_code=500)
    if request.headers.get("x-telegram-bot-api-secret-token", "") != webhook_secret:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    data = await request.json()
    token = os.environ.get("TELEGRAM_TOKEN", "")

    if "callback_query" in data:
        await dispatch_callback(data["callback_query"], token)
        return JSONResponse({"ok": True})

    if "message" in data:
        await dispatch_message(data["message"], token)

    return JSONResponse({"ok": True})
