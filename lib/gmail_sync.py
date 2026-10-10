"""
Auto-registro de gastos vía mail de aviso de Santander (Fase 1, IMAP + Gmail app password).

Cada usuario tiene credenciales en `usuario_gmail_config`. Por cada mail nuevo del
remitente de Santander: identifica el tipo, lo parsea, y lo rutea al mismo flujo de
confirmación de Telegram que ya existe para gastos tipeados a mano. Nunca registra
nada en silencio. Dedup por Message-ID en `email_procesados`.

El mail de transferencia (TIPO_TRANSFERENCIA) no se carga como gasto: va a la tabla
`transferencias` y el bot pregunta qué se pagó con ella (ver lib/transferencias.py).

Nunca loguear monto, descripción ni body crudo del mail (regla de AGENTS.md) — solo
contadores/tipos/usuario_id.
"""
import email
import imaplib
import logging
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header

from lib.supabase_client import get_supabase
from lib.tarjetas import calcular_mes_resumen, mes_resumen_tarjeta
from lib.email_parser_santander import (
    identificar_tipo_email, parse_email,
    TIPO_DEBITO_AUTOMATICO, TIPO_PAGO_1_PAGO, TIPO_PAGO_CUOTAS, TIPO_PAGO_DEBITO, TIPO_TRANSFERENCIA,
)
from api.bot.tg import _send
from lib.cotizacion import get_dolar, campos_usd
from lib.email_parser_naranja import (
    NARANJA_SENDER, TIPO_NARANJA_COMPRA, identificar_tipo_email_naranja, parse_email_naranja,
)
from email.utils import parsedate_to_datetime
from api.bot.keyboards import _cuota_fecha_keyboard
from api.bot.helpers import _categorize
from api.bot.handlers.movimientos import _save_and_confirm
from api.bot.handlers.tarjetas import get_tarjetas_activas
from api.bot.callbacks.movimiento_callbacks import finalizar_pago_tarjeta_unico

logger = logging.getLogger("gmail_sync")

IMAP_HOST = "imap.gmail.com"
SANTANDER_SENDER = "mensajesyavisos@mails.santander.com.ar"
_DIAS_VENTANA_BUSQUEDA = 5  # ventana mínima: cubre mails leídos manualmente sin depender de \Seen
_DIAS_MARGEN_ULTIMO_SYNC = 1  # se relee desde 1 día antes de la última corrida completa
_DIAS_VENTANA_MAXIMA = 60  # tope si el cron estuvo caído mucho tiempo
_MESES_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _imap_since_date(d: date) -> str:
    """Formatea una fecha para el criterio SINCE de IMAP ('DD-Mon-YYYY', en inglés, locale-independiente)."""
    return f"{d.day:02d}-{_MESES_IMAP[d.month - 1]}-{d.year}"


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="ignore"))
            except LookupError:  # ej. "unknown-8bit"
                out.append(text.decode("utf-8", errors="ignore"))
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


def _tarjeta_por_nombre(usuario_id: str, nombre: str) -> int | None:
    r = (
        get_supabase().table("tarjetas").select("id")
        .eq("usuario_id", usuario_id).eq("activa", True).ilike("nombre", f"%{nombre}%")
        .limit(1).execute()
    )
    return r.data[0]["id"] if r.data else None


def _ya_cargado(usuario_id: str, tarjeta_id: int, mes_resumen: str, monto: float) -> dict | None:
    """Fila cargada a mano / desde el Excel para la misma tarjeta y resumen con casi el mismo
    monto (±1,5%), que todavía no se cruzó con un mail. Evita duplicar débitos y compras."""
    r = (
        get_supabase().table("movimientos").select("id, descripcion, monto")
        .eq("usuario_id", usuario_id).eq("tarjeta_id", tarjeta_id).eq("mes_resumen", mes_resumen)
        .eq("tipo", "gasto").neq("estado", "anulado").in_("origen", ["excel", "telegram"])
        .is_("cuota_plan_id", "null").execute()
    ).data or []
    tol = max(1.0, monto * 0.015)
    cand = [m for m in r if abs(float(m["monto"]) - monto) <= tol]
    return min(cand, key=lambda m: abs(float(m["monto"]) - monto)) if cand else None


