"""
Fase 4 — Selección de activos RV para monitorear en un portafolio.

Flujo:
  1. Al activar portafolio (si RV% > 0): Claude sugiere activos → pre-seleccionados en portafolio_activos
  2. Mensaje con toggles ✅/⬜ por activo — cada tap persiste directo en DB
  3. Botón confirmar → cierra flujo
  4. El cron usa portafolio_activos para generar señales RSI/EMA

También se activa con /activos para gestionar activos de un portafolio existente.
"""
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message

_TIPO_ICON = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷"}
_TIPO_LABEL = {"crypto": "Crypto USD", "cedear": "CEDEAR", "accion_ar": "Acción AR"}

_TIPO_OBJETIVOS = {
    "conservador": ["cobertura"],
    "pasivo":      ["ingresos_pasivos"],
    "crecimiento": ["crecimiento"],
    "oportunista": ["crecimiento", "meta_especifica"],
}
_TIPO_FALLBACK = {
    "conservador": ["AAPL", "MSFT"],
    "pasivo":      ["GGAL", "AAPL"],
    "crecimiento": ["BTC", "AAPL"],
    "oportunista": ["BTC", "ETH"],
}


async def sugerir_activos_rv(chat_id: int, token: str, portafolio: dict) -> None:
    """
    Sugiere activos RV al finalizar el wizard (si RV% > 0).
    Pre-inserta sugeridos en portafolio_activos y muestra el selector.
    """
    from lib.claude_invest import sugerir_activos_para_perfil
    from lib.market_data import fetch_dolar_precio

    rf_pct = portafolio.get("asignacion_rf_pct") or 0
    if rf_pct >= 100:
        return

    rv_pct = 100 - rf_pct
    portafolio_id = portafolio["id"]
    tipo = portafolio.get("tipo", "crecimiento")

    # Capital total en USD: considera ambas monedas (dual-currency)
    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = (dolar_data.get("precio") if dolar_data else None) or 1200
    capital_usd = portafolio.get("capital_usd") or 0
    capital_ars_raw = portafolio.get("capital_ars") or 0
    capital_total_usd = capital_usd + capital_ars_raw / dolar_mep
    capital_rv_usd = capital_total_usd * rv_pct / 100

    supabase = get_supabase()
    activos_r = (
        supabase.table("activos")
        .select("id, codigo, nombre, tipo, moneda")
        .eq("activo", True)
        .neq("tipo", "dolar")
        .execute()
    )
    activos_disponibles = activos_r.data or []
    if not activos_disponibles:
        return

    # Llamar a Claude para sugerencias
    objetivo = portafolio.get("objetivo") or ""
    plazo = portafolio.get("plazo") or "mediano"
    moneda = portafolio.get("moneda_preferida") or "USD"
    objetivos = _TIPO_OBJETIVOS.get(tipo, ["crecimiento"])

    sugerencia = sugerir_activos_para_perfil(
        objetivos=objetivos,
        plazo=plazo,
        capital=capital_rv_usd * dolar_mep,  # ARS al MEP real
        descripcion=objetivo,
        activos_disponibles=activos_disponibles,
        moneda_preferida=moneda,
    )

    # Codigos sugeridos + razones por Claude
    razon_map: dict[str, str] = {}
    codigos_sugeridos: set[str] = set()
    if sugerencia:
        for a in sugerencia.get("activos_sugeridos", []):
            codigos_sugeridos.add(a["codigo"])
            razon_map[a["codigo"]] = a.get("razon", "")

    # Fallback si Claude falla
    if not codigos_sugeridos:
        codigos_sugeridos = set(_TIPO_FALLBACK.get(tipo, ["AAPL"]))

    # Pre-insertar sugeridos en portafolio_activos
    activos_map = {a["codigo"]: a for a in activos_disponibles}
    for codigo in codigos_sugeridos:
        activo = activos_map.get(codigo)
        if not activo:
            continue
        existing = (
            supabase.table("portafolio_activos")
            .select("id")
            .eq("portafolio_id", portafolio_id)
            .eq("activo_id", activo["id"])
            .execute()
        )
        if not existing.data:
            supabase.table("portafolio_activos").insert({
                "usuario_id": portafolio["usuario_id"],
                "portafolio_id": portafolio_id,
                "activo_id": activo["id"],
            }).execute()

    resumen = sugerencia.get("resumen", "") if sugerencia else ""
    await _send_selector_rv(
        chat_id, token, portafolio_id, portafolio,
        activos_disponibles, razon_map, resumen,
    )


