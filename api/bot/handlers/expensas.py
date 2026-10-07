"""
PDF de liquidación de expensas enviado al bot → lee la fila del inquilino y carga
expensas (sin extraordinarias), agua y gas en el mes en que se pagan.
"""
import httpx

from lib import alquiler as alq
from ..tg import _send


async def _descargar(file_id: str, token: str) -> bytes | None:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id})
        if r.status_code != 200 or not r.json().get("ok"):
            return None
        path = r.json()["result"]["file_path"]
        f = await client.get(f"https://api.telegram.org/file/bot{token}/{path}")
        return f.content if f.status_code == 200 else None


def _fmt(n: float) -> str:
    return "$" + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def handle_documento(message: dict, user_id: str, chat_id: int, token: str) -> bool:
    doc = message.get("document") or {}
    nombre = (doc.get("file_name") or "").lower()
    if doc.get("mime_type") != "application/pdf" and not nombre.endswith(".pdf"):
        return False
    contrato = alq.get_contrato(user_id)
    if not contrato:
        await _send(chat_id, "Recibí un PDF, pero no tenés un contrato de alquiler cargado.", token, parse_mode="")
        return True

    await _send(chat_id, "📄 Leyendo la liquidación de expensas...", token, parse_mode="")
    contenido = await _descargar(doc["file_id"], token)
    if not contenido:
        await _send(chat_id, "No pude descargar el PDF. Probá mandarlo de nuevo.", token, parse_mode="")
        return True

    from lib.expensas_pdf import parse_liquidacion
    try:
        liq = parse_liquidacion(contenido, contrato.get("unidad_expensas") or "SOSA VALENTINA")
    except Exception:
        liq = None
    if not liq:
        await _send(
            chat_id,
            "No encontré tu fila en el PDF. ¿Es la liquidación de expensas del edificio? "
            "Busco las filas a nombre de " + (contrato.get("unidad_expensas") or "SOSA VALENTINA") + ".",
            token, parse_mode="",
        )
        return True
    if not liq.get("cuadra"):
        await _send(chat_id, "⚠️ Leí tu fila pero los importes no suman el total. No cargué nada; revisalo a mano.",
                    token, parse_mode="")
        return True

    res = alq.aplicar_liquidacion(user_id, liq)
    lineas = [
        f"🏢 *Expensas — liquidación {liq['liquidacion']}*, se pagan en {liq['mes_pago']}"
        + (f" (vence {liq['vencimiento'][8:10]}/{liq['vencimiento'][5:7]})" if liq.get("vencimiento") else ""),
        "",
        f"Total de tu fila: {_fmt(liq['total'])}",
        f"− Expensas extraordinarias (propietaria): {_fmt(liq['exp_extra'])}",
        f"*A pagar: {_fmt(liq['a_pagar'])}*",
        "",
        f"🏢 Expensas: {_fmt(res.get('expensas', 0))}",
        f"💧 Agua: {_fmt(res.get('agua', 0))}",
        f"🔥 Gas: {_fmt(res.get('gas', 0))}",
        "",
        "Actualicé el alquiler de ese mes. Miralo con `/alquiler " + liq["mes_pago"] + "`.",
    ]
    await _send(chat_id, "\n".join(lineas), token)
    return True
