import re
from datetime import date
from lib.supabase_client import get_supabase
from lib.parser import categorize_from_keywords
from lib.date_utils import add_months
from lib.tarjetas import calcular_mes_resumen
from ..tg import _send, _answer_callback, _edit_message
from ..keyboards import _category_keyboard, _edit_submenu_keyboard, _del_confirm_keyboard, _monto_keyboard, _cuota_fecha_keyboard
from ..helpers import _save_learned_keywords
from ..handlers.presupuestos import _check_presupuesto_alert
from ..handlers.cuotas import _create_cuota_movimientos, _first_of_month


async def handle_movimiento_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:
    """Maneja callbacks de movimientos, recurrentes, cuotas y edición. Retorna True si consumió el callback."""

    # ── Medio de pago para gasto normal ──
    if parts[0] == "pago_tar" and len(parts) == 3:
        mov_id = int(parts[1])
        tarjeta_key = parts[2]  # "0" = efectivo, else = tarjeta_id

        mov_r = supabase.table("movimientos").select("*").eq("id", mov_id).eq("usuario_id", user_id).single().execute()
        if not mov_r.data:
            if token:
                await _answer_callback(callback_id, token)
            return True
        mov = mov_r.data

        hoy = date.today()
        updates: dict = {"fecha_compra": hoy.isoformat()}

        if tarjeta_key == "0":
            # Efectivo: mes_resumen = mes de la compra
            updates["mes_resumen"] = hoy.strftime("%Y-%m")
        else:
            tarjeta_id = int(tarjeta_key)
            tar_r = supabase.table("tarjetas").select("dia_cierre").eq("id", tarjeta_id).single().execute()
            if tar_r.data:
                dia_cierre = tar_r.data["dia_cierre"]
                updates["tarjeta_id"] = tarjeta_id
                updates["mes_resumen"] = calcular_mes_resumen(hoy, dia_cierre)

        monto = mov["monto"]
        monto_bajo = monto < 1000
        cat_id = mov.get("categoria_id", 7)

        if monto_bajo:
            updates["estado"] = "pendiente_confirmacion"
            supabase.table("movimientos").update(updates).eq("id", mov_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"🤔 Registré *${monto:,.0f}* — ¿está bien o querías decir *${monto * 1000:,.0f}*?",
                    token, reply_markup=_monto_keyboard(mov_id, monto))
        elif cat_id == 7:
            updates["estado"] = "pendiente_categoria"
            supabase.table("movimientos").update(updates).eq("id", mov_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"📌 Guardé *${monto:,.0f}* — ¿en qué categoría va *{mov['descripcion']}*?",
                    token)
                await _send(chat_id, "Elegí categoría:", token, parse_mode="",
                            reply_markup=_category_keyboard(mov_id))
        else:
            updates["estado"] = "confirmado"
            supabase.table("movimientos").update(updates).eq("id", mov_id).execute()
            cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", cat_id).single().execute()
            cat_name = cat_row.data.get("nombre", "Otros") if cat_row.data else "Otros"
            cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"✅ Registrado: -${monto:,.0f} · {cat_emoji} {cat_name}", token)
                await _check_presupuesto_alert(
                    usuario_id=user_id, categoria_id=cat_id, chat_id=chat_id, token=token
                )
                # Alerta de exceso en colchón si aplica
                if tarjeta_key != "0" and updates.get("mes_resumen"):
                    await _check_colchon_exceso(
                        user_id=user_id, chat_id=chat_id, token=token,
                        monto=monto, descripcion=mov["descripcion"],
                        mes_resumen=updates["mes_resumen"],
                    )
        return True

    # ── Tarjeta para cuota (cuota_tar:{plan_id}:{tarjeta_id}) ──
    if parts[0] == "cuota_tar" and len(parts) == 3:
        plan_id = int(parts[1])
        tarjeta_id = int(parts[2])

        supabase.table("cuotas_plan").update({"tarjeta_id": tarjeta_id}).eq("id", plan_id).eq("usuario_id", user_id).execute()

        plan_r = supabase.table("cuotas_plan").select("descripcion, monto_cuota, num_cuotas, cuota_inicio").eq("id", plan_id).single().execute()
        if not plan_r.data:
            if token:
                await _answer_callback(callback_id, token)
            return True
        p = plan_r.data
        cuota_inicio = p.get("cuota_inicio", 1)

        tar_r = supabase.table("tarjetas").select("nombre").eq("id", tarjeta_id).single().execute()
        nombre_tar = tar_r.data["nombre"] if tar_r.data else "tarjeta"

        if cuota_inicio > 1:
            prompt = (
                f"💳 *{p['descripcion']}* ({nombre_tar})\n"
                f"¿Cuándo cae la cuota {cuota_inicio}/{p['num_cuotas']}?"
            )
        else:
            prompt = (
                f"💳 *{p['descripcion']}* en {p['num_cuotas']} cuotas de *${p['monto_cuota']:,.0f}* ({nombre_tar})\n"
                f"¿Primera cuota?"
            )
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, prompt, token,
                                reply_markup=_cuota_fecha_keyboard(plan_id))
        return True

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
            plan_data = supabase.table("cuotas_plan").select("cuota_inicio, num_cuotas").eq("id", plan_id).single().execute()
            cuota_inicio = (plan_data.data or {}).get("cuota_inicio", 1)
            num_cuotas = (plan_data.data or {}).get("num_cuotas", "?")
            if cuota_inicio and cuota_inicio > 1:
                label = f"📅 Cuota {cuota_inicio}/{num_cuotas}: {primer_fecha.strftime('%d/%m/%Y')} — creando movimientos..."
            else:
                label = f"📅 Primera cuota: {primer_fecha.strftime('%d/%m/%Y')} — creando movimientos..."
            await _edit_message(chat_id, message_id, label, token)
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

            # Si era una cuota, ofrecer cancelar las restantes
            if row.data:
                m = re.search(r"^(.+?)\s*\(cuota \d+/(\d+)\)$", row.data["descripcion"])
                if m:
                    base, total = m.group(1), int(m.group(2))
                    resto_r = (
                        supabase.table("movimientos")
                        .select("id")
                        .eq("usuario_id", user_id)
                        .neq("estado", "anulado")
                        .like("descripcion", f"{base} (cuota %/{total})")
                        .execute()
                    )
                    if resto_r.data:
                        count = len(resto_r.data)
                        anchor_id = resto_r.data[0]["id"]
                        await _send(
                            chat_id,
                            f"¿Cancelar también las {count} cuota(s) restantes de *{base}*?",
                            token,
                            reply_markup={"inline_keyboard": [[
                                {"text": f"🗑️ Sí, cancelar {count} más", "callback_data": f"del_cuotas_resto:{anchor_id}"},
                                {"text": "✗ No", "callback_data": "del_cuotas_no"},
                            ]]},
                        )
        return True

    if parts[0] == "del_cuotas_resto" and len(parts) == 2:
        anchor_id = int(parts[1])
        anchor = supabase.table("movimientos").select("descripcion").eq("id", anchor_id).eq("usuario_id", user_id).single().execute()
        if anchor.data:
            m = re.search(r"^(.+?)\s*\(cuota \d+/(\d+)\)$", anchor.data["descripcion"])
            if m:
                base, total = m.group(1), int(m.group(2))
                resto_r = (
                    supabase.table("movimientos")
                    .select("id")
                    .eq("usuario_id", user_id)
                    .neq("estado", "anulado")
                    .like("descripcion", f"{base} (cuota %/{total})")
                    .execute()
                )
                for r in (resto_r.data or []):
                    supabase.table("movimientos").update({"estado": "anulado"}).eq("id", r["id"]).execute()
                count = len(resto_r.data or [])
                # Desactivar el plan si lo encontramos por descripción
                plan_r = (
                    supabase.table("cuotas_plan")
                    .select("id")
                    .eq("usuario_id", user_id)
                    .eq("descripcion", base)
                    .eq("num_cuotas", total)
                    .eq("activo", True)
                    .limit(1)
                    .execute()
                )
                if plan_r.data:
                    supabase.table("cuotas_plan").update({"activo": False}).eq("id", plan_r.data[0]["id"]).execute()
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, f"🗑️ Plan cancelado — {count} cuota(s) eliminadas.", token)
        return True

    if parts[0] == "del_cuotas_no":
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "✕ Solo esa cuota fue eliminada.", token)
        return True

    if parts[0] == "del_no" and len(parts) == 2:
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "✕ Cancelado.", token)
        return True

    return False


