"""
Handler para /plan_renta — Asistente inteligente de distribución de RF.
Flujo: capital → objetivo de renta → broker → generación de planes.
"""
import re
from lib.supabase_client import get_supabase
from ..tg import _send

# Estados propios del flujo /plan_renta (distinto de los estados del wizard portafolio_nuevo)
_PLAN_RENTA_ESTADOS = (
    "pidiendo_capital", "pidiendo_objetivo", "pidiendo_broker",
    "eligiendo_plan", "instrucciones_enviadas",
)


async def _ask_capital_plan(chat_id: int, token: str) -> None:
    """Pregunta capital inicial en USD."""
    await _send(
        chat_id,
        "💰 *Plan de Renta Fija*\n\n"
        "¿Con cuánto capital USD querés empezar?\n\n"
        "_Ej: 150, 500, 1000_",
        token,
    )


async def _ask_objetivo_renta(chat_id: int, token: str) -> None:
    """Pregunta objetivo de renta mensual."""
    await _send(
        chat_id,
        "💵 ¿Cuánto querés generar por mes? (en USD o ARS)\n\n"
        "_Ej: 20 USD, 5000 ARS, máximo posible_",
        token,
    )


async def _ask_broker(chat_id: int, token: str) -> None:
    """Pregunta en qué broker opera el usuario."""
    buttons = [
        [
            {"text": "IOL (Acciones + Bonos)", "callback_data": "plan_broker:iol"},
            {"text": "Balanz (Bonos)", "callback_data": "plan_broker:balanz"},
        ],
        [
            {"text": "Santander (Cauciones)", "callback_data": "plan_broker:santander"},
            {"text": "Otro", "callback_data": "plan_broker:otro"},
        ],
    ]
    await _send(
        chat_id,
        "🏦 ¿Dónde tenés cuenta para operar?\n\n"
        "(Esto afecta qué instrumentos podés comprar)",
        token,
        reply_markup={"inline_keyboard": buttons},
    )


async def _generar_planes(
    capital_usd: float,
    objetivo_renta_usd: float | None,
    chat_id: int,
    token: str,
    dolar_mep: float,
    tna_caucion: float,
    tir_bonos: float,
    user_id: str,
) -> None:
    """Genera 2-3 planes automáticos según perfil del usuario."""
    supabase = get_supabase()

    # Rendimiento esperado mensual en ARS: TNA/12
    renta_caucion_mensual_ars = (tna_caucion / 100 / 12) * capital_usd * dolar_mep
    renta_caucion_mensual_usd = (tna_caucion / 100 / 12) * capital_usd

    # Rendimiento en USD (bonos)
    renta_bonos_mensual_usd = (tir_bonos / 100 / 12) * capital_usd

    lines = [f"📊 *Planes de distribución para USD ${capital_usd:,.0f}*\n"]

    # PLAN A: 100% Caución (máxima liquidez, máximo riesgo de devaluación)
    lines.append(
        f"🟢 *PLAN A — Caución (Máxima liquidez)*\n"
        f"  100% Caución 7D\n"
        f"  Renta estimada: USD ${renta_caucion_mensual_usd:.2f}/mes\n"
        f"  Renta en ARS: ${renta_caucion_mensual_ars:,.0f}/mes\n"
        f"  Riesgo: Devaluación ARS\n"
        f"  Ventaja: Rescatás cuando quieras\n\n"
    )

    # PLAN B: 50/50 (Balanceado)
    capital_caucion = capital_usd / 2
    capital_bonos = capital_usd / 2
    renta_b_usd = (capital_caucion * tna_caucion / 100 / 12) + (capital_bonos * tir_bonos / 100 / 12)
    renta_b_ars = capital_caucion * dolar_mep * tna_caucion / 100 / 12

    lines.append(
        f"🟡 *PLAN B — Balanceado*\n"
        f"  50% Caución 7D (USD ${capital_caucion:,.0f})\n"
        f"  50% AL30 (USD ${capital_bonos:,.0f})\n"
        f"  Renta estimada: USD ${renta_b_usd:.2f}/mes\n"
        f"  Renta en ARS: ${renta_b_ars:,.0f}/mes\n"
        f"  Riesgo: Moderado\n"
        f"  Ventaja: Diversificación\n\n"
    )

    # PLAN C: 100% Bonos USD (máxima protección, sin riesgo de devaluación)
    lines.append(
        f"🔵 *PLAN C — Bonos USD (Protección)*\n"
        f"  100% AL30 + GD30\n"
        f"  Renta estimada: USD ${renta_bonos_mensual_usd:.2f}/mes\n"
        f"  Riesgo: Bajo (en USD)\n"
        f"  Ventaja: Sin devaluación\n"
        f"  Desventaja: Menos renta\n\n"
    )

    lines.append("*¿Cuál te interesa?* Escribí: A, B o C")

    # Guardar estado en cache (preferentemente en BD con estado temporal)
    supabase.table("portafolios").insert({
        "usuario_id": user_id,
        "tipo": "conservador",
        "estado_wizard": "eligiendo_plan",
        "capital_usd": capital_usd,
        "objetivo": f"Renta {objetivo_renta_usd} USD/mes" if objetivo_renta_usd else "Máxima",
        "activo": False,
    }).execute()

    await _send(chat_id, "\n".join(lines), token)


