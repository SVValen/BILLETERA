import json as _json
from lib.supabase_client import get_supabase
from ..tg import _send


async def _handle_inversiones_cmd(user_id: str, chat_id: int, token: str) -> None:
    from .wizard_inversion import _send_tipo_keyboard
    supabase = get_supabase()

    # Verificar si tiene portafolios activos
    port_r = supabase.table("portafolios").select("id").eq("usuario_id", user_id).eq("activo", True).eq("estado_wizard", "activo").limit(1).execute()
    if not port_r.data:
        await _send(chat_id, "No tenés portafolios activos. Creá uno con /portafolio_nuevo.", token, parse_mode="")
        return

    # Compatibilidad Fase 4 pendiente: mostrar recomendaciones básicas
    p = {}  # TODO Fase 4: reemplazar con datos de portafolios

    obj_labels = {
        "ingresos_pasivos": "💰 Ingresos pasivos",
        "crecimiento": "📈 Crecer capital",
        "cobertura": "🛡️ Cobertura inflación",
        "meta_especifica": "🎯 Meta específica",
    }
    plazo_labels = {"corto": "< 1 año", "mediano": "1-3 años", "largo": "+3 años"}
    perfil_emoji = {"conservador": "🛡️", "moderado": "⚖️", "arriesgado": "🚀"}.get(p.get("perfil", ""), "📈")
    plazo_txt = plazo_labels.get(p.get("plazo", ""), "")
    _obj_raw = p.get("objetivos") or p.get("objetivo") or ""
    if _obj_raw and _obj_raw.startswith("["):
        try:
            _obj_list = _json.loads(_obj_raw)
            obj_txt = " + ".join(obj_labels.get(o, o) for o in _obj_list)
        except Exception:
            obj_txt = _obj_raw
    else:
        obj_txt = obj_labels.get(_obj_raw, _obj_raw)
    header = f"📈 *Inversiones*"
    if obj_txt:
        header += f" — {obj_txt}"
    lines = [header]
    if plazo_txt:
        lines.append(f"⏱ Plazo: {plazo_txt}")
    if p.get("perfil"):
        lines.append(f"🎚 Riesgo derivado: {perfil_emoji} {p['perfil'].capitalize()}")
    if p.get("capital_disponible"):
        lines.append(f"💰 Capital: ${p['capital_disponible']:,.0f}")

    recs_r = (
        supabase.table("recomendaciones")
        .select("*, activos(codigo, nombre)")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente")
        .order("generado_at", desc=True)
        .limit(3)
        .execute()
    )
    if recs_r.data:
        lines.append(f"\n⏳ *{len(recs_r.data)} recomendación(es) pendiente(s):*")
        for r in recs_r.data:
            a = r.get("activos") or {}
            emoji = "🟢" if r["accion"] == "comprar" else "🔴" if r["accion"] == "vender" else "🟡"
            lines.append(f"{emoji} {r['accion'].upper()} {a.get('codigo', '?')} — confianza {r['confianza']}/10")
    else:
        lines.append("\n✅ Sin señales ahora. El sistema revisa cada 30 minutos.")

    stats_r = supabase.table("decisiones_inversion").select("resultado, accion").eq("usuario_id", user_id).execute()
    decisiones = stats_r.data or []
    aceptadas = [d for d in decisiones if d["accion"] == "aceptada"]
    exitosas = [d for d in aceptadas if d["resultado"] == "exitoso"]
    if aceptadas:
        winrate = round(len(exitosas) / len(aceptadas) * 100)
        lines.append(f"\n🎯 Winrate: {winrate}% ({len(exitosas)}/{len(aceptadas)})")

    lines.append("\n_/inversiones para actualizar_")
    await _send(chat_id, "\n".join(lines), token,
        reply_markup={"inline_keyboard": [[
            {"text": "✏️ Cambiar perfil", "callback_data": "inv_cambiar_perfil"},
        ]]})


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
    ua_r = supabase.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
    activos_ids = [row["activo_id"] for row in (ua_r.data or [])]

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
    from lib.market_data import fetch_dolar_precio, fetch_caucion_tna
    from lib.rf_analysis import analizar_carry_trade, calcular_rendimiento_usd, calcular_allocation, evaluar_vencimientos

    supabase = get_supabase()

    perfil_r = supabase.table("perfiles_inversion").select("capital_usd, asignacion_rf_pct").eq("usuario_id", user_id).limit(1).execute()
    perfil = perfil_r.data[0] if perfil_r.data else {}
    capital_usd = perfil.get("capital_usd")
    asignacion_obj = perfil.get("asignacion_rf_pct") or 30

    dolar_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_data["precio"] if dolar_data else None

    pos_r = supabase.table("posiciones_rf").select("*, instrumentos_rf(nombre, tipo, tna_actual)").eq("usuario_id", user_id).eq("estado", "activa").execute()
    posiciones = pos_r.data or []

    lines = ["💼 *Liquidez y Renta Fija*\n"]

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
            f"📊 *Allocation actual*\n"
            f"  Capital total: ${capital_usd:,.0f} USD\n"
            f"  En RF: ${alloc['total_usd_rf']:,.0f} USD ({alloc['pct_rf']}%) — objetivo {asignacion_obj}%\n"
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
                rdto = calcular_rendimiento_usd(p, dolar_mep)
                rdto_txt = f" | {rdto['rendimiento_usd_pct']:+.1f}% USD"
            lines.append(
                f"  • {nombre}: ${p['monto_ars']:,.0f} ARS @ {tna:.1f}% TNA{venc_txt}{rdto_txt}"
            )
            lines.append(
                f"    [Rescatar](tg://callback/rf_rescatar:{p['id']})"
            )
    else:
        lines.append("_Sin posiciones RF abiertas._\n\nPara registrar una posición escribí por ejemplo:\n`puse 500000 en caución 7 días`")

    await _send(chat_id, "\n".join(lines), token)


