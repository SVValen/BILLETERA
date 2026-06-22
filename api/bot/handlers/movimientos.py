import re
from datetime import date
from lib.supabase_client import get_supabase
from lib.parser import parse_movement, parse_recurrente, parse_cuotas, parse_cuota_progreso, strip_recurrente, strip_cuotas
from ..tg import _send, _get_dolar_oficial
from ..keyboards import _monto_keyboard, _category_keyboard
from ..helpers import _detect_currency, _categorize, _save_learned_keywords
from ..constants import AYUDA
from .presupuestos import _check_presupuesto_alert
from .recurrentes import _registrar_recurrente
from .cuotas import _registrar_cuota_plan
from .tarjetas import get_tarjetas_activas, pago_keyboard


async def _save_pending_tarjeta(
    *,
    chat_id: int,
    token: str,
    user_id: str,
    descripcion: str,
    monto: float,
    tipo: str,
    tarjetas: list[dict],
    fecha: str | None = None,
) -> None:
    """Guarda un gasto en estado pendiente_tarjeta y muestra botones de medio de pago."""
    categoria_id = await _categorize(descripcion, user_id)
    supabase = get_supabase()
    result = supabase.table("movimientos").insert({
        "usuario_id": user_id,
        "fecha": fecha or date.today().isoformat(),
        "fecha_compra": fecha or date.today().isoformat(),
        "descripcion": descripcion,
        "monto": monto,
        "categoria_id": categoria_id,
        "tipo": tipo,
        "origen": "telegram",
        "estado": "pendiente_tarjeta",
    }).execute()

    mov_id = result.data[0]["id"] if result.data else None
    if not mov_id:
        await _send(chat_id, "Error guardando el movimiento 😕", token, parse_mode="")
        return

    await _send(
        chat_id,
        f"💳 *${monto:,.0f} {descripcion}* — ¿cómo lo pagaste?",
        token,
        reply_markup=pago_keyboard(tarjetas, mov_id),
    )


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
    categoria_id = 17 if tipo == "ingreso" else await _categorize(descripcion, user_id)

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
    await _send(chat_id, f"✅ Registrado: {signo}${monto:,.0f} · {cat_emoji} {cat_name}", token, parse_mode="")

    if tipo == "gasto" and categoria_id not in (7, 17):
        await _check_presupuesto_alert(
            usuario_id=user_id, categoria_id=categoria_id, chat_id=chat_id, token=token
        )


async def _process_text(text: str, user_id: str, chat_id: int, token: str) -> None:
    # ── Edición de monto pendiente ──
    supabase = get_supabase()
    pending = (
        supabase.table("movimientos")
        .select("id, descripcion, monto")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente_edicion_monto")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if pending.data:
        mov = pending.data[0]
        num_match = re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
        if num_match:
            nuevo_monto = float(num_match.group().replace(",", "."))
            supabase.table("movimientos").update(
                {"monto": nuevo_monto, "estado": "confirmado"}
            ).eq("id", mov["id"]).execute()
            await _send(chat_id,
                f"✅ *{mov['descripcion']}* actualizado: ${nuevo_monto:,.0f}", token)
            return
        supabase.table("movimientos").update({"estado": "confirmado"}).eq("id", mov["id"]).execute()

    dia_mes = parse_recurrente(text)
    cuota_progreso = parse_cuota_progreso(text)
    num_cuotas = parse_cuotas(text)

    if dia_mes:
        clean = strip_recurrente(text)
    elif cuota_progreso or num_cuotas:
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

    if monto <= 0:
        await _send(chat_id, "El monto debe ser mayor a cero 🤔", token, parse_mode="")
        return

    # ── Gasto recurrente ──
    if dia_mes and tipo == "gasto":
        await _registrar_recurrente(text, monto, descripcion, tipo, dia_mes, user_id, chat_id, token)
        return

    # ── Compra en cuotas en progreso (ej: "cuota 3/12") ──
    if cuota_progreso and tipo == "gasto":
        cuota_actual, total = cuota_progreso
        await _registrar_cuota_plan(text, monto, descripcion, tipo, total, user_id, chat_id, token, cuota_actual=cuota_actual)
        return

    # ── Compra en cuotas desde el inicio ──
    if num_cuotas and tipo == "gasto":
        await _registrar_cuota_plan(text, monto, descripcion, tipo, num_cuotas, user_id, chat_id, token)
        return

    # ── Flujo normal ──
    moneda = _detect_currency(text)
    if moneda == "USD":
        tasa = await _get_dolar_oficial()
        if not tasa:
            await _send(chat_id, "No pude obtener el tipo de cambio 😕 Intentá de nuevo.", token, parse_mode="")
            return
        monto_ars = round(monto * tasa)
        descripcion = f"{descripcion} (USD {monto:,.0f} @ ${tasa:,.0f} oficial)"
        monto = monto_ars

    # Para gastos: preguntar medio de pago si el usuario tiene tarjetas configuradas
    if tipo == "gasto":
        tarjetas = get_tarjetas_activas(user_id)
        if tarjetas:
            await _save_pending_tarjeta(
                chat_id=chat_id, token=token, user_id=user_id,
                descripcion=descripcion, monto=monto, tipo=tipo,
                tarjetas=tarjetas,
            )
            return

    monto_bajo = monto < 1000
    await _save_and_confirm(
        chat_id=chat_id, token=token, user_id=user_id,
        descripcion=descripcion, monto=monto, tipo=tipo,
        estado="pendiente_confirmacion" if monto_bajo else "confirmado",
        nota_monto_bajo=monto_bajo,
    )
