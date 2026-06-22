"""
Handler del colchón de tarjetas — Parte B de la Fase 5.

Un portafolio conservador con proposito='colchon_tarjetas' acumula el capital
necesario para pagar los resúmenes combinados de todas las tarjetas.

Flujo:
  /colchon_nuevo → crea el portafolio colchón
  /colchon       → muestra estado del mes actual:
                   • comprometido (cuotas fijas con tarjeta ese mes)
                   • tope variable (fijado por el usuario o sugerido por Claude)
                   • total necesario
                   • invertido (posiciones RF abiertas del portafolio colchón)
                   • gastado variable acumulado

Alertas en tiempo real: disparadas desde movimiento_callbacks.py cuando
un gasto variable supera el tope_variable del mes.
"""
import re
from datetime import date
from lib.supabase_client import get_supabase
from lib.tarjetas import mes_label
from ..tg import _send, _answer_callback, _edit_message

_CUOTA_RE = re.compile(r"\(cuota \d+/\d+\)")
_MES_ACTUAL = lambda: date.today().strftime("%Y-%m")


async def handle_colchon_nuevo_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Crea un portafolio colchón de tarjetas."""
    supabase = get_supabase()

    # Verificar si ya existe
    existing = (
        supabase.table("portafolios")
        .select("id")
        .eq("usuario_id", user_id)
        .eq("proposito", "colchon_tarjetas")
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    if existing.data:
        await _send(
            chat_id,
            "Ya tenés un colchón de tarjetas activo. Usá /colchon para ver el estado.",
            token,
            parse_mode="",
        )
        return

    supabase.table("portafolios").insert({
        "usuario_id": user_id,
        "tipo": "conservador",
        "estado_wizard": "activo",
        "activo": True,
        "proposito": "colchon_tarjetas",
        "nombre_personalizado": "Colchón Tarjetas",
        "objetivo": "Cubrir resúmenes de tarjetas de crédito",
        "asignacion_rf_pct": 100,
        "capital_usd": 0,
        "capital_ars": 0,
    }).execute()

    await _send(
        chat_id,
        "✅ *Colchón de tarjetas creado.*\n\n"
        "Usá /colchon para ver el estado del mes actual y fijar el tope de gastos variables.\n\n"
        "Para invertir el capital del colchón usá /opciones_rf (asocia la posición a este portafolio).",
        token,
    )


async def handle_colchon_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Muestra el estado del colchón de tarjetas para el mes actual."""
    supabase = get_supabase()
    mes = _MES_ACTUAL()

    # Buscar portafolio colchón activo
    port_r = (
        supabase.table("portafolios")
        .select("id, capital_usd, capital_ars")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .eq("proposito", "colchon_tarjetas")
        .limit(1)
        .execute()
    )
    if not port_r.data:
        await _send(
            chat_id,
            "No tenés un colchón de tarjetas.\n\nUsá /colchon_nuevo para crear uno.",
            token,
            parse_mode="",
        )
        return

    portafolio = port_r.data[0]
    portafolio_id = portafolio["id"]

    # ── Comprometido: cuotas fijas con tarjeta para este mes_resumen ──
    cuotas_r = (
        supabase.table("movimientos")
        .select("monto, descripcion")
        .eq("usuario_id", user_id)
        .eq("mes_resumen", mes)
        .eq("tipo", "gasto")
        .neq("estado", "anulado")
        .not_.is_("tarjeta_id", "null")
        .execute()
    )
    comprometido = 0.0
    gastado_variable = 0.0
    for r in (cuotas_r.data or []):
        monto_r = float(r["monto"])
        if _CUOTA_RE.search(r.get("descripcion", "")):
            comprometido += monto_r
        else:
            gastado_variable += monto_r

    # ── Tope variable del mes (guardado en colchon_mensual) ──
    mes_r = (
        supabase.table("colchon_mensual")
        .select("id, tope_variable, tope_sugerido_claude, razon_sugerencia")
        .eq("portafolio_id", portafolio_id)
        .eq("mes", mes)
        .limit(1)
        .execute()
    )
    mes_data = mes_r.data[0] if mes_r.data else None
    tope_variable = float(mes_data["tope_variable"]) if mes_data and mes_data.get("tope_variable") else None

    # ── Invertido: posiciones RF abiertas del portafolio colchón ──
    pos_r = (
        supabase.table("posiciones_rf")
        .select("monto_ars")
        .eq("portafolio_id", portafolio_id)
        .eq("usuario_id", user_id)
        .eq("estado", "abierta")
        .execute()
    )
    invertido = sum(float(r["monto_ars"]) for r in (pos_r.data or []))

    # ── Mostrar status ──
    label_mes = mes_label(mes).capitalize()
    lines = [f"💳 *COLCHÓN DE TARJETAS — {label_mes}*\n"]

    lines.append(f"Comprometido (cuotas fijas):     ${comprometido:>12,.0f}")

    if tope_variable is not None:
        total_necesario = comprometido + tope_variable
        lines.append(f"Tope gastos variables con TC:    ${tope_variable:>12,.0f}")
        lines.append(f"{'─' * 42}")
        lines.append(f"TOTAL NECESARIO:                 ${total_necesario:>12,.0f}")
        lines.append("")
        if invertido >= total_necesario:
            lines.append(f"Invertido en renta fija:         ${invertido:>12,.0f}  ✅ Cubierto")
        else:
            falta = total_necesario - invertido
            lines.append(f"Invertido en renta fija:         ${invertido:>12,.0f}  ⚠️ Faltan ${falta:,.0f}")
        lines.append("")
        if gastado_variable > tope_variable:
            exceso = gastado_variable - tope_variable
            lines.append(f"Gastado variable c/TC:           ${gastado_variable:>12,.0f}  ⚠️ Exceso ${exceso:,.0f}")
        else:
            lines.append(f"Gastado variable c/TC:           ${gastado_variable:>12,.0f} / ${tope_variable:,.0f}")

        buttons = [[
            {"text": "📝 Cambiar tope", "callback_data": f"colchon_set:{portafolio_id}:{mes}"},
            {"text": "💰 Invertir capital", "callback_data": f"colchon_invest:{portafolio_id}"},
        ]]
        await _send(chat_id, "\n".join(lines), token, reply_markup={"inline_keyboard": buttons})
    else:
        # Sin tope fijado: sugerir o preguntar directamente
        lines.append(f"Tope gastos variables con TC:    _sin definir_")
        lines.append("")
        lines.append("_¿Cuánto querés destinar este mes para gastos nuevos con tarjeta?_")

        # Verificar si hay suficiente historial para que Claude sugiera
        sugerencia = await _obtener_sugerencia_claude(user_id, supabase)

        if sugerencia:
            monto_sug = sugerencia["monto"]
            razon = sugerencia.get("razon", "")
            lines.append(f"\n🤖 *Sugerencia de Claude:* ${monto_sug:,.0f}")
            if razon:
                lines.append(f"_{razon}_")

            # Guardar sugerencia en BD
            if mes_data:
                supabase.table("colchon_mensual").update({
                    "tope_sugerido_claude": monto_sug,
                    "razon_sugerencia": razon,
                }).eq("id", mes_data["id"]).execute()
            else:
                supabase.table("colchon_mensual").insert({
                    "usuario_id": user_id,
                    "portafolio_id": portafolio_id,
                    "mes": mes,
                    "tope_sugerido_claude": monto_sug,
                    "razon_sugerencia": razon,
                }).execute()

            buttons = [[
                {"text": f"✅ Aceptar ${monto_sug:,.0f}", "callback_data": f"colchon_aceptar:{portafolio_id}:{mes}:{int(monto_sug)}"},
                {"text": "✏️ Ingresar otro monto", "callback_data": f"colchon_set:{portafolio_id}:{mes}"},
            ]]
        else:
            if not mes_data:
                supabase.table("colchon_mensual").insert({
                    "usuario_id": user_id,
                    "portafolio_id": portafolio_id,
                    "mes": mes,
                }).execute()
            buttons = [[
                {"text": "💰 Fijar tope variable", "callback_data": f"colchon_set:{portafolio_id}:{mes}"},
            ]]

        await _send(chat_id, "\n".join(lines), token, reply_markup={"inline_keyboard": buttons})