async def _send_selector_rv(
    chat_id: int,
    token: str,
    portafolio_id: int,
    portafolio: dict,
    activos_disponibles: list[dict],
    razon_map: dict[str, str],
    resumen: str,
    message_id: int | None = None,
) -> None:
    """Construye y envía (o edita) el mensaje de selección de activos RV."""
    supabase = get_supabase()

    sel_r = (
        supabase.table("portafolio_activos")
        .select("activo_id")
        .eq("portafolio_id", portafolio_id)
        .execute()
    )
    seleccionados = {row["activo_id"] for row in (sel_r.data or [])}

    rf_pct = portafolio.get("asignacion_rf_pct") or 0
    rv_pct = 100 - rf_pct
    capital_usd = portafolio.get("capital_usd") or 0
    capital_rv_usd = capital_usd * rv_pct / 100

    lines = [
        f"📈 *Renta Variable — {rv_pct:.0f}% de tu portafolio*",
        f"Capital RV: ~${capital_rv_usd:,.0f} USD",
    ]
    if resumen:
        lines.append(f"\n_{resumen}_")
    lines.append("\n*Elegí qué activos querés monitorear:*")

    # Sugeridos primero (con razón), luego el resto
    sugeridos = [a for a in activos_disponibles if a["codigo"] in razon_map]
    otros = [a for a in activos_disponibles if a["codigo"] not in razon_map]

    for activo in sugeridos:
        sel = "✅" if activo["id"] in seleccionados else "⬜"
        icon = _TIPO_ICON.get(activo.get("tipo", ""), "📈")
        label = _TIPO_LABEL.get(activo.get("tipo", ""), "")
        razon = razon_map.get(activo["codigo"], "")
        lines.append(f"{sel} {icon} *{activo['codigo']}* · {activo['nombre']} _{label}_")
        if razon:
            lines.append(f"   ↳ _{razon}_")

    if otros:
        lines.append("")
        for activo in otros:
            sel = "✅" if activo["id"] in seleccionados else "⬜"
            icon = _TIPO_ICON.get(activo.get("tipo", ""), "📈")
            label = _TIPO_LABEL.get(activo.get("tipo", ""), "")
            lines.append(f"{sel} {icon} *{activo['codigo']}* · {activo['nombre']} _{label}_")

    n_sel = len(seleccionados)
    lines.append("\n_El cron monitorea señales RSI/EMA cada 30 min y te avisa cuando haya oportunidad._")

    # Botones de toggle (3 por fila)
    buttons: list[list[dict]] = []
    fila: list[dict] = []
    for activo in activos_disponibles:
        sel = "✅" if activo["id"] in seleccionados else "⬜"
        fila.append({
            "text": f"{sel} {activo['codigo']}",
            "callback_data": f"rv_toggle:{portafolio_id}:{activo['id']}",
        })
        if len(fila) == 3:
            buttons.append(fila)
            fila = []
    if fila:
        buttons.append(fila)

    if n_sel > 0:
        buttons.append([{
            "text": f"✅ Listo — monitorear {n_sel} activo{'s' if n_sel != 1 else ''}",
            "callback_data": f"rv_confirmar:{portafolio_id}",
        }])

    markup = {"inline_keyboard": buttons}
    text = "\n".join(lines)

    if message_id:
        await _edit_message(chat_id, message_id, text, token, reply_markup=markup)
    else:
        await _send(chat_id, text, token, reply_markup=markup)


