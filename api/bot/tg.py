import os
import httpx


def _es_error_de_formato(resp: dict) -> bool:
    """Telegram rechaza el mensaje si el Markdown queda mal armado, por ejemplo cuando el
    comercio de un mail del Santander trae un asterisco ("DLO*PedidosYa", "MERPAGO*KIOSKO")."""
    return not resp.get("ok", True) and "parse entities" in str(resp.get("description", "")).lower()


def _sin_markdown(text: str) -> str:
    return text.replace("*", "").replace("_", " ").replace("`", "")


async def _send(chat_id: int, text: str, token: str,
                parse_mode: str = "Markdown", reply_markup: dict | None = None) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json=payload
        )
        try:
            resp = r.json()
        except ValueError:
            return {"ok": False}
        if parse_mode and _es_error_de_formato(resp):
            # Reintento sin formato: mejor un mensaje sin negritas que ningún mensaje
            payload.pop("parse_mode", None)
            payload["text"] = _sin_markdown(text)
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage", json=payload
            )
            try:
                resp = r.json()
            except ValueError:
                return {"ok": False}
        return resp


async def _answer_callback(callback_id: str, token: str, text: str | None = None) -> None:
    payload: dict = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json=payload,
        )


async def _edit_message(chat_id: int, message_id: int, text: str, token: str,
                        parse_mode: str = "Markdown", reply_markup: dict | None = None) -> None:
    import json as _json
    payload: dict = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = _json.dumps(reply_markup)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json=payload,
        )
        try:
            resp = r.json()
        except ValueError:
            return
        if parse_mode and _es_error_de_formato(resp):
            payload.pop("parse_mode", None)
            payload["text"] = _sin_markdown(text)
            await client.post(
                f"https://api.telegram.org/bot{token}/editMessageText",
                json=payload,
            )


async def _transcribe_voice(file_id: str, token: str) -> str | None:
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
    """Dólar para convertir gastos en USD: mayorista BCRA (Com. A 3500), con
    fallback al oficial de dolarapi. Ver lib/cotizacion.py."""
    from lib.cotizacion import get_dolar
    return await get_dolar()
