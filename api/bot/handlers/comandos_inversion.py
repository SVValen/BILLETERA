import json as _json
from lib.supabase_client import get_supabase
from ..tg import _send


async def _handle_inversiones_cmd(user_id: str, chat_id: int, token: str) -> None:
    from .wizard_inversion import _send_tipo_keyboard
    from lib.market_data import fetch_dolar_precio
    from lib.rf_analysis import analizar_carry_trade
    supabase = get_supabase()

    # Verificar si tiene portafolios activos
    port_r = supabase.table("portafolios").select("id").eq("usuario_id", user_id).eq("activo", True).eq("estado_wizard", "activo").limit(1).execute()
    if not port_r.data:
        await _send(chat_id, "No tenés portafolios activos. Creá uno con /portafolio_nuevo.", token, parse_mode="")
        return

    # Mostrar todos los portafolios con sus recomendaciones pendientes
    ports_r = supabase.table("portafolios").select("id, tipo, nombre_personalizado, nombre_sugerido, capital_usd, asignacion_rf_pct").eq("usuario_id", user_id).eq("activo", True).eq("estado_wizard", "activo").execute()
    portafolios = ports_r.data or []

    _TIPO_EMOJI = {"conservador": "🛡️", "pasivo": "💰", "crecimiento": "📈", "oportunista": "🎯"}
    lines = ["📈 *Inversiones*\n"]

    for port in portafolios:
        nombre = port.get("nombre_personalizado") or port.get("nombre_sugerido") or port["tipo"].capitalize()
        emoji = _TIPO_EMOJI.get(port["tipo"], "📊")
        capital = port.get("capital_usd") or 0
        rf = port.get("asignacion_rf_pct") or 0
        lines.append(f"{emoji} *{nombre}* — ${capital:,.0f} USD | RF {rf:.0f}%")

    # ─── RECOMENDACIONES DE RENTA VARIABLE ───
    recs_r = (
        supabase.table("recomendaciones")
        .select("*, activos(codigo, nombre)")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente")
        .order("generado_at", desc=True)
        .limit(5)
        .execute()
    )
    if recs_r.data:
        lines.append(f"\n⏳ *{len(recs_r.data)} recomendación(es) RV pendiente(s):*")
        for r in recs_r.data:
            a = r.get("activos") or {}
            icon = "🟢" if r["accion"] == "comprar" else "🔴"
            lines.append(f"{icon} {r['accion'].upper()} {a.get('codigo', '?')} — confianza {r['confianza']}/10")
    else:
        lines.append("\n✅ Sin señales RV ahora. El cron revisa cada 30 minutos.")

    # ─── ANÁLISIS DE RENTA FIJA (Carry Trade) ───
    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_data["precio"] if dolar_data else None
    
    if dolar_mep:
        caucion_r = supabase.table("instrumentos_rf").select("tna_actual").eq("codigo", "CAUCION_7D").limit(1).execute()
        tna_ref = caucion_r.data[0]["tna_actual"] if caucion_r.data and caucion_r.data[0].get("tna_actual") else None
        
        if tna_ref:
            carry = analizar_carry_trade(tna_ref, dolar_mep, None)
            icon = "🟢" if carry["accion"] == "entrar" else "🔴" if carry["accion"] == "salir" else "🟡"
            lines.append(
                f"\n{icon} *Carry Trade RF*\n"
                f"  Caución 7D: {tna_ref:.1f}% TNA ({carry['tna_mensual']:.1f}%/mes)\n"
                f"  Carry neto: {carry['carry_mensual']:+.1f}% — {carry['accion'].upper()}\n"
                f"  Dólar MEP: ${dolar_mep:,.2f} ARS"
            )

            # Sugerir opciones RF según carry trade
            lines.append(f"\n💡 *Opciones RF disponibles:*")
            if carry["accion"] == "entrar":
                lines.append("  • Caución 7D — renovable, máxima liquidez")
                lines.append("  • Lecaps — con plazo, rentabilidad creciente")
            else:
                lines.append("  • AL30, GD30 — en USD, protección contra devaluación")

    stats_r = supabase.table("decisiones_inversion").select("resultado, accion").eq("usuario_id", user_id).execute()
    decisiones = stats_r.data or []
    aceptadas = [d for d in decisiones if d["accion"] == "aceptada"]
    exitosas = [d for d in aceptadas if d.get("resultado") == "exitoso"]
    if aceptadas:
        winrate = round(len(exitosas) / len(aceptadas) * 100)
        lines.append(f"\n🎯 Winrate RV: {winrate}% ({len(exitosas)}/{len(aceptadas)})")

    lines.append("\n_/portafolio — distribución | /liquidez — detalle RF | /precios — cotizaciones_")
    await _send(chat_id, "\n".join(lines), token)


