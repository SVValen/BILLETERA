import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase

app = FastAPI()


async def _send_telegram(chat_id: int, text: str, token: str, reply_markup: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)


def _recurrente_keyboard(rec_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✓ Sí, registrar", "callback_data": f"recurrente_si:{rec_id}"},
        {"text": "✗ No hoy", "callback_data": f"recurrente_no:{rec_id}"},
    ]]}


@app.get("/api/cron")
async def cron_job(request: Request):
    # Verificar secret de Vercel cron
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret:
        auth_header = request.headers.get("authorization", "")
        if auth_header != f"Bearer {cron_secret}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token:
        return JSONResponse({"error": "no token"}, status_code=500)

    hoy = date.today()
    dia_hoy = hoy.day
    supabase = get_supabase()

    # Buscar recurrentes que corresponden a hoy y que no fueron recordados hoy
    recurrentes = (
        supabase.table("recurrentes")
        .select("*")
        .eq("dia_del_mes", dia_hoy)
        .eq("activo", True)
        .execute()
    )

    enviados = 0
    for r in (recurrentes.data or []):
        ultimo = r.get("ultimo_recordatorio")
        if ultimo and ultimo >= hoy.isoformat():
            continue  # Ya se procesó hoy

        chat_id = int(r["usuario_id"])
        sufijo = {1: "ro", 2: "do", 3: "ro"}.get(dia_hoy, "to")
        await _send_telegram(
            chat_id,
            f"🔁 Recordatorio del {dia_hoy}{sufijo} del mes:\n"
            f"*{r['descripcion']}* — ${r['monto']:,.0f}\n"
            f"¿Lo registro hoy?",
            token,
            reply_markup=_recurrente_keyboard(r["id"]),
        )
        enviados += 1

    return JSONResponse({"ok": True, "dia": dia_hoy, "recordatorios_enviados": enviados})
