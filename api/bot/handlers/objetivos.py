import re
from datetime import date
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message


async def handle_objetivo_nuevo_cmd(text: str, user_id: str, chat_id: int, token: str) -> None:
    """
    /objetivo_nuevo Nombre | monto | YYYY-MM
    """
    args = text[len("/objetivo_nuevo"):].strip()
    if not args:
        await _send(
            chat_id,
            "📋 *Nuevo objetivo de ahorro*\n\n"
            "Formato: `/objetivo_nuevo Nombre | monto | YYYY-MM`\n\n"
            "_Ej: /objetivo_nuevo Ahorro Depto | 5000000 | 2027-12_",
            token,
        )
        return

    parts = [p.strip() for p in args.split("|")]
    if len(parts) >= 3:
        nombre = parts[0]
        monto_str = parts[1].replace(".", "").replace(",", "")
        fecha_raw = parts[2].strip()
    else:
        m = re.search(r"^(.+?)\s+([\d.,]+)\s+(\d{4}-\d{2})\s*$", args)
        if not m:
            await _send(chat_id, "No entendí el formato. Usá: `/objetivo_nuevo Nombre | monto | YYYY-MM`", token)
            return
        nombre = m.group(1).strip()
        monto_str = m.group(2).replace(".", "").replace(",", "")
        fecha_raw = m.group(3)

    fecha_str = (fecha_raw + "-01") if len(fecha_raw) == 7 else fecha_raw
    try:
        monto = float(monto_str)
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        await _send(chat_id, "Monto o fecha inválida. Usá: `/objetivo_nuevo Nombre | monto | YYYY-MM`", token)
        return

    supabase = get_supabase()
    r = supabase.table("objetivos_ahorro").insert({
        "usuario_id": user_id,
        "nombre": nombre,
        "monto_objetivo": monto,
        "fecha_objetivo": fecha.isoformat(),
    }).execute()

    if not r.data:
        await _send(chat_id, "Error al crear el objetivo 😕", token, parse_mode="")
        return

    objetivo_id = r.data[0]["id"]
    await _send(
        chat_id,
        f"🎯 *{nombre}* creado\n"
        f"Objetivo: ${monto:,.0f} para {fecha.strftime('%m/%Y')}\n\n"
        f"¿Querés iniciar una inversión para este objetivo?",
        token,
        reply_markup={"inline_keyboard": [[
            {"text": "💼 Sí, crear portafolio", "callback_data": f"obj_nuevo_port:{objetivo_id}"},
            {"text": "📋 No, solo trackearlo", "callback_data": f"obj_skip:{objetivo_id}"},
        ]]}
    )


async def handle_objetivos_cmd(user_id: str, chat_id: int, token: str) -> None:
    supabase = get_supabase()
    r = (
        supabase.table("objetivos_ahorro")
        .select("*, portafolios(nombre_personalizado, nombre_sugerido)")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .order("fecha_objetivo")
        .execute()
    )
    if not r.data:
        await _send(
            chat_id,
            "No tenés objetivos de ahorro.\n\nCreá uno con:\n`/objetivo_nuevo Nombre | monto | YYYY-MM`",
            token,
        )
        return

    lines = ["🎯 *Tus objetivos de ahorro:*\n"]
    for obj in r.data:
        monto_obj = float(obj["monto_objetivo"])
        acumulado = float(obj.get("monto_actual") or 0)
        pct = acumulado / monto_obj * 100 if monto_obj > 0 else 0
        fecha = date.fromisoformat(obj["fecha_objetivo"])

        lines.append(f"📌 *{obj['nombre']}*")
        lines.append(f"   Objetivo: ${monto_obj:,.0f} para {fecha.strftime('%m/%Y')}")
        lines.append(f"   Acumulado: ${acumulado:,.0f} ({pct:.0f}%)")

        port = obj.get("portafolios")
        if port:
            port_nombre = port.get("nombre_personalizado") or port.get("nombre_sugerido") or "Portafolio"
            lines.append(f"   💼 Vía portafolio: {port_nombre} · /portafolio")
        lines.append("")

    await _send(chat_id, "\n".join(lines).strip(), token)