async def _handle_precios_cmd(user_id: str, chat_id: int, token: str) -> None:
    from lib.market_data import fetch_coingecko_precio, fetch_dolar_precio, fetch_iol_precio

    await _send(chat_id, "📡 Consultando mercados...", token, parse_mode="")

    lines = ["📊 *Precios de mercado*\n"]

    try:
        btc = await fetch_coingecko_precio("BTCUSDT")
        lines.append(f"₿ *BTC* — ${btc['precio']:,.0f} USD" if btc else "₿ *BTC* — sin datos")
    except Exception:
        lines.append("₿ *BTC* — error")
    try:
        eth = await fetch_coingecko_precio("ETHUSDT")
        if eth:
            lines.append(f"   *ETH* — ${eth['precio']:,.0f} USD")
    except Exception:
        pass

    lines.append("")

    for tipo, label in [("oficial", "Oficial"), ("blue", "Blue"), ("cripto", "Cripto")]:
        try:
            d = await fetch_dolar_precio(tipo)
            lines.append(f"💵 *{label}* — ${d['precio']:,.2f} ARS" if d else f"💵 {label} — sin datos")
        except Exception:
            lines.append(f"💵 {label} — error")

    supabase = get_supabase()
    # Obtener todos los activos monitoreados por el usuario (de cualquier portafolio)
    pa_r = supabase.table("portafolio_activos").select("activo_id").eq("usuario_id", user_id).execute()
    activos_ids = list({row["activo_id"] for row in (pa_r.data or [])})

    if activos_ids:
        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, fuente, simbolo_fuente, moneda").in_("id", activos_ids).execute()
        activos = activos_r.data or []

        tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}

        lines.append("")
        lines.append("*Tus activos:*")
        for activo in activos:
            icon = tipo_icon.get(activo.get("tipo", ""), "📈")
            codigo = activo["codigo"]
            moneda = activo.get("moneda", "ARS")
            try:
                from lib.market_data import fetch_precio_activo
                precio_data = await fetch_precio_activo(activo)
                if precio_data:
                    precio = precio_data["precio"]
                    mon = precio_data.get("moneda", moneda)
                    lines.append(f"{icon} *{codigo}* — ${precio:,.2f} {mon}")
                else:
                    lines.append(f"{icon} *{codigo}* — sin datos")
            except Exception:
                lines.append(f"{icon} *{codigo}* — error")
    else:
        lines.append("\n_No tenés activos en tu portafolio. Usá /inversiones para configurar._")

    await _send(chat_id, "\n".join(lines), token)