async def _obtener_sugerencia_claude(user_id: str, supabase) -> dict | None:
    """
    Llama a Claude on-demand para sugerir el tope variable del mes.
    Solo si hay historial de al menos 2 meses de gastos con tarjeta.
    Retorna {monto, razon} o None.
    """
    from lib.claude_invest import sugerir_tope_tarjetas

    # Obtener historial de gastos variables con tarjeta (últimos 4 meses)
    gastos_r = (
        supabase.table("movimientos")
        .select("monto, descripcion, mes_resumen")
        .eq("usuario_id", user_id)
        .eq("tipo", "gasto")
        .neq("estado", "anulado")
        .not_.is_("tarjeta_id", "null")
        .not_.is_("mes_resumen", "null")
        .order("fecha", desc=True)
        .limit(200)
        .execute()
    )
    gastos = [
        r for r in (gastos_r.data or [])
        if not _CUOTA_RE.search(r.get("descripcion", ""))
    ]

    # Agrupar por mes_resumen
    por_mes: dict[str, float] = {}
    for g in gastos:
        mes = g.get("mes_resumen", "")
        if mes:
            por_mes[mes] = por_mes.get(mes, 0.0) + float(g["monto"])

    # Solo sugerir si hay historial de >= 2 meses
    meses_hist = sorted(por_mes.keys())
    mes_actual = _MES_ACTUAL()
    meses_hist = [m for m in meses_hist if m < mes_actual]

    if len(meses_hist) < 2:
        return None

    # Obtener presupuestos del mes actual para contexto
    pres_r = supabase.table("presupuestos").select("monto").eq("usuario_id", user_id).eq("mes", mes_actual).execute()
    presupuesto_total = sum(float(r["monto"]) for r in (pres_r.data or []))

    historial = {m: por_mes[m] for m in meses_hist[-4:]}  # max 4 meses
    return sugerir_tope_tarjetas(historial, presupuesto_total)