def _plan_ya_cargado(usuario_id: str, tarjeta_id: int, num_cuotas: int, monto_total: float) -> dict | None:
    r = (
        get_supabase().table("cuotas_plan").select("id, descripcion, monto_total")
        .eq("usuario_id", usuario_id).eq("tarjeta_id", tarjeta_id).eq("num_cuotas", num_cuotas)
        .eq("activo", True).execute()
    ).data or []
    tol = max(1.0, monto_total * 0.015)
    cand = [p for p in r if abs(float(p["monto_total"]) - monto_total) <= tol]
    return cand[0] if cand else None


async def _procesar_parsed(usuario_id: str, tipo: str, parsed: dict, token: str) -> tuple[bool, int | None, int | None]:
    """
    Rutea un mail ya parseado al flujo correspondiente.
    Retorna (listo_para_marcar_procesado, movimiento_id, cuota_plan_id).
    listo_para_marcar_procesado=False → reintentar en el próximo poll (tarjeta sin resolver o sin tipo de cambio).
    """
    chat_id = int(usuario_id)
    supabase = get_supabase()

    # TIPO_DEBITO_AUTOMATICO = débito automático EN TARJETA DE CRÉDITO (ej. Netflix,
    # Apple — ver docstring del módulo). Va con el resto de compras de crédito en 1
    # pago, no con TIPO_PAGO_DEBITO (tarjeta de débito real, que sí es efectivo).
    # Naranja: 1 pago se trata como compra en 1 pago; N cuotas, como compra en cuotas
    if tipo == TIPO_NARANJA_COMPRA:
        tipo = TIPO_PAGO_CUOTAS if parsed.get("num_cuotas", 1) > 1 else TIPO_PAGO_1_PAGO

    if tipo in (TIPO_PAGO_1_PAGO, TIPO_PAGO_CUOTAS, TIPO_DEBITO_AUTOMATICO):
        if parsed.get("tarjeta_nombre"):
            tarjeta_id = _tarjeta_por_nombre(usuario_id, parsed["tarjeta_nombre"])
            if tarjeta_id is None:
                return False, None, None
        else:
            tarjeta_id = await _resolver_tarjeta_last4(usuario_id, parsed["last4"], token)
            if tarjeta_id is None:
                return False, None, None

        hoy = date.fromisoformat(parsed["fecha"])
        tar_r = supabase.table("tarjetas").select("dia_cierre").eq("id", tarjeta_id).single().execute()
        dia_cierre = tar_r.data["dia_cierre"] if tar_r.data else None
        mes_resumen = mes_resumen_tarjeta(tarjeta_id, hoy, dia_cierre)
        categoria_id = await _categorize(parsed["descripcion"], usuario_id)

        # Compras / débitos automáticos en dólares (ej. "Monto U$S 20,00"):
        # se guardan en pesos al dólar BCRA, con el monto original en USD.
        usd: dict = {}
        if parsed.get("moneda") == "USD":
            tasa = await get_dolar()
            if not tasa:
                return False, None, None  # reintentar en el próximo poll
            usd = campos_usd(parsed["monto"], tasa)

        if tipo in (TIPO_PAGO_1_PAGO, TIPO_DEBITO_AUTOMATICO):
            monto_ars = float(usd.get("monto", parsed["monto"]))
            previo = _ya_cargado(usuario_id, tarjeta_id, mes_resumen, monto_ars)
            if previo:
                # ya estaba cargado (Excel / a mano): se completa con el dato real, sin duplicar
                supabase.table("movimientos").update({
                    "monto": monto_ars, "fecha": parsed["fecha"], "origen": "excel+email", "estimado": False,
                    **{k: v for k, v in usd.items() if k != "monto"},
                }).eq("id", previo["id"]).execute()
                return True, previo["id"], None
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
                "debito_automatico": tipo == TIPO_DEBITO_AUTOMATICO,
                **usd,
            }).execute()
            mov_id = ins.data[0]["id"] if ins.data else None
            if not mov_id:
                return False, None, None
            await finalizar_pago_tarjeta_unico(
                supabase, usuario_id, mov_id, chat_id=chat_id, token=token, forzar_categoria=True,
            )
            return True, mov_id, None

        # TIPO_PAGO_CUOTAS — el monto del mail es el total de la compra
        num_cuotas = parsed["num_cuotas"]
        monto_total = usd.get("monto", parsed["monto"])
        plan_previo = _plan_ya_cargado(usuario_id, tarjeta_id, num_cuotas, float(monto_total))
        if plan_previo:
            await _send(
                chat_id,
                f"💳 *{parsed['descripcion']}* en {num_cuotas} cuotas: ya la tenías cargada como "
                f"*{plan_previo['descripcion']}*, no la cargo de nuevo.",
                token,
            )
            return True, None, plan_previo["id"]
        monto_cuota = round(monto_total / num_cuotas, 2)
        ins = supabase.table("cuotas_plan").insert({
            "usuario_id": usuario_id,
            "descripcion": parsed["descripcion"],
            "moneda": parsed.get("moneda", "ARS"),
            "monto_total": monto_total,
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

    if tipo == TIPO_TRANSFERENCIA:
        # No es un gasto todavía: queda en `transferencias` y el bot pregunta qué se
        # pagó con ella (tarjeta, préstamo, alquiler), si fue un gasto o un pase propio.
        from lib import transferencias as trf_lib
        trf = trf_lib.registrar(
            usuario_id, parsed["monto"], parsed.get("fecha") or date.today().isoformat(),
            parsed.get("destinatario"), parsed.get("cbu"),
        )
        if not trf:
            return False, None, None
        if token:
            await _send(chat_id, trf_lib.texto_pregunta(trf), token,
                        reply_markup=trf_lib.teclado(usuario_id, trf))
        return True, None, None

    # TIPO_PAGO_DEBITO — tarjeta de débito real: sale directo de la cuenta, se
    # registra como efectivo (no tiene resumen mensual ni tarjeta asociada).
    monto = parsed["monto"]
    descripcion = parsed["descripcion"]
    extra: dict | None = None
    if parsed["moneda"] == "USD":
        tasa = await get_dolar()
        if not tasa:
            return False, None, None
        extra = campos_usd(monto, tasa)
        monto = extra["monto"]

    monto_bajo = monto < 1000 and not extra
    movement_id = await _save_and_confirm(
        chat_id=chat_id, token=token, user_id=usuario_id,
        descripcion=descripcion, monto=monto, tipo="gasto",
        estado="pendiente_confirmacion" if monto_bajo else "confirmado",
        nota_monto_bajo=monto_bajo, fecha=parsed["fecha"], extra=extra,
    )
    return True, movement_id, None


_HORAS_ENTRE_AVISOS_LOGIN = 12


async def _avisar_fallo_login(usuario_id: str, token: str) -> None:
    """
    Avisa por Telegram que el login IMAP falló (ej. app password de Gmail
    vencida/revocada) — antes esto quedaba silencioso. Debounced a 1 aviso
    cada _HORAS_ENTRE_AVISOS_LOGIN para no spamear en cada corrida del cron.
    """
    if not token:
        return
    supabase = get_supabase()
    cfg_r = (
        supabase.table("usuario_gmail_config")
        .select("ultimo_aviso_error_at")
        .eq("usuario_id", usuario_id)
        .single()
        .execute()
    )
    if not cfg_r.data:
        return
    ultimo = cfg_r.data.get("ultimo_aviso_error_at")
    if ultimo:
        try:
            ultimo_dt = datetime.fromisoformat(ultimo.replace("Z", "+00:00"))
            if ultimo_dt.tzinfo is None:
                ultimo_dt = ultimo_dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - ultimo_dt) < timedelta(hours=_HORAS_ENTRE_AVISOS_LOGIN):
                return
        except ValueError:
            pass

    supabase.table("usuario_gmail_config").update(
        {"ultimo_aviso_error_at": datetime.now(timezone.utc).isoformat()}
    ).eq("usuario_id", usuario_id).execute()

    await _send(
        int(usuario_id),
        "⚠️ No pude conectarme a tu Gmail para leer los avisos de Santander y Naranja — "
        "probablemente venció o se revocó la contraseña de aplicación. "
        "Generá una nueva en myaccount.google.com/apppasswords y actualizala "
        "para que vuelva a detectar tus compras y transferencias automáticamente.",
        token,
    )


_MAX_DETALLE_ERRORES = 5


def _parse_ts(valor) -> datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def calcular_desde(hoy: date, ultimo_sync_at, desde_forzado: date | None = None) -> date:
    """
    Fecha SINCE de la búsqueda IMAP. Antes era fija (hoy − 5 días): si el cron se caía más
    de 5 días, los mails de ese hueco no se leían nunca. Ahora arranca desde la última corrida
    completa (− 1 día de margen), nunca menos de 5 días ni más de 60. `desde_forzado` (backfill
    manual con ?desde=YYYY-MM-DD) manda sobre todo lo demás.
    """
    if desde_forzado:
        return desde_forzado
    minimo = hoy - timedelta(days=_DIAS_VENTANA_BUSQUEDA)
    ultimo = _parse_ts(ultimo_sync_at)
    if not ultimo:
        return minimo
    desde = ultimo.date() - timedelta(days=_DIAS_MARGEN_ULTIMO_SYNC)
    return max(min(desde, minimo), hoy - timedelta(days=_DIAS_VENTANA_MAXIMA))


def _fecha_mail(msg: email.message.Message) -> datetime | None:
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def sync_gmail_for_user(
    usuario_id: str, gmail_email: str, gmail_app_password: str, token: str,
    ultimo_sync_at=None, desde_forzado: date | None = None,
) -> dict:
    """Procesa los avisos de Santander y Naranja de un usuario. Aísla fallos por mail."""
    supabase = get_supabase()
    inicio = datetime.now(timezone.utc)
    stats = {"vistos": 0, "procesados": 0, "pendientes_tarjeta": 0, "ignorados": 0, "errores": 0, "errores_detalle": []}
    # Fecha del mail más viejo que quedó sin procesar (pendiente o con error): la próxima
    # corrida tiene que volver a buscar desde ahí, así que no se avanza la marca más allá.
    mas_viejo_sin_procesar: datetime | None = None

    def _anotar_sin_procesar(dt: datetime | None) -> None:
        nonlocal mas_viejo_sin_procesar
        dt = dt or inicio
        if mas_viejo_sin_procesar is None or dt < mas_viejo_sin_procesar:
            mas_viejo_sin_procesar = dt

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST)
        imap.login(gmail_email, gmail_app_password)
    except Exception:
        logger.warning("gmail_sync: fallo de login IMAP para usuario_id=%s", usuario_id)
        stats["errores"] += 1
        await _avisar_fallo_login(usuario_id, token)
        return stats

    try:
        imap.select("INBOX")
        fecha_desde = calcular_desde(date.today(), ultimo_sync_at, desde_forzado)
        stats["desde"] = fecha_desde.isoformat()
        desde = _imap_since_date(fecha_desde)
        # No filtramos por UNSEEN: un mail leído manualmente (preview de Gmail, celular, etc.)
        # no debe perderse — el dedup real es por Message-ID en email_procesados.
        a_procesar: list[tuple[bytes, str]] = []
        for sender, banco in ((SANTANDER_SENDER, "santander"), (NARANJA_SENDER, "naranja")):
            status, data = imap.search(None, "SINCE", desde, f'FROM "{sender}"')
            if status == "OK" and data and data[0]:
                a_procesar.extend((num, banco) for num in data[0].split())

        # Con la ventana más larga hay más mails por corrida: se trae la lista de Message-ID ya
        # procesados una sola vez y solo se baja el cuerpo completo de los mails nuevos.
        procesados_r = (
            supabase.table("email_procesados").select("message_id")
            .eq("usuario_id", usuario_id).gte("procesado_at", (fecha_desde - timedelta(days=2)).isoformat())
            .execute()
        )
        ya_procesados = {r["message_id"] for r in (procesados_r.data or [])}

        for num, banco in a_procesar:
            stats["vistos"] += 1
            tipo = None
            fecha_dt = None
            try:
                status, hdr_data = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE)])")
                if status != "OK" or not hdr_data or not hdr_data[0]:
                    continue
                hdr = email.message_from_bytes(hdr_data[0][1])
                message_id = (hdr.get("Message-ID") or "").strip()
                if not message_id:
                    continue
                fecha_dt = _fecha_mail(hdr)
                if message_id in ya_procesados:
                    continue

                status, msg_data = imap.fetch(num, "(BODY.PEEK[])")
                if status != "OK" or not msg_data or not msg_data[0]:
                    _anotar_sin_procesar(fecha_dt)
                    continue
                msg = email.message_from_bytes(msg_data[0][1])

                subject = _decode_header_value(msg.get("Subject"))
                body = _extract_body(msg)

                if banco == "naranja":
                    try:
                        fecha_mail = parsedate_to_datetime(msg.get("Date")).date()
                    except Exception:
                        fecha_mail = date.today()
                    tipo = identificar_tipo_email_naranja(subject, body)
                    parsed = parse_email_naranja(subject, body, fecha_mail) if tipo else None
                else:
                    tipo = identificar_tipo_email(subject, body)
                    parsed = parse_email(tipo, subject, body) if tipo else None
                    if parsed and not parsed.get("fecha"):
                        # la transferencia no trae fecha en el cuerpo: la del mail
                        try:
                            parsed["fecha"] = parsedate_to_datetime(msg.get("Date")).date().isoformat()
                        except Exception:
                            parsed["fecha"] = date.today().isoformat()

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
                    _anotar_sin_procesar(fecha_dt)
                    continue

                supabase.table("email_procesados").insert({
                    "usuario_id": usuario_id, "message_id": message_id, "tipo_detectado": tipo,
                    "movimiento_id": movimiento_id, "cuota_plan_id": cuota_plan_id,
                }).execute()
                imap.store(num, "+FLAGS", "\\Seen")
                stats["procesados"] += 1
            except Exception as e:
                # Nunca incluir el mensaje de la excepción: puede traer monto/descripción/body
                # (ej. un error de Supabase al insertar incluye el payload). Solo tipo + clase.
                logger.warning(
                    "gmail_sync: error procesando mail tipo=%s (%s) para usuario_id=%s",
                    tipo, type(e).__name__, usuario_id,
                )
                stats["errores"] += 1
                _anotar_sin_procesar(fecha_dt)
                if len(stats["errores_detalle"]) < _MAX_DETALLE_ERRORES:
                    stats["errores_detalle"].append(f"tipo={tipo} exc={type(e).__name__}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    # La corrida terminó: la próxima arranca desde acá (o desde el mail más viejo que quedó
    # sin procesar). Un backfill manual no mueve la marca.
    if not desde_forzado:
        marca = min(inicio, mas_viejo_sin_procesar) if mas_viejo_sin_procesar else inicio
        try:
            supabase.table("usuario_gmail_config").update(
                {"ultimo_sync_at": marca.isoformat()}
            ).eq("usuario_id", usuario_id).execute()
        except Exception as e:
            logger.warning("gmail_sync: no pude guardar ultimo_sync_at (%s) usuario_id=%s", type(e).__name__, usuario_id)

    return stats


async def sync_gmail_all_users(token: str = "", desde_forzado: date | None = None) -> dict:
    """Entry point del cron: itera todos los usuarios con Gmail configurado y activo."""
    import os
    if not token:
        token = os.getenv("TELEGRAM_TOKEN", "")

    supabase = get_supabase()
    rows = supabase.table("usuario_gmail_config").select("*").eq("activo", True).execute()

    total = {"usuarios": 0, "vistos": 0, "procesados": 0, "pendientes_tarjeta": 0, "ignorados": 0, "errores": 0, "errores_detalle": []}
    for cfg in (rows.data or []):
        usuario_id = str(cfg["usuario_id"])
        try:
            stats = await sync_gmail_for_user(
                usuario_id, cfg["gmail_email"], cfg["gmail_app_password"], token,
                ultimo_sync_at=cfg.get("ultimo_sync_at"), desde_forzado=desde_forzado,
            )
            total["usuarios"] += 1
            total.setdefault("desde", stats.get("desde"))
            for k in ("vistos", "procesados", "pendientes_tarjeta", "ignorados", "errores"):
                total[k] += stats.get(k, 0)
            if len(total["errores_detalle"]) < _MAX_DETALLE_ERRORES:
                total["errores_detalle"].extend(stats.get("errores_detalle", []))
        except Exception as e:
            logger.warning("gmail_sync: fallo no aislado (%s) para usuario_id=%s", type(e).__name__, usuario_id)
            total["errores"] += 1
            if len(total["errores_detalle"]) < _MAX_DETALLE_ERRORES:
                total["errores_detalle"].append(f"fallo_no_aislado exc={type(e).__name__}")

    return total