async def _handle_liquidez_cmd(user_id: str, chat_id: int, token: str, portafolio: dict | None = None) -> None:
    from lib.market_data import fetch_dolar_precio
    from lib.rf_analysis import analizar_carry_trade, calcular_rendimiento_usd, calcular_allocation

    supabase = get_supabase()

    capital_usd = portafolio.get("capital_usd") if portafolio else None
    asignacion_obj = portafolio.get("asignacion_rf_pct") or 30 if portafolio else 30
    portafolio_id = portafolio.get("id") if portafolio else None
    nombre_port = portafolio.get("nombre_personalizado") or portafolio.get("nombre_sugerido") or "Portafolio" if portafolio else "Portafolio"

    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_data["precio"] if dolar_data else None

    pos_q = supabase.table("posiciones_rf").select("*, instrumentos_rf(nombre, tipo, tna_actual)").eq("usuario_id", user_id).eq("estado", "abierta")
    if portafolio_id:
        pos_q = pos_q.eq("portafolio_id", portafolio_id)
    posiciones = (pos_q.execute()).data or []

    lines = [f"💼 *Liquidez y RF — {nombre_port}*\n"]

    if dolar_mep:
        caucion_r = supabase.table("instrumentos_rf").select("tna_actual").eq("codigo", "CAUCION_7D").limit(1).execute()
        tna_ref = caucion_r.data[0]["tna_actual"] if caucion_r.data and caucion_r.data[0].get("tna_actual") else None
        if tna_ref:
            carry = analizar_carry_trade(tna_ref, dolar_mep, None)
            icon = "🟢" if carry["accion"] == "entrar" else "🔴" if carry["accion"] == "salir" else "🟡"
            lines.append(
                f"{icon} *Carry trade actual*\n"
                f"  TNA caución 7D: {tna_ref:.1f}% ({carry['tna_mensual']:.1f}%/mes)\n"
                f"  Devaluación MEP 30d: ~{carry['devaluacion_mensual']:.1f}%/mes\n"
                f"  Carry neto: {carry['carry_mensual']:+.1f}% — {carry['accion'].upper()}\n"
            )
        else:
            lines.append("🟡 *Carry trade*: TNA de caución no disponible aún\n")

        lines.append(f"💵 Dólar MEP: ${dolar_mep:,.2f} ARS\n")
    else:
        lines.append("⚠️ No se pudo obtener dólar MEP\n")

    if capital_usd and dolar_mep:
        alloc = calcular_allocation(posiciones, capital_usd, dolar_mep)
        lines.append(
            f"📊 *Allocation*\n"
            f"  Capital: ${capital_usd:,.0f} USD\n"
            f"  En RF: ${alloc['total_usd_rf']:,.0f} USD ({alloc['pct_rf']}%) — objetivo {asignacion_obj:.0f}%\n"
            f"  Libre: ${alloc['total_usd_libre']:,.0f} USD ({alloc['pct_libre']}%)\n"
        )

    if posiciones:
        lines.append("📄 *Posiciones abiertas*\n")
        for p in posiciones:
            inst = p.get("instrumentos_rf") or {}
            nombre = inst.get("nombre") or "instrumento"
            tna = p.get("tna_contratada") or inst.get("tna_actual") or 0
            venc = p.get("fecha_vencimiento")
            venc_txt = f" | vence {venc}" if venc else ""
            rdto_txt = ""
            if dolar_mep:
                try:
                    rdto = calcular_rendimiento_usd(p, dolar_mep)
                    rdto_txt = f" | {rdto['rendimiento_usd_pct']:+.1f}% USD"
                except Exception:
                    pass
            lines.append(f"  • {nombre}: ${p['monto_ars']:,.0f} ARS @ {tna:.1f}% TNA{venc_txt}{rdto_txt}")
    else:
        lines.append("_Sin posiciones RF abiertas._\n\nPara registrar:\n`puse 500000 en caución 7 días`")

    await _send(chat_id, "\n".join(lines), token)


async def _handle_portafolio_cmd(user_id: str, chat_id: int, token: str, portafolio: dict | None = None) -> None:
    supabase = get_supabase()

    portafolio_id = portafolio.get("id") if portafolio else None
    nombre_port = portafolio.get("nombre_personalizado") or portafolio.get("nombre_sugerido") or "Portafolio" if portafolio else "Portafolio"
    tipo_port = portafolio.get("tipo", "") if portafolio else ""
    capital_usd = portafolio.get("capital_usd") if portafolio else None
    rf_pct = portafolio.get("asignacion_rf_pct") if portafolio else None

    _TIPO_EMOJI = {"conservador": "🛡️", "pasivo": "💰", "crecimiento": "📈", "oportunista": "🎯"}
    tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}
    tend_icon = {"alcista": "📈", "bajista": "📉", "lateral": "➡️"}

    lines = [f"📊 *{_TIPO_EMOJI.get(tipo_port, '📊')} {nombre_port}*\n"]

    if capital_usd:
        rv_pct = 100 - (rf_pct or 0)
        lines.append(f"Capital: ${capital_usd:,.0f} USD | RF: {rf_pct:.0f}% | RV: {rv_pct:.0f}%\n")

    # Activos asignados al portafolio
    if portafolio_id:
        pa_r = supabase.table("portafolio_activos").select("activo_id, porcentaje_objetivo, monto_usd").eq("portafolio_id", portafolio_id).execute()
        pa_data = pa_r.data or []
    else:
        pa_data = []

    if pa_data:
        activos_ids = [row["activo_id"] for row in pa_data]
        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda, precio_actual, precio_ars, tendencia, rsi").in_("id", activos_ids).execute()
        activos_map = {a["id"]: a for a in (activos_r.data or [])}
        pa_map = {row["activo_id"]: row for row in pa_data}

        for activo_id, activo in activos_map.items():
            pa = pa_map.get(activo_id, {})
            icon = tipo_icon.get(activo.get("tipo", ""), "")
            precio_actual = activo.get("precio_actual") or activo.get("precio_ars")
            moneda = activo.get("moneda", "")
            tend = tend_icon.get(activo.get("tendencia", "lateral"), "➡️")
            rsi = activo.get("rsi")

            linea = f"{icon} *{activo['codigo']}* — {activo['nombre']}\n"
            if precio_actual:
                linea += f"   Precio: {precio_actual:,.2f} {moneda}  {tend}\n"
            if rsi:
                linea += f"   RSI: {rsi:.1f}\n"
            if pa.get("porcentaje_objetivo") and pa.get("monto_usd"):
                linea += f"   Asignado: {pa['porcentaje_objetivo']}% = ${pa['monto_usd']:,.0f} USD\n"
            lines.append(linea)
    else:
        lines.append("_Sin activos RV asignados todavía._\n")

    lines.append("_Precios actualizados por el cron cada 30 min_")
    await _send(chat_id, "\n".join(lines), token)


