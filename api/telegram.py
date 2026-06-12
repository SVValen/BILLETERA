import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import calendar
from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.parser import (
    parse_movement, categorize_from_keywords,
    parse_recurrente, parse_cuotas, strip_recurrente, strip_cuotas,
)

app = FastAPI()

AYUDA = (
    "💡 *Cómo registrar:*\n\n"
    "*Gastos* — monto primero:\n"
    "  `5000 comida`\n"
    "  `gasté 3000 en nafta`\n\n"
    "*Ingresos* — palabra primero:\n"
    "  `sueldo 80000`\n"
    "  `ingreso 50000 freelance`\n\n"
    "*Dólares* — agregá 'dólares' o 'USD':\n"
    "  `100 dolares supermercado`\n\n"
    "*Recurrentes* — recordatorio mensual:\n"
    "  `40000 internet todos los 1 del mes`\n\n"
    "*Cuotas* — compra en cuotas:\n"
    "  `15000 zapatillas 12 cuotas`\n\n"
    "🎤 *También podés mandar un audio.*\n\n"
    "📋 *Comandos:*\n"
    "  /id — Tu Telegram ID\n"
    "  /recurrentes — Ver gastos recurrentes\n"
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


def _cuota_fecha_keyboard(plan_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "📅 Este mes", "callback_data": f"cuota_fecha:{plan_id}:0"},
        {"text": "📅 Próximo mes", "callback_data": f"cuota_fecha:{plan_id}:1"},
    ]]}


