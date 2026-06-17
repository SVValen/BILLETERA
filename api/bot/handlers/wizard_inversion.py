import json as _json
from lib.supabase_client import get_supabase
from ..tg import _send, _answer_callback, _edit_message


async def _send_objetivos_keyboard(
    user_id: str, chat_id: int, token: str, supabase=None, edit_message_id: int | None = None
) -> None:
    """Teclado multi-select de objetivos de inversión."""
    if supabase is None:
        supabase = get_supabase()

    perfil_r = supabase.table("perfiles_inversion").select("objetivos").eq("usuario_id", user_id).limit(1).execute()
    seleccionados = []
    if perfil_r.data and perfil_r.data[0].get("objetivos"):
        try:
            seleccionados = _json.loads(perfil_r.data[0]["objetivos"])
        except Exception:
            seleccionados = []

    opciones = [
        ("ingresos_pasivos", "💰 Ingresos pasivos"),
        ("crecimiento",      "📈 Crecer capital"),
        ("cobertura",        "🛡️ Cobertura inflación"),
        ("meta_especifica",  "🎯 Meta específica"),
    ]

    rows = []
    for key, label in opciones:
        check = "✅" if key in seleccionados else "⬜"
        rows.append([{"text": f"{check} {label}", "callback_data": f"inv_toggle_objetivo:{key}"}])
    rows.append([{"text": "➡️ Continuar", "callback_data": "inv_confirmar_objetivos"}])

    texto = (
        "📈 *Módulo de Inversiones*\n\n"
        "*¿Cuáles son tus objetivos?* Podés elegir más de uno.\n"
        "_Tocá para marcar/desmarcar._"
    )
    if edit_message_id:
        await _edit_message(chat_id, edit_message_id, texto, token, reply_markup={"inline_keyboard": rows})
    else:
        await _send(chat_id, texto, token, reply_markup={"inline_keyboard": rows})


async def _send_activos_keyboard(
    user_id: str, chat_id: int, token: str, supabase=None, edit_message_id: int | None = None
) -> None:
    """Envía (o edita) el teclado de selección de activos. Marca los ya seleccionados."""
    if supabase is None:
        supabase = get_supabase()

    activos_r = supabase.table("activos").select("id, codigo, nombre, tipo").eq("activo", True).execute()
    todos = activos_r.data or []

    seleccionados_r = supabase.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
    seleccionados = {row["activo_id"] for row in (seleccionados_r.data or [])}

    def _label(a: dict) -> str:
        check = "✅" if a["id"] in seleccionados else "⬜"
        tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}.get(a["tipo"], "")
        return f"{check} {tipo_icon} {a['codigo']}"

    rows = []
    for i in range(0, len(todos), 2):
        fila = []
        for activo in todos[i:i+2]:
            fila.append({
                "text": _label(activo),
                "callback_data": f"inv_toggle:{activo['id']}",
            })
        rows.append(fila)

    rows.append([{"text": "✔️ Confirmar selección", "callback_data": "inv_confirmar_activos"}])

    texto = (
        "📊 *¿Qué activos querés monitorear?*\n"
        "_Tocá para marcar/desmarcar. Podés cambiar esto en cualquier momento._"
    )
    reply_markup = {"inline_keyboard": rows}

    if edit_message_id:
        await _edit_message(chat_id, edit_message_id, texto, token, reply_markup=reply_markup)
    else:
        await _send(chat_id, texto, token, reply_markup=reply_markup)


