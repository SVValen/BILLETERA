"""
Auto-registro de gastos vía mail de aviso de Santander (Fase 1, IMAP + Gmail app password).

Cada usuario tiene credenciales en `usuario_gmail_config`. Por cada mail nuevo del
remitente de Santander: identifica el tipo, lo parsea, y lo rutea al mismo flujo de
confirmación de Telegram que ya existe para gastos tipeados a mano. Nunca registra
nada en silencio. Dedup por Message-ID en `email_procesados`.

Nunca loguear monto, descripción ni body crudo del mail (regla de AGENTS.md) — solo
contadores/tipos/usuario_id.
"""
import email
import imaplib
import logging
from datetime import date
from email.header import decode_header

from lib.supabase_client import get_supabase
from lib.tarjetas import calcular_mes_resumen
from lib.email_parser_santander import (
    identificar_tipo_email, parse_email,
    TIPO_DEBITO_AUTOMATICO, TIPO_PAGO_1_PAGO, TIPO_PAGO_CUOTAS, TIPO_PAGO_DEBITO,
)
from api.bot.tg import _send, _get_dolar_oficial
from api.bot.keyboards import _cuota_fecha_keyboard
from api.bot.helpers import _categorize
from api.bot.handlers.movimientos import _save_and_confirm
from api.bot.handlers.tarjetas import get_tarjetas_activas
from api.bot.callbacks.movimiento_callbacks import finalizar_pago_tarjeta_unico

logger = logging.getLogger("gmail_sync")

IMAP_HOST = "imap.gmail.com"
SANTANDER_SENDER = "mensajesyavisos@mails.santander.com.ar"


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            out.append(text.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(text)
    return "".join(out)


def _extract_body(msg: email.message.Message) -> str:
    """Prioriza text/plain; si no hay, extrae texto del HTML."""
    plain, html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and plain is None:
                plain = part.get_payload(decode=True)
            elif ctype == "text/html" and html is None:
                html = part.get_payload(decode=True)
    else:
        if msg.get_content_type() == "text/plain":
            plain = msg.get_payload(decode=True)
        else:
            html = msg.get_payload(decode=True)

    charset = msg.get_content_charset() or "utf-8"

    if plain:
        return plain.decode(charset, errors="ignore")
    if html:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html.decode(charset, errors="ignore"), "html.parser").get_text()
    return ""


async def _resolver_tarjeta_last4(usuario_id: str, last4: str, token: str) -> int | None:
    """
    Retorna el tarjeta_id mapeado. Si no hay mapeo, crea uno pendiente y pregunta por
    Telegram (retorna None). Si ya hay un mapeo pendiente, no vuelve a preguntar (retorna None).
    """
    supabase = get_supabase()
    r = (
        supabase.table("tarjeta_last4_map")
        .select("id, tarjeta_id")
        .eq("usuario_id", usuario_id)
        .eq("last4", last4)
        .limit(1)
        .execute()
    )
    if r.data:
        return r.data[0]["tarjeta_id"]

    tarjetas = get_tarjetas_activas(usuario_id)
    if not tarjetas:
        return None

    ins = supabase.table("tarjeta_last4_map").insert({
        "usuario_id": usuario_id, "last4": last4, "tarjeta_id": None,
    }).execute()
    map_id = ins.data[0]["id"] if ins.data else None
    if map_id and token:
        buttons = [
            [{"text": f"💳 {t['nombre']}", "callback_data": f"last4_tar:{map_id}:{t['id']}"}]
            for t in tarjetas
        ]
        await _send(
            int(usuario_id),
            f"🆕 Detecté un movimiento con una tarjeta terminada en *{last4}* que no reconozco — ¿cuál es?",
            token,
            reply_markup={"inline_keyboard": buttons},
        )
    return None