async def handle_activos_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Comando /activos — gestiona activos RV de un portafolio existente."""
    supabase = get_supabase()

    ports = (
        supabase.table("portafolios")
        .select("id, tipo, nombre_personalizado, nombre_sugerido, capital_usd, asignacion_rf_pct, objetivo, plazo, moneda_preferida, usuario_id")
        .eq("usuario_id", user_id)
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .execute()
    )
    portafolios = ports.data or []

    if not portafolios:
        await _send(chat_id, "No tenés portafolios activos. Usá /portafolio_nuevo para crear uno.", token, parse_mode="")
        return

    activos_r = (
        supabase.table("activos")
        .select("id, codigo, nombre, tipo, moneda")
        .eq("activo", True)
        .neq("tipo", "dolar")
        .execute()
    )
    activos_disponibles = activos_r.data or []

    if len(portafolios) == 1:
        portafolio = portafolios[0]
        rf_pct = portafolio.get("asignacion_rf_pct") or 0
        if rf_pct >= 100:
            await _send(chat_id, "Tu portafolio es 100% Renta Fija. Para agregar activos RV, modificá el % RF con /portafolio_nuevo.", token)
            return
        await _send_selector_rv(chat_id, token, portafolio["id"], portafolio, activos_disponibles, {}, "")
    else:
        # Múltiples portafolios: mostrar selector
        _TIPO_EMOJI = {"conservador": "🛡️", "pasivo": "💰", "crecimiento": "📈", "oportunista": "🎯"}
        buttons = []
        for p in portafolios:
            rf_pct = p.get("asignacion_rf_pct") or 0
            if rf_pct >= 100:
                continue
            nombre = p.get("nombre_personalizado") or p.get("nombre_sugerido") or p["tipo"].capitalize()
            emoji = _TIPO_EMOJI.get(p.get("tipo", ""), "📊")
            rv_pct = 100 - rf_pct
            buttons.append([{
                "text": f"{emoji} {nombre} (RV {rv_pct:.0f}%)",
                "callback_data": f"rv_sel_port:{p['id']}",
            }])
        if not buttons:
            await _send(chat_id, "Todos tus portafolios son 100% RF. No hay activos RV para gestionar.", token)
            return
        await _send(chat_id, "¿De qué portafolio querés gestionar los activos RV?", token, reply_markup={"inline_keyboard": buttons})


async def handle_rv_callback(
    parts: list[str],
    callback_id: str,
    chat_id: int,
    message_id: int,
    user_id: str,
    supabase,
    token: str,
) -> bool:
    """
    Maneja rv_toggle, rv_confirmar, rv_sel_port.
    Retorna True si consumió el callback.
    """
    if parts[0] == "rv_sel_port" and len(parts) == 2:
        portafolio_id = int(parts[1])
        port_r = supabase.table("portafolios").select("*").eq("id", portafolio_id).eq("usuario_id", user_id).limit(1).execute()
        if not port_r.data:
            await _answer_callback(callback_id, token)
            return True
        portafolio = port_r.data[0]

        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda").eq("activo", True).neq("tipo", "dolar").execute()
        activos_disponibles = activos_r.data or []

        await _answer_callback(callback_id, token)
        await _send_selector_rv(
            chat_id, token, portafolio_id, portafolio,
            activos_disponibles, {}, "", message_id=message_id,
        )
        return True

    if parts[0] == "rv_toggle" and len(parts) == 3:
        portafolio_id = int(parts[1])
        activo_id = int(parts[2])

        port_r = supabase.table("portafolios").select("*").eq("id", portafolio_id).eq("usuario_id", user_id).limit(1).execute()
        if not port_r.data:
            await _answer_callback(callback_id, token)
            return True
        portafolio = port_r.data[0]

        # Toggle: si existe → eliminar, si no → insertar
        existing = (
            supabase.table("portafolio_activos")
            .select("id")
            .eq("portafolio_id", portafolio_id)
            .eq("activo_id", activo_id)
            .execute()
        )
        if existing.data:
            supabase.table("portafolio_activos").delete().eq("portafolio_id", portafolio_id).eq("activo_id", activo_id).execute()
        else:
            supabase.table("portafolio_activos").insert({
                "usuario_id": user_id,
                "portafolio_id": portafolio_id,
                "activo_id": activo_id,
            }).execute()

        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda").eq("activo", True).neq("tipo", "dolar").execute()
        activos_disponibles = activos_r.data or []

        await _answer_callback(callback_id, token)
        await _send_selector_rv(
            chat_id, token, portafolio_id, portafolio,
            activos_disponibles, {}, "", message_id=message_id,
        )
        return True

    if parts[0] == "rv_confirmar" and len(parts) == 2:
        portafolio_id = int(parts[1])
        sel_r = (
            supabase.table("portafolio_activos")
            .select("activo_id, activos(codigo)")
            .eq("portafolio_id", portafolio_id)
            .execute()
        )
        rows = sel_r.data or []
        n = len(rows)
        codigos = [r.get("activos", {}).get("codigo", "?") for r in rows]

        await _answer_callback(callback_id, token)
        await _edit_message(
            chat_id, message_id,
            f"✅ *{n} activo{'s' if n != 1 else ''} en seguimiento: {', '.join(codigos)}*\n\n"
            f"El cron los revisa cada 30 min. Cuando haya señal RSI, te aviso por acá.\n"
            f"Usá /activos para cambiar la selección en cualquier momento.",
            token,
        )
        return True

    return False
