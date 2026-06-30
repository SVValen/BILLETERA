import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import calendar
from datetime import date, timedelta
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
    ], [
        {"text": "✏️ Editar monto", "callback_data": f"recurrente_editar:{rec_id}"},
    ]]}


async def _procesar_recurrentes(hoy: date, token: str) -> int:
    """Envía recordatorios de recurrentes que corresponden a hoy."""
    supabase = get_supabase()
    rows = (
        supabase.table("recurrentes")
        .select("*")
        .eq("dia_del_mes", hoy.day)
        .eq("activo", True)
        .execute()
    )
    enviados = 0
    for r in (rows.data or []):
        # Atomic claim: solo actualiza si no fue procesado hoy; previene duplicados en retries
        claim = (
            supabase.table("recurrentes")
            .update({"ultimo_recordatorio": hoy.isoformat()})
            .eq("id", r["id"])
            .or_(f"ultimo_recordatorio.is.null,ultimo_recordatorio.lt.{hoy.isoformat()}")
            .execute()
        )
        if not claim.data:
            continue  # Otro proceso ya procesó este recurrente hoy
        chat_id = int(r["usuario_id"])
        sufijo = {1: "ro", 2: "do", 3: "ro"}.get(hoy.day, "to")
        try:
            await _send_telegram(
                chat_id,
                f"🔁 Recordatorio del {hoy.day}{sufijo} del mes:\n"
                f"*{r['descripcion']}* — ${r['monto']:,.0f}\n¿Lo registro hoy?",
                token,
                reply_markup=_recurrente_keyboard(r["id"]),
            )
            enviados += 1
        except Exception:
            pass  # No cortar el loop si falla un envío individual
    return enviados


async def _enviar_resumen_semanal(hoy: date, token: str) -> int:
    """Los lunes: resumen de la semana pasada. Usa 2 queries en total (no N+1)."""
    supabase = get_supabase()
    inicio = hoy - timedelta(days=7)
    fin = hoy - timedelta(days=1)

    perfiles = supabase.table("perfiles").select("telegram_id").execute()
    uids = [p["telegram_id"] for p in (perfiles.data or []) if p.get("telegram_id")]
    if not uids:
        return 0

    # Una sola query para todos los usuarios en lugar de N queries
    movs = (
        supabase.table("movimientos")
        .select("usuario_id, monto, tipo, categorias(nombre, emoji)")
        .in_("usuario_id", uids)
        .neq("estado", "anulado")
        .gte("fecha", inicio.isoformat())
        .lte("fecha", fin.isoformat())
        .execute()
    )

    # Agrupar por usuario en Python
    movs_por_uid: dict[str, list] = {uid: [] for uid in uids}
    for m in (movs.data or []):
        uid = m["usuario_id"]
        if uid in movs_por_uid:
            movs_por_uid[uid].append(m)

    enviados = 0
    for uid in uids:
        rows = movs_por_uid[uid]
        if not rows:
            continue

        gastos = sum(r["monto"] for r in rows if r["tipo"] == "gasto")
        ingresos = sum(r["monto"] for r in rows if r["tipo"] == "ingreso")

        por_cat: dict = {}
        for r in rows:
            if r["tipo"] != "gasto":
                continue
            cat = r.get("categorias") or {}
            nombre = cat.get("nombre", "Otros")
            emoji = cat.get("emoji", "📌")
            por_cat.setdefault(nombre, {"emoji": emoji, "monto": 0})
            por_cat[nombre]["monto"] += r["monto"]

        top = sorted(por_cat.items(), key=lambda x: x[1]["monto"], reverse=True)[:5]
        lines = [f"📊 *Resumen {inicio.strftime('%d/%m')}–{fin.strftime('%d/%m')}*\n"]
        for nombre, d in top:
            lines.append(f"{d['emoji']} {nombre}: ${d['monto']:,.0f}")
        lines += [
            "",
            f"💸 Gastos: *${gastos:,.0f}*",
            f"💵 Ingresos: *${ingresos:,.0f}*",
            f"{'✅' if ingresos >= gastos else '📉'} Saldo: *${ingresos - gastos:,.0f}*",
        ]

        await _send_telegram(int(uid), "\n".join(lines), token)
        enviados += 1

    return enviados


@app.get("/api/cron")
async def cron_job(request: Request):
    cron_secret = os.environ.get("CRON_SECRET", "")
    auth = request.headers.get("authorization", "")
    if not cron_secret or auth != f"Bearer {cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token:
        return JSONResponse({"error": "no token"}, status_code=500)

    hoy = date.today()
    rec_enviados = await _procesar_recurrentes(hoy, token)

    resumen_enviados = 0
    if hoy.weekday() == 0:  # Lunes
        resumen_enviados = await _enviar_resumen_semanal(hoy, token)

    return JSONResponse({
        "ok": True,
        "fecha": hoy.isoformat(),
        "lunes": hoy.weekday() == 0,
        "recordatorios": rec_enviados,
        "resumenes_semanales": resumen_enviados,
    })
