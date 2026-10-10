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


async def _preguntar_cierres(hoy: date, token: str) -> int:
    """Desde el 25, pregunta la fecha de cierre de las tarjetas que cierran en días variables."""
    from lib.tarjetas import cierres_a_preguntar, marcar_preguntado, mes_label
    from api.bot.handlers.tarjetas import teclado_cierre
    enviados = 0
    for t in cierres_a_preguntar(hoy):
        try:
            await _send_telegram(
                int(t["usuario_id"]),
                f"📅 ¿Cuándo cierra *{t['nombre']}* el resumen que pagás en {mes_label(t['mes_resumen'])}?\n"
                "_Con eso ubico bien cada compra en su resumen. También podés escribir `/cierre "
                f"{t['nombre'].lower()} 30/10`._",
                token, reply_markup=teclado_cierre(t["id"], t["mes_resumen"]),
            )
            marcar_preguntado(t["id"], t["mes_resumen"])
            enviados += 1
        except Exception:
            pass
    return enviados


async def _ajustes_ipc(token: str) -> int:
    """Calcula el ajuste por IPC del alquiler cuando ya están los datos, y avisa."""
    from lib import alquiler as alq
    contratos = get_supabase().table("alquiler_contrato").select("usuario_id").eq("activo", True).execute()
    aplicados = 0
    for c in (contratos.data or []):
        aj = await alq.actualizar_ajuste_ipc(c["usuario_id"])
        if not aj:
            continue
        aplicados += 1
        try:
            await _send_telegram(
                int(c["usuario_id"]),
                f"🏠 *Ajuste del alquiler desde {aj['mes']}*\n\n"
                f"${aj['monto_anterior']:,.0f} → *${aj['monto']:,.0f}* ({aj['variacion'] * 100:+.2f}%)\n"
                f"_{aj['detalle']}_\n\nYa actualicé los alquileres de ese período.",
                token,
            )
        except Exception:
            pass
    return aplicados


def _asegurar_alquileres(hoy: date) -> int:
    """Crea como pendientes los conceptos de alquiler del mes en curso y del próximo."""
    from lib import alquiler as alq
    contratos = get_supabase().table("alquiler_contrato").select("usuario_id").eq("activo", True).execute()
    mes = hoy.strftime("%Y-%m")
    creados = 0
    for c in (contratos.data or []):
        for m in (mes, alq.sumar_meses(mes, 1)):
            creados += len(alq.asegurar_mes(c["usuario_id"], m))
    return creados


@app.get("/api/cron")
async def cron_job(request: Request, job: str = "", desde: str = ""):
    cron_secret = os.environ.get("CRON_SECRET", "")
    auth = request.headers.get("authorization", "")
    if not cron_secret or auth != f"Bearer {cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token:
        return JSONResponse({"error": "no token"}, status_code=500)

    # ?job=gmail_sync → lee los mails de aviso (Santander, Naranja) y registra los gastos
    # ?job=gmail_sync&desde=YYYY-MM-DD → backfill manual desde esa fecha (no mueve la marca)
    if job == "gmail_sync":
        from lib.gmail_sync import sync_gmail_all_users
        desde_forzado = None
        if desde:
            try:
                desde_forzado = date.fromisoformat(desde)
            except ValueError:
                return JSONResponse({"error": "desde inválido, usar YYYY-MM-DD"}, status_code=400)
        stats = await sync_gmail_all_users(token=token, desde_forzado=desde_forzado)
        return JSONResponse({"ok": True, **stats})

    hoy = date.today()
    from lib.cotizacion import actualizar_cotizacion
    dolar_bcra = await actualizar_cotizacion()
    rec_enviados = await _procesar_recurrentes(hoy, token)
    alquiler_creados = _asegurar_alquileres(hoy)
    ajustes = await _ajustes_ipc(token)
    cierres = await _preguntar_cierres(hoy, token)

    return JSONResponse({
        "ok": True,
        "fecha": hoy.isoformat(),
        "recordatorios": rec_enviados,
        "alquiler_conceptos_creados": alquiler_creados,
        "dolar_bcra": dolar_bcra,
        "ajustes_ipc": ajustes,
        "cierres_preguntados": cierres,
    })