async def handle_colchon_callback(
    parts: list[str],
    callback_id: str,
    chat_id: int,
    message_id: int,
    user_id: str,
    supabase,
    token: str,
) -> bool:
    """
    Maneja:
      colchon_set:{portafolio_id}:{mes}         → pide monto por texto (estado transitorio)
      colchon_aceptar:{portafolio_id}:{mes}:{n} → acepta sugerencia de Claude
      colchon_ajustar:{portafolio_id}:{mes}:{n} → suma exceso al tope
      colchon_dejar                              → dismiss alerta de exceso
      colchon_invest:{portafolio_id}             → redirige a /opciones_rf
    """
    if parts[0] == "colchon_dejar":
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id, "✓ Exceso registrado. Podés ajustar el colchón cuando quieras con /colchon.", token)
        return True

    if parts[0] == "colchon_invest" and len(parts) == 2:
        if token:
            await _answer_callback(callback_id, token)
            await _send(chat_id, "Para invertir el capital del colchón, usá /opciones_rf y elegí un instrumento.", token, parse_mode="")
        return True

    if parts[0] == "colchon_aceptar" and len(parts) == 4:
        portafolio_id = int(parts[1])
        mes = parts[2]
        monto = float(parts[3])

        _upsert_tope(supabase, user_id, portafolio_id, mes, monto)
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"✅ Tope fijado: ${monto:,.0f} para gastos variables con tarjeta en {mes_label(mes)}.\n\n"
                f"Te avisaré si lo superás al registrar un gasto.",
                token)
        return True

    if parts[0] == "colchon_ajustar" and len(parts) == 4:
        portafolio_id = int(parts[1])
        mes = parts[2]
        exceso = float(parts[3])

        mes_r = (
            supabase.table("colchon_mensual")
            .select("tope_variable")
            .eq("portafolio_id", portafolio_id)
            .eq("mes", mes)
            .limit(1)
            .execute()
        )
        tope_actual = float(mes_r.data[0]["tope_variable"]) if mes_r.data and mes_r.data[0].get("tope_variable") else 0.0
        nuevo_tope = tope_actual + exceso
        _upsert_tope(supabase, user_id, portafolio_id, mes, nuevo_tope)

        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"✅ Tope ajustado a ${nuevo_tope:,.0f}.\n\n"
                f"Recordá invertir ${exceso:,.0f} más en el colchón para seguir cubierto. "
                f"Usá /opciones_rf para hacerlo.",
                token)
        return True

    if parts[0] == "colchon_set" and len(parts) == 3:
        portafolio_id = int(parts[1])
        mes = parts[2]
        # Guardar estado de espera de texto con un registro sin tope (o actualizar)
        mes_r = (
            supabase.table("colchon_mensual")
            .select("id")
            .eq("portafolio_id", portafolio_id)
            .eq("mes", mes)
            .limit(1)
            .execute()
        )
        if not mes_r.data:
            supabase.table("colchon_mensual").insert({
                "usuario_id": user_id,
                "portafolio_id": portafolio_id,
                "mes": mes,
            }).execute()

        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(
                chat_id, message_id,
                f"💰 ¿Cuánto querés destinar para gastos variables con tarjeta en {mes_label(mes)}?\n\n"
                f"_Respondé con un número (ej: 80000)_",
                token,
            )
        return True

    return False