async def handle_wizard_callback(
    parts: list[str], callback_id: str, chat_id: int, message_id: int,
    user_id: str, supabase, token: str
) -> bool:
    """Maneja callbacks del wizard de inversiones. Retorna True si consumió el callback."""

    if parts[0] == "inv_toggle_objetivo" and len(parts) == 2:
        objetivo = parts[1]
        if objetivo not in ("ingresos_pasivos", "crecimiento", "cobertura", "meta_especifica"):
            return False

        perfil_r = supabase.table("perfiles_inversion").select("objetivos").eq("usuario_id", user_id).limit(1).execute()
        if not perfil_r.data:
            supabase.table("perfiles_inversion").insert({
                "usuario_id": user_id,
                "perfil": "moderado",
                "objetivos": _json.dumps([objetivo]),
                "estado": "configurando_objetivos",
            }).execute()
        else:
            obj_actual = []
            raw = perfil_r.data[0].get("objetivos")
            if raw:
                try:
                    obj_actual = _json.loads(raw)
                except Exception:
                    obj_actual = []
            if objetivo in obj_actual:
                obj_actual.remove(objetivo)
            else:
                obj_actual.append(objetivo)
            supabase.table("perfiles_inversion").update({
                "objetivos": _json.dumps(obj_actual),
                "estado": "configurando_objetivos",
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()

        if token:
            await _answer_callback(callback_id, token)
        await _send_objetivos_keyboard(user_id, chat_id, token, supabase, edit_message_id=message_id)
        return True

    if parts[0] == "inv_confirmar_objetivos":
        perfil_r = supabase.table("perfiles_inversion").select("objetivos").eq("usuario_id", user_id).limit(1).execute()
        obj_list = []
        if perfil_r.data and perfil_r.data[0].get("objetivos"):
            try:
                obj_list = _json.loads(perfil_r.data[0]["objetivos"])
            except Exception:
                obj_list = []

        if not obj_list:
            if token:
                await _answer_callback(callback_id, token, text="Seleccioná al menos un objetivo")
        else:
            supabase.table("perfiles_inversion").update({
                "estado": "configurando_plazo",
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()
            _obj_labels = {
                "ingresos_pasivos": "💰 Ingresos pasivos",
                "crecimiento": "📈 Crecer capital",
                "cobertura": "🛡️ Cobertura inflación",
                "meta_especifica": "🎯 Meta específica",
            }
            obj_txt = " + ".join(_obj_labels.get(o, o) for o in obj_list)
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"✅ Objetivos: *{obj_txt}*\n\n"
                    "⏱ *¿A qué plazo pensás invertir?*",
                    token,
                    reply_markup={"inline_keyboard": [
                        [{"text": "⚡ Corto plazo (< 1 año)",   "callback_data": "inv_plazo:corto"}],
                        [{"text": "📅 Mediano plazo (1-3 años)", "callback_data": "inv_plazo:mediano"}],
                        [{"text": "🔭 Largo plazo (+ 3 años)",  "callback_data": "inv_plazo:largo"}],
                    ]})
        return True

    if parts[0] == "inv_plazo" and len(parts) == 2:
        plazo = parts[1]
        if plazo in ("corto", "mediano", "largo"):
            supabase.table("perfiles_inversion").update({
                "plazo": plazo,
                "estado": "configurando_moneda",
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()
            plazo_label = {"corto": "< 1 año", "mediano": "1-3 años", "largo": "+ 3 años"}[plazo]
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"✅ Plazo: *{plazo_label}*\n\n"
                    "💱 *¿Preferís invertir en pesos o dólares?*",
                    token,
                    reply_markup={"inline_keyboard": [
                        [{"text": "🇦🇷 Pesos (ARS)", "callback_data": "inv_moneda:ARS"}],
                        [{"text": "🇺🇸 Dólares (USD)", "callback_data": "inv_moneda:USD"}],
                        [{"text": "⚖️ Ambas monedas", "callback_data": "inv_moneda:ambas"}],
                    ]})
        return True

    if parts[0] == "inv_moneda" and len(parts) == 2:
        moneda = parts[1]
        if moneda in ("ARS", "USD", "ambas"):
            supabase.table("perfiles_inversion").update({
                "moneda_preferida": moneda,
                "estado": "configurando_capital",
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()
            moneda_label = {"ARS": "Pesos 🇦🇷", "USD": "Dólares 🇺🇸", "ambas": "Ambas monedas ⚖️"}[moneda]
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"✅ Moneda: *{moneda_label}*\n\n"
                    "💰 *¿Cuánto capital tenés disponible para invertir?* (en USD)\n"
                    "_Respondé con un número, ej: `5000`_\n"
                    "_O escribí `skip` para omitirlo_",
                    token)
        return True

    if parts[0] == "inv_rf_pct" and len(parts) == 2:
        pct_raw = parts[1]
        upd_rf: dict = {"estado": "configurando_descripcion", "actualizado_at": "now()"}
        if pct_raw != "skip":
            try:
                pct = int(pct_raw)
                if 0 < pct <= 100:
                    upd_rf["asignacion_rf_pct"] = pct
            except ValueError:
                pass
        supabase.table("perfiles_inversion").update(upd_rf).eq("usuario_id", user_id).execute()
        pct_label = f"{pct_raw}% en RF" if pct_raw != "skip" else "sin objetivo RF"
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                f"✅ Asignación RF: *{pct_label}*\n\n"
                "📝 *Casi listo.*\n\n"
                "Contame en tus propias palabras qué buscás con tus inversiones. "
                "Por ejemplo: qué te preocupa, si querés cubrirte del dólar, si ya tenés algo invertido, etc.\n\n"
                "_También podés mandar un audio. Escribí `skip` para saltearlo._",
                token)
        return True

    if parts[0] == "inv_cambiar_perfil":
        if token:
            await _answer_callback(callback_id, token)
        supabase.table("perfiles_inversion").update({
            "objetivos": "[]",
            "estado": "configurando_objetivos",
            "actualizado_at": "now()",
        }).eq("usuario_id", user_id).execute()
        await _send_objetivos_keyboard(user_id, chat_id, token, supabase, edit_message_id=message_id)
        return True

    if parts[0] == "inv_toggle" and len(parts) == 2:
        activo_id = int(parts[1])
        existe_r = supabase.table("usuario_activos").select("id").eq("usuario_id", user_id).eq("activo_id", activo_id).limit(1).execute()
        if existe_r.data:
            supabase.table("usuario_activos").delete().eq("usuario_id", user_id).eq("activo_id", activo_id).execute()
        else:
            supabase.table("usuario_activos").insert({"usuario_id": user_id, "activo_id": activo_id}).execute()
        if token:
            await _answer_callback(callback_id, token)
        await _send_activos_keyboard(user_id, chat_id, token, supabase, edit_message_id=message_id)
        return True

    if parts[0] == "inv_confirmar_activos":
        seleccionados_r = supabase.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
        n = len(seleccionados_r.data or [])
        if n == 0:
            if token:
                await _answer_callback(callback_id, token, text="Seleccioná al menos un activo")
        else:
            perfil_r2 = supabase.table("perfiles_inversion").select("capital_disponible, perfil, objetivos, plazo").eq("usuario_id", user_id).limit(1).execute()
            capital = perfil_r2.data[0].get("capital_disponible") if perfil_r2.data else None

            if capital and n > 1:
                supabase.table("perfiles_inversion").update({
                    "estado": "configurando_portafolio",
                    "actualizado_at": "now()",
                }).eq("usuario_id", user_id).execute()

                activos_ids = [row["activo_id"] for row in seleccionados_r.data]
                activos_precios_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda, precio_actual, precio_ars").in_("id", activos_ids).execute()
                activos_precios = activos_precios_r.data or []

                tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}
                lines = [
                    f"✅ Activos confirmados. Ahora distribuimos los *${capital:,.0f}*\n",
                    "📊 *Precios actuales:*",
                ]
                for a in activos_precios:
                    precio = a.get("precio_actual") or a.get("precio_ars")
                    moneda = a.get("moneda", "")
                    icon = tipo_icon.get(a.get("tipo", ""), "")
                    lines.append(f"{icon} *{a['codigo']}* — {precio:,.2f} {moneda}" if precio else f"{icon} *{a['codigo']}* — precio no disponible")

                lines += [
                    "",
                    "💬 *¿Cómo querés dividir el capital?*",
                    "_Podés escribir porcentajes: `50% BTC, 50% AAPL`_",
                    "_O pedirme que lo decida: `vos decidí`_",
                ]
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id, "\n".join(lines), token)
            else:
                supabase.table("perfiles_inversion").update({
                    "estado": "activo",
                    "actualizado_at": "now()",
                }).eq("usuario_id", user_id).execute()
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id,
                        f"✅ *Perfil listo*\nVas a recibir señales para los {n} activo{'s' if n != 1 else ''} seleccionados.\n\n"
                        "Usá /inversiones o /portafolio para ver el estado.",
                        token)
        return True

    if parts[0] == "inv_confirmar_portafolio":
        portafolio_raw = supabase.table("perfiles_inversion").select("portafolio_pendiente").eq("usuario_id", user_id).limit(1).execute()
        distribuciones = []
        if portafolio_raw.data and portafolio_raw.data[0].get("portafolio_pendiente"):
            try:
                distribuciones = _json.loads(portafolio_raw.data[0]["portafolio_pendiente"])
            except Exception:
                distribuciones = []

        if distribuciones:
            activos_r2 = supabase.table("activos").select("id, codigo, precio_actual, precio_ars").execute()
            activos_map = {a["codigo"]: a for a in (activos_r2.data or [])}

            for d in distribuciones:
                activo_info = activos_map.get(d["codigo"])
                if activo_info:
                    precio_entrada = activo_info.get("precio_actual") or activo_info.get("precio_ars")
                    supabase.table("usuario_activos").update({
                        "porcentaje": d.get("porcentaje"),
                        "monto_ars": d.get("monto_ars"),
                        "precio_entrada": precio_entrada,
                    }).eq("usuario_id", user_id).eq("activo_id", activo_info["id"]).execute()

        supabase.table("perfiles_inversion").update({
            "estado": "activo",
            "portafolio_pendiente": None,
            "actualizado_at": "now()",
        }).eq("usuario_id", user_id).execute()

        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                "✅ *Portafolio configurado*\n\nUsá /portafolio para ver tu distribución y precios actuales.",
                token)
        return True

    if parts[0] == "inv_cambiar_portafolio":
        supabase.table("perfiles_inversion").update({
            "portafolio_pendiente": None,
            "actualizado_at": "now()",
        }).eq("usuario_id", user_id).execute()
        if token:
            await _answer_callback(callback_id, token)
            await _edit_message(chat_id, message_id,
                "✏️ Escribí cómo querés dividir el capital.\n"
                "Ej: `40% BTC, 60% AAPL` o `vos decidí`.",
                token)
        return True

    return False


