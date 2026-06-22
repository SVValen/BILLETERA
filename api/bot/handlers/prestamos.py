import re
from datetime import date
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message

_KEYWORDS_RE = re.compile(
    r"\b(cuota\s+auto|prestamo|préstamo|cuota\s+prest|pago\s+auto)\b", re.IGNORECASE
)


def detect_prestamo_text(text: str) -> bool:
    return bool(_KEYWORDS_RE.search(text))


def _get_auto_cat_id(supabase) -> int:
    r = supabase.table("categorias").select("id").eq("nombre", "Auto").limit(1).execute()
    return r.data[0]["id"] if r.data else 7


def _proxima_pendiente(prestamo_id: int, supabase) -> dict | None:
    r = (
        supabase.table("prestamo_cuotas")
        .select("*")
        .eq("prestamo_id", prestamo_id)
        .eq("pagado", False)
        .order("numero_cuota")
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def _cuotas_stats(prestamo_id: int, supabase) -> tuple[int, int]:
    """Returns (pagadas, total)."""
    total_r = supabase.table("prestamo_cuotas").select("id").eq("prestamo_id", prestamo_id).execute()
    pend_r = supabase.table("prestamo_cuotas").select("id").eq("prestamo_id", prestamo_id).eq("pagado", False).execute()
    total = len(total_r.data) if total_r.data else 0
    pendientes = len(pend_r.data) if pend_r.data else 0
    return total - pendientes, total


async def handle_prestamos_cmd(user_id: str, chat_id: int, token: str) -> None:
    supabase = get_supabase()
    prest_r = (
        supabase.table("prestamos")
        .select("*")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .execute()
    )
    if not prest_r.data:
        await _send(
            chat_id,
            "No tenés préstamos registrados.\n\nImportá el cronograma desde el dashboard.",
            token, parse_mode="",
        )
        return

    lines = []
    buttons = []
    for p in prest_r.data:
        pagadas, total = _cuotas_stats(p["id"], supabase)
        proxima = _proxima_pendiente(p["id"], supabase)
        pendientes = total - pagadas

        lines.append(f"🏦 *{p['nombre']}*\n")
        lines.append(f"Cuotas pagadas: {pagadas} de {total}")
        if proxima:
            monto_ord = proxima.get("monto_ordinario") or 0
            lines.append(f"Próxima cuota: #{proxima['numero_cuota']} — {proxima['mes_previsto']} — ${monto_ord:,.0f}")
            lines.append(f"Cuotas restantes: {pendientes}")
            buttons.append([{"text": f"💳 Pagar cuotas — {p['nombre']}", "callback_data": f"prest_iniciar:{p['id']}"}])
        else:
            lines.append("✅ ¡Préstamo cancelado!")
        lines.append("")

    kb = {"inline_keyboard": buttons} if buttons else None
    await _send(chat_id, "\n".join(lines).strip(), token, reply_markup=kb)


async def handle_prestamo_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:

    if parts[0] == "prest_iniciar" and len(parts) == 2:
        prestamo_id = int(parts[1])
        prest_r = (
            supabase.table("prestamos").select("*")
            .eq("id", prestamo_id).eq("usuario_id", user_id).limit(1).execute()
        )
        if not prest_r.data:
            await _answer_callback(callback_id, token)
            return True
        prest = prest_r.data[0]
        proxima = _proxima_pendiente(prestamo_id, supabase)
        if not proxima:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "✅ ¡Todas las cuotas están pagadas!", token)
            return True
        monto_ord = proxima.get("monto_ordinario") or 0
        n = proxima["numero_cuota"]
        mes = proxima["mes_previsto"]
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id,
            f"🏦 *{prest['nombre']}* — Próxima cuota pendiente: #{n}\n"
            f"Mes previsto: {mes}\n"
            f"Monto ordinario: ${monto_ord:,.0f}\n\n"
            f"¿Pagás la cuota {n} completa?",
            token,
            reply_markup={"inline_keyboard": [[
                {"text": f"✅ Sí, pagar cuota {n}", "callback_data": f"prest_pagar:{proxima['id']}"},
                {"text": "❌ No por ahora", "callback_data": f"prest_skip:{prestamo_id}"},
            ]]}
        )
        return True

    if parts[0] == "prest_skip" and len(parts) == 2:
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "Ok, cuando quieras retomás con /prestamos.", token)
        return True

    if parts[0] == "prest_pagar" and len(parts) == 2:
        cuota_id = int(parts[1])
        cuota_r = (
            supabase.table("prestamo_cuotas").select("*")
            .eq("id", cuota_id).eq("usuario_id", user_id).limit(1).execute()
        )
        if not cuota_r.data:
            await _answer_callback(callback_id, token)
            return True
        cuota = cuota_r.data[0]
        prestamo_id = cuota["prestamo_id"]

        prest_r = supabase.table("prestamos").select("nombre").eq("id", prestamo_id).limit(1).execute()
        prest_nombre = prest_r.data[0]["nombre"] if prest_r.data else "Préstamo"
        cat_id = _get_auto_cat_id(supabase)
        monto = cuota.get("monto_ordinario") or cuota["capital"]

        mov_r = supabase.table("movimientos").insert({
            "usuario_id": user_id,
            "fecha": date.today().isoformat(),
            "descripcion": f"{prest_nombre} — cuota {cuota['numero_cuota']}",
            "monto": monto,
            "categoria_id": cat_id,
            "tipo": "gasto",
            "origen": "telegram",
            "estado": "confirmado",
        }).execute()
        mov_id = mov_r.data[0]["id"] if mov_r.data else None

        supabase.table("prestamo_cuotas").update({
            "pagado": True,
            "tipo_pago": "ordinaria",
            "monto_pagado": monto,
            "fecha_pago": date.today().isoformat(),
            "movimiento_id": mov_id,
        }).eq("id", cuota_id).execute()

        pagadas, total = _cuotas_stats(prestamo_id, supabase)
        pending_r = (
            supabase.table("prestamo_cuotas").select("id")
            .eq("prestamo_id", prestamo_id).eq("pagado", False).execute()
        )
        hay_pendientes = bool(pending_r.data)

        await _answer_callback(callback_id, token)
        if not hay_pendientes:
            await _edit_message(chat_id, message_id,
                f"✅ Cuota {cuota['numero_cuota']} registrada — ${monto:,.0f}\n\n"
                f"🎉 ¡Préstamo cancelado! No quedan cuotas pendientes.", token)
            return True

        await _edit_message(chat_id, message_id,
            f"✅ Cuota {cuota['numero_cuota']} registrada — ${monto:,.0f}\n"
            f"Cuotas pagadas: {pagadas} de {total}\n\n"
            f"¿Querés adelantar cuotas este mes?",
            token,
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Sí", "callback_data": f"prest_adelantar_si:{prestamo_id}"},
                {"text": "❌ No", "callback_data": f"prest_adelantar_no:{prestamo_id}"},
            ]]}
        )
        return True

    if parts[0] == "prest_adelantar_no" and len(parts) == 2:
        prestamo_id = int(parts[1])
        proxima = _proxima_pendiente(prestamo_id, supabase)
        await _answer_callback(callback_id, token)
        if proxima:
            await _edit_message(chat_id, message_id,
                f"Listo. Próxima cuota pendiente: #{proxima['numero_cuota']} ({proxima['mes_previsto']})", token)
        else:
            await _edit_message(chat_id, message_id, "🎉 ¡Préstamo cancelado!", token)
        return True

    if parts[0] == "prest_adelantar_si" and len(parts) == 2:
        prestamo_id = int(parts[1])
        prest_r = supabase.table("prestamos").select("id").eq("id", prestamo_id).eq("usuario_id", user_id).limit(1).execute()
        if not prest_r.data:
            await _answer_callback(callback_id, token)
            return True
        pending_r = (
            supabase.table("prestamo_cuotas").select("numero_cuota")
            .eq("prestamo_id", prestamo_id).eq("pagado", False)
            .order("numero_cuota").execute()
        )
        max_n = min(5, len(pending_r.data) if pending_r.data else 0)
        if max_n == 0:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "No hay cuotas pendientes para adelantar.", token)
            return True
        buttons = [[
            {"text": f"{n} cuota{'s' if n > 1 else ''}",
             "callback_data": f"prest_ncuotas:{prestamo_id}:{n}"}
            for n in range(1, max_n + 1)
        ]]
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "¿Cuántas cuotas adelantás?", token,
                            reply_markup={"inline_keyboard": buttons})
        return True

    if parts[0] == "prest_ncuotas" and len(parts) == 3:
        prestamo_id = int(parts[1])
        n = int(parts[2])
        prest_r = supabase.table("prestamos").select("nombre").eq("id", prestamo_id).eq("usuario_id", user_id).limit(1).execute()
        if not prest_r.data:
            await _answer_callback(callback_id, token)
            return True
        pending_r = (
            supabase.table("prestamo_cuotas").select("*")
            .eq("prestamo_id", prestamo_id).eq("pagado", False)
            .order("numero_cuota").limit(n).execute()
        )
        cuotas = pending_r.data or []
        if not cuotas:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "No hay cuotas pendientes.", token)
            return True

        total_adelanto = sum(round(float(c["capital"]) * 1.25, 2) for c in cuotas)
        cuota_ids = ",".join(str(c["id"]) for c in cuotas)

        lines = ["*Cuotas a adelantar:*\n```"]
        lines.append(f"{'Cuota':<8} {'Capital':>12}  {'× 1.25':>12}")
        lines.append("─" * 36)
        for c in cuotas:
            adelanto = round(float(c["capital"]) * 1.25, 2)
            lines.append(f"#{c['numero_cuota']:<7} ${float(c['capital']):>11,.0f}  ${adelanto:>11,.0f}")
        lines.append("─" * 36)
        lines.append(f"{'Total':<20}  ${total_adelanto:>11,.0f}")
        lines.append("```")
        lines.append("\n¿Adelantás ese monto completo?")

        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "\n".join(lines), token,
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Confirmar", "callback_data": f"prest_confirmar:{prestamo_id}:{cuota_ids}"},
                {"text": "⚙️ Cambiar cantidad", "callback_data": f"prest_adelantar_si:{prestamo_id}"},
                {"text": "❌ Cancelar", "callback_data": f"prest_adelantar_no:{prestamo_id}"},
            ]]}
        )
        return True

    if parts[0] == "prest_confirmar" and len(parts) == 3:
        prestamo_id = int(parts[1])
        cuota_ids = [int(x) for x in parts[2].split(",")]
        prest_r = supabase.table("prestamos").select("nombre").eq("id", prestamo_id).eq("usuario_id", user_id).limit(1).execute()
        if not prest_r.data:
            await _answer_callback(callback_id, token)
            return True
        prest_nombre = prest_r.data[0]["nombre"]
        cat_id = _get_auto_cat_id(supabase)

        cuotas_r = (
            supabase.table("prestamo_cuotas").select("*")
            .in_("id", cuota_ids).eq("usuario_id", user_id).execute()
        )
        cuotas = sorted(cuotas_r.data or [], key=lambda c: c["numero_cuota"])

        today = date.today().isoformat()
        total_adelanto = 0.0
        for c in cuotas:
            monto_adelanto = round(float(c["capital"]) * 1.25, 2)
            total_adelanto += monto_adelanto
            mov_r = supabase.table("movimientos").insert({
                "usuario_id": user_id,
                "fecha": today,
                "descripcion": f"{prest_nombre} — adelanto cuota {c['numero_cuota']}",
                "monto": monto_adelanto,
                "categoria_id": cat_id,
                "tipo": "gasto",
                "origen": "telegram",
                "estado": "confirmado",
            }).execute()
            mov_id = mov_r.data[0]["id"] if mov_r.data else None
            supabase.table("prestamo_cuotas").update({
                "pagado": True,
                "tipo_pago": "adelanto",
                "monto_adelanto": monto_adelanto,
                "monto_pagado": monto_adelanto,
                "fecha_pago": today,
                "movimiento_id": mov_id,
            }).eq("id", c["id"]).execute()

        numeros = [str(c["numero_cuota"]) for c in cuotas]
        if len(numeros) > 1:
            nums_txt = ", ".join(numeros[:-1]) + f" y {numeros[-1]}"
        else:
            nums_txt = numeros[0]

        pagadas, total = _cuotas_stats(prestamo_id, supabase)
        proxima = _proxima_pendiente(prestamo_id, supabase)

        msg = (
            f"✅ Adelanto de ${total_adelanto:,.0f} registrado.\n"
            f"Cuotas {nums_txt} marcadas como pagadas.\n\n"
        )
        if proxima:
            msg += f"Próxima cuota pendiente: #{proxima['numero_cuota']} ({proxima['mes_previsto']})\n"
            msg += f"Cuotas pagadas: {pagadas} de {total} — Restan: {total - pagadas}"
        else:
            msg += "🎉 ¡Préstamo cancelado! No quedan cuotas pendientes."

        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, msg, token)
        return True

    return False
