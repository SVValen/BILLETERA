"""
/alquiler — estado del alquiler del mes (alquiler, expensas, agua, gas, descuentos)
con botones para marcar pagos.

Texto libre: "descuento 28500 ducha" → descuento del alquiler del mes en curso.
"""
import re

from lib import alquiler as alq
from lib.date_utils import validate_mes
from ..tg import _send, _answer_callback, _edit_message

_DESCUENTO_RE = re.compile(r"^\s*descuento\s+\$?\s*([\d.,]+)\s+(.+)$", re.IGNORECASE)
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _nombre_mes(mes: str) -> str:
    y, m = mes.split("-")
    return f"{_MESES[int(m) - 1].capitalize()} {y}"


def _fmt(n: float) -> str:
    s = f"{abs(n):,.0f}".replace(",", ".")
    return f"-${s}" if n < 0 else f"${s}"


def _parse_monto(raw: str) -> float | None:
    raw = raw.strip()
    # "28.500" / "28500" / "28.500,50" / "28500.5"
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") >= 1 and len(raw.split(".")[-1]) == 3:
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _texto_y_teclado(user_id: str, mes: str) -> tuple[str, dict | None]:
    res = alq.resumen_mes(user_id, mes)
    if not res["items"]:
        return f"🏠 No hay gastos de alquiler cargados para {_nombre_mes(mes)}.", None

    lines = [f"🏠 *Alquiler — {_nombre_mes(mes)}*\n"]
    botones = []
    for i in res["items"]:
        concepto = i.get("concepto") or ""
        emoji = alq.EMOJI.get(concepto, "•")
        monto = float(i["monto"])
        if concepto == "descuento":
            estado = ""
        else:
            estado = "✅" if i["pagado"] else "⏳"
        est = " _(estimado)_" if i.get("estimado") else ""
        lines.append(f"{estado} {emoji} {i['descripcion']}: {_fmt(monto)}{est}")
        if not i["pagado"]:
            botones.append([{
                "text": f"✅ Pagué {i['descripcion'].lower()} ({_fmt(monto)})",
                "callback_data": f"alq_pag:{i['id']}",
            }])

    lines.append(f"\n*Total del mes:* {_fmt(res['total'])}")
    if res["pendiente"] > 0:
        lines.append(f"*Pendiente:* {_fmt(res['pendiente'])} — vence el 10")
        botones.append([{"text": "✅ Pagué todo", "callback_data": f"alq_todo:{mes}"}])
    else:
        lines.append("Todo pagado 🎉")
    if res["hay_estimados"]:
        lines.append("\n_Los estimados se actualizan cuando llega la liquidación de expensas o el ajuste por IPC._")
    lines.append("_Para descontar un arreglo: `descuento 28500 ducha`_")
    return "\n".join(lines), ({"inline_keyboard": botones} if botones else None)


async def handle_alquiler_cmd(text: str, user_id: str, chat_id: int, token: str) -> None:
    if not alq.get_contrato(user_id):
        await _send(chat_id, "No tenés un contrato de alquiler cargado.", token, parse_mode="")
        return
    arg = text[len("/alquiler"):].strip()
    mes = arg if validate_mes(arg) else alq.mes_actual()
    alq.asegurar_mes(user_id, mes)
    msg, kb = _texto_y_teclado(user_id, mes)
    await _send(chat_id, msg, token, reply_markup=kb)


async def handle_descuento_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    m = _DESCUENTO_RE.match(text)
    if not m or not alq.get_contrato(user_id):
        return False
    monto = _parse_monto(m.group(1))
    detalle = m.group(2).strip()
    if not monto:
        return False
    mes = alq.mes_actual()
    alq.asegurar_mes(user_id, mes)
    alq.agregar_descuento(user_id, mes, monto, detalle)
    res = alq.resumen_mes(user_id, mes)
    await _send(
        chat_id,
        f"🔧 Descuento registrado en el alquiler de {_nombre_mes(mes)}: *{detalle}* {_fmt(-monto)}\n"
        f"Total del mes: {_fmt(res['total'])}",
        token,
    )
    return True


async def handle_alquiler_callback(parts: list[str], callback_id: str, chat_id: int,
                                   message_id: int, user_id: str, token: str) -> bool:
    if parts[0] not in ("alq_pag", "alq_todo") or len(parts) != 2:
        return False
    if parts[0] == "alq_pag":
        alq.marcar_pagado(user_id, mov_id=int(parts[1]))
        r = alq.get_supabase().table("movimientos").select("mes_resumen").eq("id", int(parts[1])).limit(1).execute()
        mes = r.data[0]["mes_resumen"] if r.data else alq.mes_actual()
    else:
        mes = parts[1]
        alq.marcar_pagado(user_id, mes=mes)
    await _answer_callback(callback_id, token, "Listo ✅")
    msg, kb = _texto_y_teclado(user_id, mes)
    await _edit_message(chat_id, message_id, msg, token, reply_markup=kb)
    return True
