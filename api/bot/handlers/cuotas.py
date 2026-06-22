import re
from datetime import date
from lib.supabase_client import get_supabase
from lib.date_utils import add_months
from lib.tarjetas import calcular_mes_resumen
from ..tg import _send, _get_dolar_oficial
from ..keyboards import _cuota_fecha_keyboard
from ..helpers import _detect_currency, _categorize
from .tarjetas import get_tarjetas_activas, cuota_tarjeta_keyboard


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


async def _create_cuota_movimientos(plan_id: int, primer_fecha: date, token: str) -> None:
    supabase = get_supabase()
    plan = supabase.table("cuotas_plan").select("*").eq("id", plan_id).single().execute()
    if not plan.data:
        return
    p = plan.data
    cuota_inicio = p.get("cuota_inicio", 1)
    remaining = p["num_cuotas"] - cuota_inicio + 1
    tarjeta_id = p.get("tarjeta_id")

    # Resolver dia_cierre si tiene tarjeta asociada
    dia_cierre = None
    if tarjeta_id:
        tar_r = supabase.table("tarjetas").select("dia_cierre").eq("id", tarjeta_id).single().execute()
        dia_cierre = tar_r.data.get("dia_cierre") if tar_r.data else None

    movimientos = []
    for i in range(remaining):
        fecha_cuota = add_months(primer_fecha, i)
        # mes_resumen: como la cuota cae el 1° del mes, siempre es <= dia_cierre → mismo mes
        mes_res = calcular_mes_resumen(fecha_cuota, dia_cierre) if dia_cierre else None
        row: dict = {
            "usuario_id": p["usuario_id"],
            "fecha": fecha_cuota.isoformat(),
            "fecha_compra": fecha_cuota.isoformat(),
            "descripcion": f"{p['descripcion']} (cuota {cuota_inicio + i}/{p['num_cuotas']})",
            "monto": p["monto_cuota"],
            "categoria_id": p["categoria_id"],
            "tipo": "gasto",
            "origen": "telegram",
            "estado": "confirmado",
        }
        if tarjeta_id:
            row["tarjeta_id"] = tarjeta_id
        if mes_res:
            row["mes_resumen"] = mes_res
        movimientos.append(row)

    supabase.table("movimientos").insert(movimientos).execute()
    supabase.table("cuotas_plan").update(
        {"fecha_primera_cuota": primer_fecha.isoformat()}
    ).eq("id", plan_id).execute()

    chat_id = int(p["usuario_id"])
    ultima = add_months(primer_fecha, remaining - 1)
    if cuota_inicio > 1:
        msg = (
            f"✅ *{p['descripcion']}* — registrando cuota {cuota_inicio}/{p['num_cuotas']} en adelante\n"
            f"💳 ${p['monto_cuota']:,.0f}/mes · desde: {primer_fecha.strftime('%m/%Y')}\n"
            f"📆 Última cuota: {ultima.strftime('%m/%Y')}"
        )
    else:
        msg = (
            f"✅ *{p['descripcion']}* en {p['num_cuotas']} cuotas\n"
            f"💳 ${p['monto_cuota']:,.0f}/mes · primera: {primer_fecha.strftime('%d/%m/%Y')}\n"
            f"📆 Última cuota: {ultima.strftime('%m/%Y')}"
        )
    await _send(chat_id, msg, token)


async def _registrar_cuota_plan(
    text: str, monto: float, descripcion: str, tipo: str,
    num_cuotas: int, user_id: str, chat_id: int, token: str,
    cuota_actual: int = 1,
) -> None:
    moneda = _detect_currency(text)
    if moneda == "USD":
        tasa = await _get_dolar_oficial()
        if not tasa:
            await _send(chat_id, "No pude obtener el tipo de cambio 😕 Intentá de nuevo.", token, parse_mode="")
            return
        desc_limpia = re.sub(r"^(?:usd|dolar|dólares?)\s+", "", descripcion, flags=re.IGNORECASE).strip()
        monto = round(monto * tasa)
        descripcion = f"{desc_limpia} (USD @ ${tasa:,.0f} oficial)"

    monto_cuota = round(monto / num_cuotas, 2)
    categoria_id = await _categorize(descripcion, user_id)
    supabase = get_supabase()
    result = supabase.table("cuotas_plan").insert({
        "usuario_id": user_id,
        "descripcion": descripcion,
        "monto_total": monto,
        "monto_cuota": monto_cuota,
        "num_cuotas": num_cuotas,
        "cuota_inicio": cuota_actual,
        "categoria_id": categoria_id,
    }).execute()
    plan_id = result.data[0]["id"] if result.data else None
    if not plan_id:
        await _send(chat_id, "Error guardando el plan 😕", token, parse_mode="")
        return

    # Preguntar tarjeta antes de la fecha (toda compra en cuotas va con tarjeta)
    tarjetas = get_tarjetas_activas(user_id)
    if tarjetas:
        if cuota_actual > 1:
            prompt = (
                f"💳 *{descripcion}* — {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n"
                f"¿Con qué tarjeta? _(cuota {cuota_actual}/{num_cuotas})_"
            )
        else:
            prompt = (
                f"💳 *{descripcion}* en {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n"
                f"¿Con qué tarjeta?"
            )
        await _send(chat_id, prompt, token, reply_markup=cuota_tarjeta_keyboard(tarjetas, plan_id))
    else:
        if cuota_actual > 1:
            prompt = (
                f"💳 *{descripcion}* — {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n"
                f"¿Cuándo cae la cuota {cuota_actual}/{num_cuotas}?"
            )
        else:
            prompt = f"💳 *{descripcion}* en {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n¿Primera cuota?"
        await _send(chat_id, prompt, token, reply_markup=_cuota_fecha_keyboard(plan_id))