async def handle_objetivo_conectar_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Lista objetivos sin portafolio para que el usuario elija cuál vincular."""
    supabase = get_supabase()
    objs_r = (
        supabase.table("objetivos_ahorro")
        .select("id, nombre")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .is_("portafolio_id", "null")
        .execute()
    )
    if not objs_r.data:
        await _send(chat_id, "Todos tus objetivos ya tienen un portafolio asociado.", token, parse_mode="")
        return
    buttons = [[{"text": obj["nombre"], "callback_data": f"obj_elegir:{obj['id']}"}] for obj in objs_r.data]
    await _send(chat_id, "¿Qué objetivo querés vincular a un portafolio?", token,
                reply_markup={"inline_keyboard": buttons})


async def handle_objetivo_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:

    if parts[0] == "obj_skip" and len(parts) == 2:
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id,
            "✅ Objetivo creado. Seguí el progreso con /objetivos.", token)
        return True

    if parts[0] == "obj_nuevo_port" and len(parts) == 2:
        objetivo_id = int(parts[1])
        supabase.table("objetivos_ahorro").update({"esperando_portafolio": True}).eq("id", objetivo_id).eq("usuario_id", user_id).execute()
        from .wizard_inversion import _send_tipo_keyboard
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id,
            "💼 *Creando portafolio para el objetivo...*\n\nAl terminar el wizard lo voy a vincular automáticamente.",
            token)
        await _send_tipo_keyboard(chat_id, token)
        return True

    if parts[0] == "obj_elegir" and len(parts) == 2:
        objetivo_id = int(parts[1])
        # Show portafolios to link to
        ports_r = (
            supabase.table("portafolios")
            .select("id, nombre_personalizado, nombre_sugerido, tipo")
            .eq("usuario_id", user_id)
            .eq("activo", True)
            .eq("estado_wizard", "activo")
            .execute()
        )
        if not ports_r.data:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "No tenés portafolios activos. Creá uno con /portafolio_nuevo.", token)
            return True
        buttons = []
        for p in ports_r.data:
            nombre = p.get("nombre_personalizado") or p.get("nombre_sugerido") or p["tipo"].capitalize()
            buttons.append([{"text": nombre, "callback_data": f"obj_sel:{p['id']}:{objetivo_id}"}])
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "¿A qué portafolio lo vinculás?", token,
                            reply_markup={"inline_keyboard": buttons})
        return True

    if parts[0] == "obj_link" and len(parts) == 2:
        portafolio_id = int(parts[1])
        objs_r = (
            supabase.table("objetivos_ahorro")
            .select("id, nombre")
            .eq("usuario_id", user_id)
            .eq("activo", True)
            .is_("portafolio_id", "null")
            .execute()
        )
        if not objs_r.data:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "No hay objetivos sin portafolio para vincular.", token)
            return True
        buttons = [[{"text": obj["nombre"], "callback_data": f"obj_sel:{portafolio_id}:{obj['id']}"}] for obj in objs_r.data]
        buttons.append([{"text": "❌ No vincular ahora", "callback_data": "obj_nolink"}])
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "¿A qué objetivo vinculás este portafolio?", token,
                            reply_markup={"inline_keyboard": buttons})
        return True

    if parts[0] == "obj_sel" and len(parts) == 3:
        portafolio_id = int(parts[1])
        objetivo_id = int(parts[2])
        supabase.table("objetivos_ahorro").update({
            "portafolio_id": portafolio_id,
            "esperando_portafolio": False,
        }).eq("id", objetivo_id).eq("usuario_id", user_id).execute()
        obj_r = supabase.table("objetivos_ahorro").select("nombre").eq("id", objetivo_id).limit(1).execute()
        obj_nombre = obj_r.data[0]["nombre"] if obj_r.data else "objetivo"
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id,
            f"✅ Portafolio vinculado al objetivo *{obj_nombre}*.", token)
        return True

    if parts[0] == "obj_nolink":
        await _answer_callback(callback_id, token)
        await _edit_message(chat_id, message_id, "Ok, sin vincular por ahora.", token)
        return True

    return False