async def _handle_portafolio_cmd(user_id: str, chat_id: int, token: str, portafolio: dict | None = None) -> None:
    supabase = get_supabase()

    ua_r = supabase.table("usuario_activos").select("activo_id, porcentaje, monto_ars, precio_entrada").eq("usuario_id", user_id).execute()
    if not ua_r.data:
        await _send(chat_id,
            "📊 No tenés activos configurados todavía.\nUsá /inversiones para empezar.",
            token, parse_mode="")
        return

    activos_ids = [row["activo_id"] for row in ua_r.data]
    activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda, precio_actual, precio_ars, tendencia, rsi").in_("id", activos_ids).execute()
    activos_map = {a["id"]: a for a in (activos_r.data or [])}
    ua_map = {row["activo_id"]: row for row in ua_r.data}

    tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}
    tend_icon = {"alcista": "📈", "bajista": "📉", "lateral": "➡️"}

    lines = ["📊 *Tu Portafolio*\n"]
    for activo_id, activo in activos_map.items():
        ua = ua_map.get(activo_id, {})
        icon = tipo_icon.get(activo.get("tipo", ""), "")
        precio_actual = activo.get("precio_actual") or activo.get("precio_ars")
        precio_entrada = ua.get("precio_entrada")
        moneda = activo.get("moneda", "")
        tend = tend_icon.get(activo.get("tendencia", "lateral"), "➡️")
        rsi = activo.get("rsi")

        linea = f"{icon} *{activo['codigo']}* — {activo['nombre']}\n"
        if precio_actual:
            linea += f"   Precio: {precio_actual:,.2f} {moneda}  {tend}\n"
        if rsi:
            linea += f"   RSI: {rsi:.1f}\n"
        if ua.get("porcentaje") and ua.get("monto_ars"):
            linea += f"   Asignado: {ua['porcentaje']}% = ${ua['monto_ars']:,.0f} ARS\n"
        if precio_entrada and precio_actual:
            pnl = (float(precio_actual) - float(precio_entrada)) / float(precio_entrada) * 100
            emoji_pnl = "📈" if pnl > 0 else "📉" if pnl < 0 else "➡️"
            linea += f"   P&L desde entrada: {pnl:+.1f}% {emoji_pnl}\n"
        lines.append(linea)

    perfil_r = supabase.table("perfiles_inversion").select("capital_disponible, perfil, objetivos").eq("usuario_id", user_id).limit(1).execute()
    if perfil_r.data:
        p = perfil_r.data[0]
        perfil_emoji = {"conservador": "🛡️", "moderado": "⚖️", "arriesgado": "🚀"}.get(p.get("perfil", ""), "📈")
        lines.append(f"\n{perfil_emoji} Perfil: {p.get('perfil', '?').capitalize()}")
        if p.get("capital_disponible"):
            lines.append(f"💰 Capital base: ${p['capital_disponible']:,.0f} ARS")

    lines.append("\n_Precios actualizados por el cron cada 30 min_")
    await _send(chat_id, "\n".join(lines), token)