async def _procesar_parsed(usuario_id: str, tipo: str, parsed: dict, token: str) -> tuple[bool, int | None, int | None]:
    """
    Rutea un mail ya parseado al flujo correspondiente.
    Retorna (listo_para_marcar_procesado, movimiento_id, cuota_plan_id).
    listo_para_marcar_procesado=False → reintentar en el próximo poll (tarjeta sin resolver o sin tipo de cambio).
    """
    chat_id = int(usuario_id)
    supabase = get_supabase()

    if tipo in (TIPO_PAGO_1_PAGO, TIPO_PAGO_CUOTAS):
        tarjeta_id = await _resolver_tarjeta_last4(usuario_id, parsed["last4"], token)
        if tarjeta_id is None:
            return False, None, None

        hoy = date.fromisoformat(parsed["fecha"])
        tar_r = supabase.table("tarjetas").select("dia_cierre").eq("id", tarjeta_id).single().execute()
        dia_cierre = tar_r.data["dia_cierre"] if tar_r.data else None
        mes_resumen = calcular_mes_resumen(hoy, dia_cierre) if dia_cierre else hoy.strftime("%Y-%m")
        categoria_id = await _categorize(parsed["descripcion"], usuario_id)

        if tipo == TIPO_PAGO_1_PAGO:
            ins = supabase.table("movimientos").insert({
                "usuario_id": usuario_id,
                "fecha": parsed["fecha"],
                "fecha_compra": parsed["fecha"],
                "descripcion": parsed["descripcion"],
                "monto": parsed["monto"],
                "categoria_id": categoria_id,
                "tipo": "gasto",
                "origen": "email",
                "estado": "pendiente_tarjeta",
                "tarjeta_id": tarjeta_id,
                "mes_resumen": mes_resumen,
            }).execute()
            mov_id = ins.data[0]["id"] if ins.data else None
            if not mov_id:
                return False, None, None
            await finalizar_pago_tarjeta_unico(supabase, usuario_id, mov_id, chat_id=chat_id, token=token)
            return True, mov_id, None

        # TIPO_PAGO_CUOTAS — el monto del mail es el total de la compra
        num_cuotas = parsed["num_cuotas"]
        monto_cuota = round(parsed["monto"] / num_cuotas, 2)
        ins = supabase.table("cuotas_plan").insert({
            "usuario_id": usuario_id,
            "descripcion": parsed["descripcion"],
            "monto_total": parsed["monto"],
            "monto_cuota": monto_cuota,
            "num_cuotas": num_cuotas,
            "cuota_inicio": 1,
            "categoria_id": categoria_id,
            "tarjeta_id": tarjeta_id,
        }).execute()
        plan_id = ins.data[0]["id"] if ins.data else None
        if not plan_id:
            return False, None, None
        await _send(
            chat_id,
            f"💳 *{parsed['descripcion']}* en {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n¿Primera cuota?",
            token,
            reply_markup=_cuota_fecha_keyboard(plan_id),
        )
        return True, None, plan_id

    # TIPO_DEBITO_AUTOMATICO / TIPO_PAGO_DEBITO — todo lo que no es tarjeta de crédito se registra como efectivo
    monto = parsed["monto"]
    descripcion = parsed["descripcion"]
    if parsed["moneda"] == "USD":
        tasa = await _get_dolar_oficial()
        if not tasa:
            return False, None, None
        descripcion = f"{descripcion} (USD {monto:,.0f} @ ${tasa:,.0f} oficial)"
        monto = round(monto * tasa)

    monto_bajo = monto < 1000
    movement_id = await _save_and_confirm(
        chat_id=chat_id, token=token, user_id=usuario_id,
        descripcion=descripcion, monto=monto, tipo="gasto",
        estado="pendiente_confirmacion" if monto_bajo else "confirmado",
        nota_monto_bajo=monto_bajo, fecha=parsed["fecha"],
    )
    return True, movement_id, None


async def sync_gmail_for_user(usuario_id: str, gmail_email: str, gmail_app_password: str, token: str) -> dict:
    """Procesa los mails no leídos de Santander de un usuario. Aísla fallos por mail."""
    supabase = get_supabase()
    stats = {"vistos": 0, "procesados": 0, "pendientes_tarjeta": 0, "ignorados": 0, "errores": 0}

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST)
        imap.login(gmail_email, gmail_app_password)
    except Exception:
        logger.warning("gmail_sync: fallo de login IMAP para usuario_id=%s", usuario_id)
        stats["errores"] += 1
        return stats

    try:
        imap.select("INBOX")
        status, data = imap.search(None, "UNSEEN", f'FROM "{SANTANDER_SENDER}"')
        if status != "OK":
            return stats

        msg_nums = data[0].split()
        for num in msg_nums:
            stats["vistos"] += 1
            try:
                status, msg_data = imap.fetch(num, "(BODY.PEEK[])")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                message_id = msg.get("Message-ID", "").strip()
                if not message_id:
                    continue

                ya_procesado = (
                    supabase.table("email_procesados")
                    .select("id")
                    .eq("usuario_id", usuario_id)
                    .eq("message_id", message_id)
                    .limit(1)
                    .execute()
                )
                if ya_procesado.data:
                    imap.store(num, "+FLAGS", "\\Seen")
                    continue

                subject = _decode_header_value(msg.get("Subject"))
                body = _extract_body(msg)

                tipo = identificar_tipo_email(subject, body)
                parsed = parse_email(tipo, subject, body) if tipo else None

                if not tipo or not parsed:
                    supabase.table("email_procesados").insert({
                        "usuario_id": usuario_id, "message_id": message_id, "tipo_detectado": tipo,
                    }).execute()
                    imap.store(num, "+FLAGS", "\\Seen")
                    stats["ignorados"] += 1
                    continue

                listo, movimiento_id, cuota_plan_id = await _procesar_parsed(usuario_id, tipo, parsed, token)
                if not listo:
                    # Tarjeta sin resolver o sin tipo de cambio disponible: reintentar en el próximo poll
                    stats["pendientes_tarjeta"] += 1
                    continue

                supabase.table("email_procesados").insert({
                    "usuario_id": usuario_id, "message_id": message_id, "tipo_detectado": tipo,
                    "movimiento_id": movimiento_id, "cuota_plan_id": cuota_plan_id,
                }).execute()
                imap.store(num, "+FLAGS", "\\Seen")
                stats["procesados"] += 1
            except Exception:
                logger.warning("gmail_sync: error procesando un mail para usuario_id=%s", usuario_id)
                stats["errores"] += 1
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return stats


async def sync_gmail_all_users(token: str = "") -> dict:
    """Entry point del cron: itera todos los usuarios con Gmail configurado y activo."""
    import os
    if not token:
        token = os.getenv("TELEGRAM_TOKEN", "")

    supabase = get_supabase()
    rows = supabase.table("usuario_gmail_config").select("*").eq("activo", True).execute()

    total = {"usuarios": 0, "vistos": 0, "procesados": 0, "pendientes_tarjeta": 0, "ignorados": 0, "errores": 0}
    for cfg in (rows.data or []):
        usuario_id = str(cfg["usuario_id"])
        try:
            stats = await sync_gmail_for_user(usuario_id, cfg["gmail_email"], cfg["gmail_app_password"], token)
            total["usuarios"] += 1
            for k in ("vistos", "procesados", "pendientes_tarjeta", "ignorados", "errores"):
                total[k] += stats.get(k, 0)
        except Exception:
            logger.warning("gmail_sync: fallo no aislado para usuario_id=%s", usuario_id)
            total["errores"] += 1

    return total
