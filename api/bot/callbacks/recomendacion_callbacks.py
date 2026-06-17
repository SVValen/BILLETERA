from ..tg import _answer_callback, _edit_message


async def handle_recomendacion_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:
    """Maneja inv_ok e inv_no. Retorna True si consumió el callback."""

    if parts[0] == "inv_ok" and len(parts) == 2:
        rec_id = int(parts[1])
        rec_r = supabase.table("recomendaciones").select("*").eq("id", rec_id).eq("usuario_id", user_id).limit(1).execute()
        rec = rec_r.data[0] if rec_r.data else None
        if rec and rec["estado"] == "pendiente":
            supabase.table("recomendaciones").update({
                "estado": "aceptada", "decidido_at": "now()"
            }).eq("id", rec_id).execute()
            supabase.table("decisiones_inversion").insert({
                "usuario_id": user_id,
                "recomendacion_id": rec_id,
                "accion": "aceptada",
                "precio_entrada": rec.get("precio_recomendacion"),
            }).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✅ *Recomendación aceptada* — acordate de ejecutar la orden en IOL/exchange.", token)
        return True

    if parts[0] == "inv_no" and len(parts) == 2:
        rec_id = int(parts[1])
        rec_r = supabase.table("recomendaciones").select("id, estado").eq("id", rec_id).eq("usuario_id", user_id).limit(1).execute()
        rec = rec_r.data[0] if rec_r.data else None
        if rec and rec["estado"] == "pendiente":
            supabase.table("recomendaciones").update({
                "estado": "rechazada", "decidido_at": "now()"
            }).eq("id", rec_id).execute()
            supabase.table("decisiones_inversion").insert({
                "usuario_id": user_id,
                "recomendacion_id": rec_id,
                "accion": "rechazada",
            }).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id, "❌ Recomendación rechazada.", token)
        return True

    return False