async def _handle_opciones_rf_cmd(user_id: str, chat_id: int, token: str) -> None:
    """Muestra análisis de opciones de RF disponibles y carry trade actual."""
    from lib.market_data import fetch_dolar_precio
    from lib.rf_analysis import analizar_carry_trade
    supabase = get_supabase()

    lines = ["💰 *Opciones de Renta Fija*\n"]

    # ─── Obtener dólar y carry trade ───
    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_data["precio"] if dolar_data else None

    if not dolar_mep:
        await _send(chat_id, "No se pudo obtener cotización. Intentá de nuevo.", token)
        return

    # ─── Carry trade actual ───
    caucion_r = supabase.table("instrumentos_rf").select("tna_actual").eq("codigo", "CAUCION_7D").limit(1).execute()
    tna_ref = caucion_r.data[0]["tna_actual"] if caucion_r.data and caucion_r.data[0].get("tna_actual") else None

    if tna_ref:
        carry = analizar_carry_trade(tna_ref, dolar_mep, None)
        icon = "🟢" if carry["accion"] == "entrar" else "🔴" if carry["accion"] == "salir" else "🟡"
        lines.append(
            f"{icon} *Carry Trade*\n"
            f"  Acción: {carry['accion'].upper()}\n"
            f"  Caución 7D: {tna_ref:.1f}% TNA\n"
            f"  Carry mensual: {carry['carry_mensual']:+.1f}%\n"
            f"  Dólar MEP: ${dolar_mep:,.2f} ARS\n"
        )

    # ─── Instrumentos disponibles ───
    lines.append("*📄 Instrumentos disponibles:*\n")

    # Cauciones
    caucion_opts = supabase.table("instrumentos_rf").select("codigo, nombre, plazo_dias, tna_actual").eq("tipo", "caucion").eq("activo", True).order("plazo_dias").execute()
    if caucion_opts.data:
        lines.append("*🔄 Cauciones (Liquidez máxima)*")
        for c in caucion_opts.data:
            tna = c.get("tna_actual") or "—"
            if isinstance(tna, (int, float)):
                tna = f"{tna:.1f}%"
            lines.append(f"  • {c['nombre']}: {tna} TNA — renovable")
        lines.append("")

    # Letras (Lecaps)
    lecap_opts = supabase.table("instrumentos_rf").select("codigo, nombre, plazo_dias, tna_actual, vencimiento").eq("tipo", "letra").eq("activo", True).limit(3).execute()
    if lecap_opts.data:
        lines.append("*📋 Letras del Tesoro (Lecaps)*")
        for l in lecap_opts.data:
            tna = l.get("tna_actual") or "—"
            if isinstance(tna, (int, float)):
                tna = f"{tna:.1f}%"
            venc = l.get("vencimiento", "")
            plazo = l.get("plazo_dias", "")
            venc_txt = f" vence {venc}" if venc else f" {plazo}d"
            lines.append(f"  • {l['nombre']}: {tna} TNA •{venc_txt}")
        lines.append("")

    # Bonos soberanos
    bono_opts = supabase.table("instrumentos_rf").select("codigo, nombre, moneda, tna_actual").eq("tipo", "bono_soberano").eq("activo", True).limit(4).execute()
    if bono_opts.data:
        lines.append("*🪙 Bonos Soberanos (USD)*")
        for b in bono_opts.data:
            tir = b.get("tna_actual") or "—"
            if isinstance(tir, (int, float)):
                tir = f"{tir:.1f}%"
            lines.append(f"  • {b['codigo']} ({b['nombre']}): {tir} TIR")
        lines.append("")

    lines.append("*Para registrar una posición:*\n`puse 500000 en caución 7 días`\n`lecap 300000 S28F6`\n`AL30 100000`\n")
    lines.append("_Ver estado con /liquidez — Ver recomendaciones con /inversiones_")
    await _send(chat_id, "\n".join(lines), token)