def _recurrente_keyboard(rec_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✓ Sí, registrar", "callback_data": f"recurrente_si:{rec_id}"},
        {"text": "✗ No hoy", "callback_data": f"recurrente_no:{rec_id}"},
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
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://dolarapi.com/v1/dolares/oficial")
            if r.status_code == 200:
                return float(r.json()["venta"])
    except Exception:
        pass
    return None


# ── Helpers de fecha ──────────────────────────────────────────────────────────

def _add_months(d: date, months: int) -> date:
    """Suma N meses a una fecha, ajustando el día si el mes destino es más corto."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


# ── Lógica de cuotas ──────────────────────────────────────────────────────────

async def _create_cuota_movimientos(plan_id: int, primer_fecha: date, token: str) -> None:
    supabase = get_supabase()
    plan = supabase.table("cuotas_plan").select("*").eq("id", plan_id).single().execute()
    if not plan.data:
        return
    p = plan.data

    movimientos = [
        {
            "usuario_id": p["usuario_id"],
            "fecha": _add_months(primer_fecha, i).isoformat(),
            "descripcion": f"{p['descripcion']} (cuota {i + 1}/{p['num_cuotas']})",
            "monto": p["monto_cuota"],
            "categoria_id": p["categoria_id"],
            "tipo": "gasto",
            "origen": "telegram",
            "estado": "confirmado",
        }
        for i in range(p["num_cuotas"])
    ]
    supabase.table("movimientos").insert(movimientos).execute()
    supabase.table("cuotas_plan").update(
        {"fecha_primera_cuota": primer_fecha.isoformat(), "activo": True}
    ).eq("id", plan_id).execute()

    chat_id = int(p["usuario_id"])
    ultima = _add_months(primer_fecha, p["num_cuotas"] - 1)
    await _send(
        chat_id,
        f"✅ *{p['descripcion']}* en {p['num_cuotas']} cuotas\n"
        f"💳 ${p['monto_cuota']:,.0f}/mes · primera: {primer_fecha.strftime('%d/%m/%Y')}\n"
        f"📆 Última cuota: {ultima.strftime('%m/%Y')}",
        token,
    )


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
    fecha: str | None = None,
) -> None:
    if tipo == "ingreso":
        categoria_id = 17
    else:
        categoria_id = categorize_from_keywords(descripcion)

    supabase = get_supabase()
    result = supabase.table("movimientos").insert({
        "usuario_id": user_id,
        "fecha": fecha or date.today().isoformat(),
        "descripcion": descripcion,
        "monto": monto,
        "categoria_id": categoria_id,
        "tipo": tipo,
        "origen": "telegram",
        "estado": estado,
    }).execute()

    movement_id = result.data[0]["id"] if result.data else None

    if nota_monto_bajo and movement_id:
        await _send(
            chat_id,
            f"🤔 Registré *${monto:,.0f}* — ¿está bien o querías decir *${monto * 1000:,.0f}*?",
            token,
            reply_markup=_monto_keyboard(movement_id, monto),
        )
        return

    if categoria_id == 7 and tipo == "gasto" and movement_id:
        await _send(
            chat_id,
            f"📌 Guardé *${monto:,.0f}* — ¿en qué categoría va *{descripcion}*?",
            token,
            reply_markup=_category_keyboard(movement_id),
        )
        return

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
    # ── Detección especial ──
    dia_mes = parse_recurrente(text)
    num_cuotas = parse_cuotas(text)

    # Limpiar el texto antes de parsear monto/descripción
    if dia_mes:
        clean = strip_recurrente(text)
    elif num_cuotas:
        clean = strip_cuotas(text)
    else:
        clean = text

    parsed = parse_movement(clean) or (parse_movement(text) if clean != text else None)
    if not parsed:
        await _send(chat_id, "No entendí 🤔\n\n" + AYUDA, token)
        return

    monto = parsed["monto"]
    descripcion = parsed["descripcion"]
    tipo = parsed["tipo"]

    # ── Gasto recurrente ──────────────────────────────────────────────────────
    if dia_mes and tipo == "gasto":
        categoria_id = categorize_from_keywords(descripcion)
        supabase = get_supabase()
        result = supabase.table("recurrentes").insert({
            "usuario_id": user_id,
            "descripcion": descripcion,
            "monto": monto,
            "categoria_id": categoria_id,
            "tipo": tipo,
            "dia_del_mes": dia_mes,
            "activo": True,
        }).execute()
        rec_id = result.data[0]["id"] if result.data else "?"
        sufijo = {1: "ro", 2: "do", 3: "ro"}.get(dia_mes, "to")
        await _send(
            chat_id,
            f"🔁 Recordatorio configurado:\n"
            f"*{descripcion}* — ${monto:,.0f} — todos los *{dia_mes}{sufijo}* del mes\n\n"
            f"Voy a preguntarte cada mes si querés registrarlo.",
            token,
        )
        return

    # ── Compra en cuotas ──────────────────────────────────────────────────────
    if num_cuotas and tipo == "gasto":
        monto_cuota = round(monto / num_cuotas, 2)
        categoria_id = categorize_from_keywords(descripcion)
        supabase = get_supabase()
        result = supabase.table("cuotas_plan").insert({
            "usuario_id": user_id,
            "descripcion": descripcion,
            "monto_total": monto,
            "monto_cuota": monto_cuota,
            "num_cuotas": num_cuotas,
            "categoria_id": categoria_id,
        }).execute()
        plan_id = result.data[0]["id"] if result.data else None
        if not plan_id:
            await _send(chat_id, "Error guardando el plan de cuotas 😕", token, parse_mode="")
            return
        await _send(
            chat_id,
            f"💳 *{descripcion}* en {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n"
            f"¿Cuándo se paga la primera cuota?",
            token,
            reply_markup=_cuota_fecha_keyboard(plan_id),
        )
        return

    # ── Flujo normal ──────────────────────────────────────────────────────────
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

    # ── Callbacks de botones ──────────────────────────────────────────────────
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
                        await _send(chat_id, f"¿En qué categoría va *{descripcion}*?", token,
                                    reply_markup=_category_keyboard(movement_id))
                    else:
                        await _edit_message(
                            chat_id, message_id,
                            f"✅ Guardado: -${nuevo_monto:,.0f} · {cat.get('emoji','📌')} {cat.get('nombre','?')}",
                            token,
                        )

        # Primera cuota: este mes o próximo
        elif parts[0] == "cuota_fecha" and len(parts) == 3:
            plan_id = int(parts[1])
            proximo = int(parts[2])  # 0 = este mes, 1 = próximo mes
            hoy = date.today()
            primer_fecha = _first_of_month(_add_months(hoy, proximo))
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"📅 Primera cuota: {primer_fecha.strftime('%d/%m/%Y')} — creando movimientos...", token)
                await _create_cuota_movimientos(plan_id, primer_fecha, token)

        # Recordatorio recurrente — confirmar registro
        elif parts[0] == "recurrente_si" and len(parts) == 2:
            rec_id = int(parts[1])
            rec = supabase.table("recurrentes").select("*").eq("id", rec_id).single().execute()
            if rec.data:
                r = rec.data
                supabase.table("movimientos").insert({
                    "usuario_id": r["usuario_id"],
                    "fecha": date.today().isoformat(),
                    "descripcion": r["descripcion"],
                    "monto": r["monto"],
                    "categoria_id": r["categoria_id"],
                    "tipo": r["tipo"],
                    "origen": "telegram",
                    "estado": "confirmado",
                }).execute()
                supabase.table("recurrentes").update(
                    {"ultimo_recordatorio": date.today().isoformat()}
                ).eq("id", rec_id).execute()
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id,
                        f"✅ Registrado: -{r['descripcion']} ${r['monto']:,.0f}", token)

        # Recordatorio recurrente — saltar hoy
        elif parts[0] == "recurrente_no" and len(parts) == 2:
            rec_id = int(parts[1])
            supabase.table("recurrentes").update(
                {"ultimo_recordatorio": date.today().isoformat()}
            ).eq("id", rec_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id, "⏭ Saltado por hoy.", token)

        return JSONResponse({"ok": True})

    # ── Mensajes ──────────────────────────────────────────────────────────────
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
        return JSONResponse({"ok": True})

    if token:
        await _process_text(text, user_id, chat_id, token)

    return JSONResponse({"ok": True})
