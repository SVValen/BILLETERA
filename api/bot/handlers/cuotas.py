import re
from datetime import date
from lib.supabase_client import get_supabase
from lib.date_utils import add_months
from ..tg import _send, _get_dolar_oficial
from ..keyboards import _cuota_fecha_keyboard
from ..helpers import _detect_currency, _categorize


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


async def _create_cuota_movimientos(plan_id: int, primer_fecha: date, token: str) -> None:
    supabase = get_supabase()
    plan = supabase.table("cuotas_plan").select("*").eq("id", plan_id).single().execute()
    if not plan.data:
        return
    p = plan.data
    movimientos = [
        {
            "usuario_id": p["usuario_id"],
            "fecha": add_months(primer_fecha, i).isoformat(),
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
        {"fecha_primera_cuota": primer_fecha.isoformat()}
    ).eq("id", plan_id).execute()

    chat_id = int(p["usuario_id"])
    ultima = add_months(primer_fecha, p["num_cuotas"] - 1)
    await _send(
        chat_id,
        f"✅ *{p['descripcion']}* en {p['num_cuotas']} cuotas\n"
        f"💳 ${p['monto_cuota']:,.0f}/mes · primera: {primer_fecha.strftime('%d/%m/%Y')}\n"
        f"📆 Última cuota: {ultima.strftime('%m/%Y')}",
        token,
    )


async def _registrar_cuota_plan(
    text: str, monto: float, descripcion: str, tipo: str,
    num_cuotas: int, user_id: str, chat_id: int, token: str
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
        "categoria_id": categoria_id,
    }).execute()
    plan_id = result.data[0]["id"] if result.data else None
    if not plan_id:
        await _send(chat_id, "Error guardando el plan 😕", token, parse_mode="")
        return
    await _send(chat_id,
        f"💳 *{descripcion}* en {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n¿Primera cuota?",
        token, reply_markup=_cuota_fecha_keyboard(plan_id))