def _upsert_tope(supabase, user_id: str, portafolio_id: int, mes: str, monto: float) -> None:
    existing = (
        supabase.table("colchon_mensual")
        .select("id")
        .eq("portafolio_id", portafolio_id)
        .eq("mes", mes)
        .limit(1)
        .execute()
    )
    if existing.data:
        supabase.table("colchon_mensual").update({"tope_variable": monto}).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase.table("colchon_mensual").insert({
            "usuario_id": user_id,
            "portafolio_id": portafolio_id,
            "mes": mes,
            "tope_variable": monto,
        }).execute()


async def handle_colchon_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    """
    Detecta si el usuario está respondiendo con el monto del tope variable
    (cuando hay un colchon_mensual sin tope_variable para el mes actual).
    Retorna True si consumió el mensaje.
    """
    import re as _re
    num_m = _re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
    if not num_m:
        return False

    supabase = get_supabase()
    mes = _MES_ACTUAL()

    # Buscar colchón del usuario
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
        return False

    portafolio_id = port_r.data[0]["id"]

    # Buscar mes sin tope_variable
    mes_r = (
        supabase.table("colchon_mensual")
        .select("id, tope_variable")
        .eq("portafolio_id", portafolio_id)
        .eq("mes", mes)
        .limit(1)
        .execute()
    )
    if not mes_r.data or mes_r.data[0].get("tope_variable") is not None:
        return False  # No hay pendiente de tope

    monto = float(num_m.group().replace(",", "."))
    if monto <= 0:
        return False

    supabase.table("colchon_mensual").update({"tope_variable": monto}).eq("id", mes_r.data[0]["id"]).execute()
    await _send(
        chat_id,
        f"✅ Tope variable fijado: *${monto:,.0f}* para gastos con tarjeta en {mes_label(mes)}.\n\n"
        f"Te avisaré en el momento si lo superás.",
        token,
    )
    return True