async def _check_colchon_exceso(
    *, user_id: str, chat_id: int, token: str,
    monto: float, descripcion: str, mes_resumen: str,
) -> None:
    """
    Verifica si un gasto variable con tarjeta supera el tope_variable del colchón.
    Solo actúa si hay un colchón activo con tope_variable fijado para ese mes.
    """
    supabase = get_supabase()

    # Buscar colchón activo del usuario
    port_r = (
        supabase.table("portafolios")
        .select("id")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .eq("proposito", "colchon_tarjetas")
        .limit(1)
        .execute()
    )
    if not port_r.data:
        return

    portafolio_id = port_r.data[0]["id"]

    # Buscar registro mensual con tope fijado
    mes_r = (
        supabase.table("colchon_mensual")
        .select("tope_variable")
        .eq("portafolio_id", portafolio_id)
        .eq("mes", mes_resumen)
        .limit(1)
        .execute()
    )
    if not mes_r.data or not mes_r.data[0].get("tope_variable"):
        return

    tope = float(mes_r.data[0]["tope_variable"])

    # Sumar gastos variables con tarjeta para ese mes_resumen (excluye cuotas)
    gastos_r = (
        supabase.table("movimientos")
        .select("monto, descripcion")
        .eq("usuario_id", user_id)
        .eq("mes_resumen", mes_resumen)
        .eq("tipo", "gasto")
        .neq("estado", "anulado")
        .not_.is_("tarjeta_id", "null")
        .execute()
    )
    cuota_re = re.compile(r"\(cuota \d+/\d+\)")
    gastado = sum(
        float(r["monto"]) for r in (gastos_r.data or [])
        if not cuota_re.search(r.get("descripcion", ""))
    )

    if gastado > tope:
        exceso = gastado - tope
        await _send(
            chat_id,
            f"⚠️ *Te pasaste del tope de gastos variables con tarjeta este mes.*\n\n"
            f"Tope: ${tope:,.0f} | Gastado: ${gastado:,.0f} | Exceso: ${exceso:,.0f}\n\n"
            f"¿Querés ajustar el colchón o lo dejás así?",
            token,
            reply_markup={"inline_keyboard": [[
                {"text": f"📈 Ajustar colchón +${exceso:,.0f}", "callback_data": f"colchon_ajustar:{portafolio_id}:{mes_resumen}:{int(exceso)}"},
                {"text": "✓ Dejarlo así", "callback_data": "colchon_dejar"},
            ]]},
        )