async def handle_wizard_text(
    text: str, user_id: str, chat_id: int, token: str, supabase, perfil_check
) -> bool:
    """Maneja respuestas de texto del wizard de inversiones. Retorna True si consumió el texto."""
    estado_perfil = perfil_check.data[0].get("estado") if perfil_check.data else None
    if not estado_perfil:
        return False

    # Guard: estados que solo usan botones
    if estado_perfil.startswith("configurando_") and estado_perfil not in (
        "configurando_capital", "configurando_descripcion",
        "configurando_activos", "configurando_portafolio",
        "configurando_rf_pct",
    ):
        await _send(chat_id,
            "📋 Usá los botones del mensaje anterior para continuar.\n"
            "Si no los ves, enviá /inversiones para retomar el setup.",
            token, parse_mode="")
        return True

    if estado_perfil == "configurando_capital":
        clean = text.replace(".", "").replace(",", "").replace("$", "").replace(" ", "").replace("USD", "").replace("usd", "").replace("U$S", "").strip()
        if text.lower().strip() in ("skip", "/skip"):
            capital_usd = None
        else:
            try:
                capital_usd = float(clean)
                if capital_usd <= 0:
                    raise ValueError("capital debe ser positivo")
            except ValueError:
                await _send(chat_id,
                    "No entendí el monto. Enviá el número en USD (ej: `5000`) o escribí `skip` para omitirlo.", token)
                return True

        capital_ars = None
        if capital_usd:
            try:
                from lib.market_data import fetch_dolar_precio
                dolar = await fetch_dolar_precio("bolsa")
                if dolar:
                    capital_ars = round(capital_usd * dolar["precio"], 2)
            except Exception:
                pass

        upd: dict = {"estado": "configurando_rf_pct", "actualizado_at": "now()"}
        if capital_usd is not None:
            upd["capital_usd"] = capital_usd
        if capital_ars is not None:
            upd["capital_disponible"] = capital_ars
        supabase.table("perfiles_inversion").update(upd).eq("usuario_id", user_id).execute()

        capital_txt = f"${capital_usd:,.0f} USD" if capital_usd else "no especificado"
        await _send(chat_id,
            f"✅ Capital: *{capital_txt}*\n\n"
            "💼 *¿Qué porcentaje querés tener siempre en renta fija (liquidez)?*\n\n"
            "_La renta fija incluye cauciones, letras y bonos — instrumentos más seguros "
            "que te permiten no estar en dólares sin perder rendimiento cuando el carry es favorable._\n\n"
            "_Ej: 30% significa que de tus USD 5000, ~1500 estarían en ARS rentando._",
            token,
            reply_markup={"inline_keyboard": [
                [{"text": "🛡️ 20% (conservador en RV)", "callback_data": "inv_rf_pct:20"}],
                [{"text": "⚖️ 30% (balanceado)",         "callback_data": "inv_rf_pct:30"}],
                [{"text": "📈 50% (mitad en liquidez)",  "callback_data": "inv_rf_pct:50"}],
                [{"text": "⏭️ Saltar",                   "callback_data": "inv_rf_pct:skip"}],
            ]})
        return True

    if estado_perfil == "configurando_rf_pct":
        return True

    if estado_perfil == "configurando_descripcion":
        from lib.claude_invest import sugerir_activos_para_perfil
        descripcion = text if text.lower() not in ("skip", "/skip") else ""

        supabase.table("perfiles_inversion").update({
            "descripcion_libre": descripcion or None,
            "actualizado_at": "now()",
        }).eq("usuario_id", user_id).execute()

        await _send(chat_id, "🤖 Analizando tu perfil...", token, parse_mode="")

        perfil_data = perfil_check.data[0]
        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda").eq("activo", True).execute()
        activos_disponibles = activos_r.data or []

        _obj_raw = perfil_data.get("objetivos") or perfil_data.get("objetivo") or "[]"
        try:
            objetivos_lista = _json.loads(_obj_raw) if _obj_raw.startswith("[") else [_obj_raw] if _obj_raw else []
        except Exception:
            objetivos_lista = []

        sugerencia = sugerir_activos_para_perfil(
            objetivos=objetivos_lista,
            plazo=perfil_data.get("plazo", ""),
            capital=perfil_data.get("capital_disponible"),
            descripcion=descripcion,
            activos_disponibles=activos_disponibles,
            moneda_preferida=perfil_data.get("moneda_preferida", "ARS"),
        )

        if sugerencia:
            supabase.table("perfiles_inversion").update({
                "perfil": sugerencia.get("perfil_riesgo", "moderado"),
                "estado": "configurando_activos",
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()

            activos_sugeridos = sugerencia.get("activos_sugeridos", [])
            codigos_sugeridos = {a["codigo"].upper() if isinstance(a, dict) else a.upper() for a in activos_sugeridos}
            for activo in activos_disponibles:
                if activo["codigo"] in codigos_sugeridos:
                    try:
                        supabase.table("usuario_activos").insert({
                            "usuario_id": user_id, "activo_id": activo["id"]
                        }).execute()
                    except Exception:
                        pass

            perfil_emoji = {"conservador": "🛡️", "moderado": "⚖️", "arriesgado": "🚀"}.get(
                sugerencia.get("perfil_riesgo", ""), "📈")
            tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}
            activos_por_codigo = {a["codigo"]: a for a in activos_disponibles}

            lines = [
                f"{perfil_emoji} *Perfil sugerido: {sugerencia.get('perfil_riesgo', '').capitalize()}*",
                f"_{sugerencia.get('resumen', '')}_\n",
                "📌 *Activos recomendados para vos:*\n",
            ]
            for item in activos_sugeridos:
                if isinstance(item, dict):
                    codigo = item.get("codigo", "")
                    razon = item.get("razon", "")
                    explicacion = item.get("explicacion", "")
                    a_info = activos_por_codigo.get(codigo, {})
                    icon = tipo_icon.get(a_info.get("tipo", ""), "")
                    nombre = a_info.get("nombre", codigo)
                    lines.append(f"*{icon} {codigo} — {nombre}*")
                    if razon:
                        lines.append(f"_{razon}_")
                    if explicacion:
                        lines.append(explicacion)
                    lines.append("")

            otros = sugerencia.get("otros_disponibles", [])
            if otros:
                lines.append(f"💡 *También disponibles:* {', '.join(otros)}")
                lines.append("_Podés activarlos desde el teclado de abajo._\n")

            lines.append("💬 _¿Tenés dudas? Escribime cualquier pregunta sobre los activos._")
            await _send(chat_id, "\n".join(lines), token)
        else:
            supabase.table("perfiles_inversion").update({
                "estado": "configurando_activos",
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()
            await _send(chat_id, "No pude analizar el perfil ahora, pero podés elegir los activos manualmente:", token, parse_mode="")

        await _send_activos_keyboard(user_id, chat_id, token, supabase)
        return True

    if estado_perfil == "configurando_activos":
        from lib.claude_invest import responder_pregunta_activos

        _listo_keywords = {"listo", "ok", "dale", "bueno", "confirmar", "continuar", "siguiente", "ya", "confirmo"}
        if text.lower().strip() in _listo_keywords:
            await _send(chat_id, "👍 Tocá *Confirmar selección* en el teclado para avanzar 👆", token)
            await _send_activos_keyboard(user_id, chat_id, token, supabase)
            return True

        perfil_data = perfil_check.data[0]
        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda").eq("activo", True).execute()
        activos_disponibles = activos_r.data or []

        _obj_raw = perfil_data.get("objetivos") or perfil_data.get("objetivo") or "[]"
        try:
            objetivos_lista = _json.loads(_obj_raw) if _obj_raw.startswith("[") else [_obj_raw] if _obj_raw else []
        except Exception:
            objetivos_lista = []

        ua_r = supabase.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
        seleccionados_ids = {row["activo_id"] for row in (ua_r.data or [])}
        seleccionados_codigos = [a["codigo"] for a in activos_disponibles if a["id"] in seleccionados_ids]

        historial = []
        raw_hist = perfil_data.get("historial_chat", "[]") or "[]"
        try:
            historial = _json.loads(raw_hist)
        except Exception:
            historial = []

        respuesta = responder_pregunta_activos(
            pregunta=text,
            objetivos=objetivos_lista,
            plazo=perfil_data.get("plazo", ""),
            activos_disponibles=activos_disponibles,
            activos_seleccionados=seleccionados_codigos,
            historial=historial,
        )
        if respuesta:
            historial.append({"u": text, "b": respuesta})
            if len(historial) > 20:
                historial = historial[-20:]
            supabase.table("perfiles_inversion").update({
                "historial_chat": _json.dumps(historial),
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()

            await _send(chat_id,
                f"{respuesta}\n\n_Escribí *listo* cuando termines de explorar 👆_",
                token)
        else:
            await _send(chat_id, "No pude responder eso ahora. Probá más tarde.", token, parse_mode="")
        return True

    if estado_perfil == "configurando_portafolio":
        from lib.claude_invest import sugerir_portafolio

        perfil_data = perfil_check.data[0]
        capital = perfil_data.get("capital_disponible")
        if not capital:
            supabase.table("perfiles_inversion").update({"estado": "activo"}).eq("usuario_id", user_id).execute()
            await _send(chat_id, "✅ Perfil listo. Usá /portafolio para ver tus activos.", token)
            return True

        ua_r = supabase.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
        activos_ids = [row["activo_id"] for row in (ua_r.data or [])]
        activos_r = supabase.table("activos").select("id, codigo, nombre, tipo, moneda, precio_actual, precio_ars").in_("id", activos_ids).execute()
        activos_con_precios = activos_r.data or []

        _obj_raw = perfil_data.get("objetivos") or perfil_data.get("objetivo") or "[]"
        try:
            objetivos_lista = _json.loads(_obj_raw) if _obj_raw.startswith("[") else [_obj_raw] if _obj_raw else []
        except Exception:
            objetivos_lista = []

        historial = []
        raw_hist = perfil_data.get("historial_chat", "[]") or "[]"
        try:
            historial = _json.loads(raw_hist)
        except Exception:
            historial = []

        _pide_sugerencia = any(w in text.lower() for w in ("vos", "decidí", "sugerí", "no sé", "no se", "elegí", "decide", "sugiere"))

        if _pide_sugerencia:
            await _send(chat_id, "🤖 Calculando distribución óptima...", token, parse_mode="")
            distribuciones = sugerir_portafolio(
                objetivos=objetivos_lista,
                perfil_riesgo=perfil_data.get("perfil", "moderado"),
                plazo=perfil_data.get("plazo", ""),
                capital_ars=float(capital),
                activos_con_precios=activos_con_precios,
                historial=historial,
            )
        else:
            await _send(chat_id, "🤖 Interpretando tu distribución...", token, parse_mode="")
            _parse_prompt = (
                f"El usuario escribió: \"{text}\"\n"
                f"Activos disponibles: {[a['codigo'] for a in activos_con_precios]}\n"
                f"Capital total: ${capital:,.0f} ARS\n\n"
                "Interpretá la distribución y respondé SOLO en JSON:\n"
                "[{\"codigo\": \"BTC\", \"porcentaje\": 50, \"monto_ars\": 250000, \"razon\": \"como pidió el usuario\"}]"
            )
            try:
                from lib.claude_invest import _get_client, _parse_json
                _resp = _get_client().messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{"role": "user", "content": _parse_prompt}],
                )
                distribuciones = _parse_json(_resp.content[0].text)
                if not isinstance(distribuciones, list):
                    distribuciones = None
            except Exception:
                distribuciones = None

        if not distribuciones:
            await _send(chat_id,
                "No pude interpretar la distribución. "
                "Probá con el formato: `40% BTC, 60% AAPL` o escribí `vos decidí`.",
                token)
            return True

        supabase.table("perfiles_inversion").update({
            "portafolio_pendiente": _json.dumps(distribuciones),
            "actualizado_at": "now()",
        }).eq("usuario_id", user_id).execute()

        tipo_icon = {"crypto": "₿", "cedear": "🏢", "accion_ar": "🇦🇷", "dolar": "💵"}
        activos_map = {a["codigo"]: a for a in activos_con_precios}
        lines = ["📊 *Distribución sugerida:*\n"]
        for d in distribuciones:
            a_info = activos_map.get(d.get("codigo", ""), {})
            icon = tipo_icon.get(a_info.get("tipo", ""), "")
            lines.append(
                f"{icon} *{d['codigo']}*: {d.get('porcentaje', '?')}% = ${d.get('monto_ars', 0):,.0f}\n"
                f"   _{d.get('razon', '')}_"
            )
        lines.append("\n¿Confirmás esta distribución?")

        await _send(chat_id, "\n".join(lines), token,
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Confirmar", "callback_data": "inv_confirmar_portafolio"},
                {"text": "✏️ Cambiar", "callback_data": "inv_cambiar_portafolio"},
            ]]})
        return True

    return False
