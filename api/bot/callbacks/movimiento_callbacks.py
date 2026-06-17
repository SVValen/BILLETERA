from datetime import date
from lib.supabase_client import get_supabase
from lib.parser import categorize_from_keywords
from lib.date_utils import add_months
from ..tg import _send, _answer_callback, _edit_message
from ..keyboards import _category_keyboard, _edit_submenu_keyboard, _del_confirm_keyboard
from ..helpers import _save_learned_keywords
from ..handlers.presupuestos import _check_presupuesto_alert
from ..handlers.cuotas import _create_cuota_movimientos, _first_of_month


async def handle_movimiento_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:
    """Maneja callbacks de movimientos, recurrentes, cuotas y edición. Retorna True si consumió el callback."""

    if parts[0] == "cat" and len(parts) == 3:
        movement_id, cat_id = int(parts[1]), int(parts[2])
        supabase.table("movimientos").update(
            {"categoria_id": cat_id, "estado": "confirmado"}
        ).eq("id", movement_id).eq("usuario_id", user_id).execute()
        cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", cat_id).single().execute()
        cat_name = cat_row.data.get("nombre", "?") if cat_row.data else "?"
        cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"
        mov = supabase.table("movimientos").select("usuario_id, descripcion").eq("id", movement_id).single().execute()
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, f"✅ Guardado como {cat_emoji} {cat_name}", token)
        if mov.data:
            uid = mov.data["usuario_id"]
            desc = mov.data["descripcion"]
            await _save_learned_keywords(desc, cat_id, uid)
            if token:
                await _check_presupuesto_alert(
                    usuario_id=uid, categoria_id=cat_id, chat_id=chat_id, token=token
                )
        return True

    if parts[0] == "monto_ok" and len(parts) == 2:
        movement_id = int(parts[1])
        supabase.table("movimientos").update({"estado": "confirmado"}).eq("id", movement_id).eq("usuario_id", user_id).execute()
        row = supabase.table("movimientos").select("monto, usuario_id, categoria_id, categorias(nombre, emoji)").eq("id", movement_id).single().execute()
        monto = row.data["monto"] if row.data else 0
        cat = (row.data.get("categorias") or {}) if row.data else {}
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"✅ Guardado: -${monto:,.0f} · {cat.get('emoji','📌')} {cat.get('nombre','?')}", token)
        if row.data and token:
            await _check_presupuesto_alert(
                usuario_id=row.data["usuario_id"], categoria_id=row.data["categoria_id"],
                chat_id=chat_id, token=token
            )
        return True

    if parts[0] == "monto_x1000" and len(parts) == 2:
        movement_id = int(parts[1])
        row = supabase.table("movimientos").select("monto, tipo, descripcion, usuario_id, categorias(nombre, emoji)").eq("id", movement_id).eq("usuario_id", user_id).single().execute()
        if row.data:
            nuevo_monto = row.data["monto"] * 1000
            tipo = row.data["tipo"]
            descripcion = row.data["descripcion"]
            cat = row.data.get("categorias") or {}
            categoria_id = categorize_from_keywords(descripcion)
            supabase.table("movimientos").update({
                "monto": nuevo_monto,
                "categoria_id": categoria_id,
                "estado": "confirmado" if categoria_id != 7 else "pendiente_categoria",
            }).eq("id", movement_id).eq("usuario_id", user_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                if categoria_id == 7 and tipo == "gasto":
                    await _edit_message(chat_id, message_id,
                        f"💲 Actualizado a ${nuevo_monto:,.0f} — ¿categoría?", token)
                    await _send(chat_id, f"¿En qué categoría va *{descripcion}*?", token,
                                reply_markup=_category_keyboard(movement_id))
                else:
                    await _edit_message(chat_id, message_id,
                        f"✅ Guardado: -${nuevo_monto:,.0f} · {cat.get('emoji','📌')} {cat.get('nombre','?')}", token)
                if tipo == "gasto" and categoria_id not in (7, 17) and token:
                    await _check_presupuesto_alert(
                        usuario_id=row.data["usuario_id"], categoria_id=categoria_id,
                        chat_id=chat_id, token=token
                    )
        return True

    if parts[0] == "cuota_fecha" and len(parts) == 3:
        plan_id, proximo = int(parts[1]), int(parts[2])
        plan_check = supabase.table("cuotas_plan").select("usuario_id").eq("id", plan_id).single().execute()
        if not plan_check.data or plan_check.data["usuario_id"] != user_id:
            if token:
                await _answer_callback(callback_id, token)
            return True
        hoy = date.today()
        meses = proximo if (proximo > 0 or hoy.day == 1) else 1
        primer_fecha = _first_of_month(add_months(hoy, meses))
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"📅 Primera cuota: {primer_fecha.strftime('%d/%m/%Y')} — creando movimientos...", token)
            await _create_cuota_movimientos(plan_id, primer_fecha, token)
        return True

    if parts[0] == "recurrente_si" and len(parts) == 2:
        rec_id = int(parts[1])
        rec = supabase.table("recurrentes").select("*").eq("id", rec_id).single().execute()
        if rec.data and rec.data["usuario_id"] != user_id:
            if token:
                await _answer_callback(callback_id, token)
            return True
        if rec.data:
            r = rec.data
            supabase.table("movimientos").insert({
                "usuario_id": r["usuario_id"],
                "fecha": date.today().isoformat(),
                "descripcion": r["descripcion"],
                "monto": r["monto"],
                "categoria_id": r["categoria_id"],
                "tipo": r["tipo"],
                "origen": "telegram",
                "estado": "confirmado",
            }).execute()
            supabase.table("recurrentes").update(
                {"ultimo_recordatorio": date.today().isoformat()}
            ).eq("id", rec_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"✅ Registrado: -{r['descripcion']} ${r['monto']:,.0f}", token)
            if token:
                await _check_presupuesto_alert(
                    usuario_id=r["usuario_id"], categoria_id=r["categoria_id"],
                    chat_id=chat_id, token=token
                )
        return True

    if parts[0] == "recurrente_no" and len(parts) == 2:
        rec_id = int(parts[1])
        supabase.table("recurrentes").update(
            {"ultimo_recordatorio": date.today().isoformat()}
        ).eq("id", rec_id).eq("usuario_id", user_id).execute()
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "⏭ Saltado por hoy.", token)
        return True

    if parts[0] == "edit" and len(parts) == 2:
        movement_id = int(parts[1])
        row = supabase.table("movimientos").select("descripcion, monto, tipo").eq("id", movement_id).eq("usuario_id", user_id).single().execute()
        if row.data and token:
            r = row.data
            signo = "-" if r["tipo"] == "gasto" else "+"
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"✏️ *{r['descripcion']}* — {signo}${r['monto']:,.0f}\n¿Qué querés hacer?", token)
            await _send(chat_id, "Elegí una opción:", token, parse_mode="",
                        reply_markup=_edit_submenu_keyboard(movement_id))
        return True

    if parts[0] == "edit_monto" and len(parts) == 2:
        movement_id = int(parts[1])
        supabase.table("movimientos").update(
            {"estado": "pendiente_edicion_monto"}
        ).eq("id", movement_id).eq("usuario_id", user_id).execute()
        row = supabase.table("movimientos").select("descripcion").eq("id", movement_id).eq("usuario_id", user_id).single().execute()
        desc = row.data["descripcion"] if row.data else "?"
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"💰 Enviá el nuevo monto para *{desc}*:", token)
        return True

    if parts[0] == "edit_cat" and len(parts) == 2:
        movement_id = int(parts[1])
        row = supabase.table("movimientos").select("descripcion").eq("id", movement_id).eq("usuario_id", user_id).single().execute()
        desc = row.data["descripcion"] if row.data else "?"
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"📂 ¿A qué categoría movemos *{desc}*?", token)
            await _send(chat_id, "Elegí categoría:", token, parse_mode="",
                        reply_markup=_category_keyboard(movement_id))
        return True

    if parts[0] == "del" and len(parts) == 2:
        movement_id = int(parts[1])
        row = supabase.table("movimientos").select("descripcion, monto, tipo").eq("id", movement_id).eq("usuario_id", user_id).single().execute()
        if row.data and token:
            r = row.data
            signo = "-" if r["tipo"] == "gasto" else "+"
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"🗑️ ¿Borrar *{r['descripcion']}* ({signo}${r['monto']:,.0f})?", token)
            await _send(chat_id, "¿Confirmar?", token, parse_mode="",
                        reply_markup=_del_confirm_keyboard(movement_id))
        return True

    if parts[0] == "del_ok" and len(parts) == 2:
        movement_id = int(parts[1])
        row = supabase.table("movimientos").select("descripcion, monto").eq("id", movement_id).eq("usuario_id", user_id).single().execute()
        supabase.table("movimientos").update({"estado": "anulado"}).eq("id", movement_id).eq("usuario_id", user_id).execute()
        if token:
            await _answer_callback(callback_id, token)
            desc = row.data["descripcion"] if row.data else "?"
            await _edit_message(chat_id, message_id, f"🗑️ *{desc}* eliminado.", token)
        return True

    if parts[0] == "del_no" and len(parts) == 2:
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "✕ Cancelado.", token)
        return True

    return False