async def handle_plan_renta_text(text: str, user_id: str, chat_id: int, token: str) -> bool:
    """Procesa texto en el flujo de /plan_renta."""
    supabase = get_supabase()

    # Buscar si hay un plan_renta en progreso (identificado por estado_wizard)
    result = (
        supabase.table("portafolios")
        .select("*")
        .eq("usuario_id", user_id)
        .eq("activo", False)
        .in_("estado_wizard", list(_PLAN_RENTA_ESTADOS))
        .order("id", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        # No hay plan_renta en progreso, ignorar
        return False

    plan = result.data[0]
    estado = plan.get("estado_wizard")

    # ── Recolectar capital ──
    if estado == "pidiendo_capital":
        m = re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
        if not m:
            await _send(chat_id, "No entendí el monto. Escribí un número, ej: _150_", token)
            return True

        capital = float(m.group().replace(",", "."))
        supabase.table("portafolios").update({
            "capital_usd": capital,
            "estado_wizard": "pidiendo_objetivo",
        }).eq("id", plan["id"]).execute()

        await _ask_objetivo_renta(chat_id, token)
        return True

    # ── Recolectar objetivo ──
    if estado == "pidiendo_objetivo":
        objetivo_txt = text.strip()[:100]
        supabase.table("portafolios").update({
            "objetivo": objetivo_txt,
            "estado_wizard": "pidiendo_broker",
        }).eq("id", plan["id"]).execute()

        await _ask_broker(chat_id, token)
        return True

    # ── Elegir plan (A, B, C) ──
    if estado == "eligiendo_plan":
        opcion = text.strip().upper()
        if opcion not in ("A", "B", "C"):
            await _send(chat_id, "Escribí A, B o C para elegir el plan.", token, parse_mode="")
            return True

        capital_usd = plan.get("capital_usd", 100)
        broker = plan.get("nombre_personalizado", "otro")  # Guardamos broker aquí

        # Generar instrucciones según plan elegido
        if opcion == "A":
            lines = [
                f"🟢 *Plan A — Caución (100%)*\n",
                f"Capital: USD ${capital_usd:,.0f}\n\n",
                "📋 *Registra esto en orden:*\n",
                f"`puse {capital_usd * 1400:.0f} en caución 7 días`",
            ]
            broker_hint = f"(en {broker.upper()})" if broker != "otro" else ""
            lines.append(f"\n_Convertimos USD ${capital_usd:,.0f} @ ~$1.400 ARS/USD {broker_hint}_")

        elif opcion == "B":
            capital_50 = capital_usd / 2
            lines = [
                f"🟡 *Plan B — Balanceado (50/50)*\n",
                f"Capital: USD ${capital_usd:,.0f}\n\n",
                "📋 *Registra esto en orden:*\n",
                f"`puse {capital_50 * 1400:.0f} en caución 7 días`\n",
                f"`AL30 {capital_50 * 1400:.0f}`",
            ]
            lines.append(f"\n_Caución en {broker.upper()}, Bonos en IOL_")

        else:  # C
            lines = [
                f"🔵 *Plan C — Bonos USD (100%)*\n",
                f"Capital: USD ${capital_usd:,.0f}\n\n",
                "📋 *Registra esto en orden:*\n",
                f"`AL30 {capital_usd * 1400 * 0.5:.0f}`\n",
                f"`GD30 {capital_usd * 1400 * 0.5:.0f}`",
            ]
            lines.append(f"\n_(En IOL)_")

        lines.append(
            f"\n✅ Una vez registrado, usá `/liquidez` para ver tu posición.\n"
            f"Te enviaré alertas semanales con tu rendimiento."
        )

        # Guardar plan elegido en BD
        supabase.table("portafolios").update({
            "nombre_personalizado": f"Plan{opcion}_{broker}",
            "broker_preferido": broker,
            "estado_wizard": "instrucciones_enviadas",
        }).eq("id", plan["id"]).execute()

        await _send(chat_id, "\n".join(lines), token)
        return True

    return False


async def handle_plan_renta_callback(parts: list[str], callback_id: str, chat_id: int, user_id: str, token: str) -> bool:
    """Maneja callbacks del plan_renta."""
    from ..tg import _answer_callback
    from lib.market_data import fetch_dolar_precio
    from lib.rf_analysis import analizar_carry_trade

    supabase = get_supabase()

    if parts[0] != "plan_broker":
        return False

    broker = parts[1] if len(parts) > 1 else "otro"

    # Obtener plan en progreso
    result = (
        supabase.table("portafolios")
        .select("*")
        .eq("usuario_id", user_id)
        .eq("activo", False)
        .in_("estado_wizard", list(_PLAN_RENTA_ESTADOS))
        .order("id", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        await _answer_callback(callback_id, token)
        return True

    plan = result.data[0]
    capital_usd = plan.get("capital_usd", 100)

    # Obtener datos de mercado
    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_data["precio"] if dolar_data else 1000

    caucion_r = supabase.table("instrumentos_rf").select("tna_actual").eq("codigo", "CAUCION_7D").limit(1).execute()
    tna_caucion = caucion_r.data[0]["tna_actual"] if caucion_r.data else 35.0

    # Asumir TIR de bonos ~4-5% (simplificado)
    tir_bonos = 4.5

    # Generar planes
    await _generar_planes(
        capital_usd,
        None,
        chat_id,
        token,
        dolar_mep,
        tna_caucion,
        tir_bonos,
        user_id,
    )

    # Actualizar plan con broker
    supabase.table("portafolios").update({
        "nombre_personalizado": broker,  # Reutilizar para guardar broker
        "estado_wizard": "eligiendo_plan",
    }).eq("id", plan["id"]).execute()

    await _answer_callback(callback_id, token)
    return True
