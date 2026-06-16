import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from datetime import date
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase
from lib.parser import (
    parse_movement, categorize_from_keywords,
    parse_recurrente, parse_cuotas, strip_recurrente, strip_cuotas,
)
from lib.date_utils import mes_rango, add_months

app = FastAPI()

AYUDA = (
    "💰 *Billetera — Guía rápida*\n\n"

    "📥 *Registrar un gasto:*\n"
    "  `5000 comida`\n"
    "  `gasté 3000 en nafta`\n"
    "  `15000 ropa` → te pregunta la categoría\n\n"

    "📤 *Registrar un ingreso:*\n"
    "  `sueldo 80000`\n"
    "  `ingreso 50000 freelance`\n\n"

    "💵 *En dólares* — convertidos al oficial:\n"
    "  `100 dolares supermercado`\n"
    "  `2.49 usd spotify`\n\n"

    "🔁 *Gasto recurrente* — recordatorio mensual:\n"
    "  `40000 internet todos los 1 del mes`\n"
    "  `2.49 usd spotify todos los 15 del mes`\n"
    "  _(el bot te avisa cada mes para confirmar)_\n\n"

    "💳 *Compra en cuotas:*\n"
    "  `150000 tele 12 cuotas`\n"
    "  `500 usd laptop 6 cuotas`\n\n"

    "🎤 *Audio* — mandá un mensaje de voz.\n\n"

    "📋 *Comandos:*\n"
    "  `/presupuesto` — ver estado de tus presupuestos\n"
    "  `/presupuesto comida 20000` — fijar presupuesto mensual\n"
    "    _(categorías: super, comida, transporte, servicios,\n"
    "    entretenimiento, salud, ropa, vivienda, mascotas,\n"
    "    viajes, seguros, inversiones, compras, belleza,\n"
    "    suscripciones, otros)_\n"
    "  `/editar` — elegir un movimiento reciente para editar\n"
    "  `/editar comida` — filtrar por palabra y editar\n"
    "  `/borrar` — elegir un movimiento reciente para borrar\n"
    "  `/borrar netflix` — filtrar por palabra y borrar\n"
    "  `/recurrentes` — ver tus gastos recurrentes activos\n"
    "  `/inversiones` — ver recomendaciones y estado del portafolio\n"
    "  `/portafolio` — ver distribución de activos y P&L\n"
    "  `/precios` — cotizaciones en tiempo real (BTC, dólar, IOL)\n"
    "  `/id` — tu Telegram ID (para vincular el dashboard)\n"
    "  `/ayuda` — esta guía"
)

CAT_BUTTONS = [
    (1,  "🛒 Super"),    (3,  "🍽️ Comida"),  (2,  "🚗 Trans."),  (4,  "💡 Servicios"),
    (5,  "🎬 Entret."),  (6,  "🏥 Salud"),   (8,  "👕 Ropa"),    (10, "🏠 Vivienda"),
    (9,  "📚 Educ."),    (11, "🐾 Mascotas"), (12, "✈️ Viajes"),  (13, "🛡️ Seguros"),
    (14, "💰 Invers."),  (15, "💳 Compras"),  (16, "✨ Belleza"), (18, "📱 Suscripc."),
    (7,  "📌 Otros"),
]

# Palabras a ignorar al aprender keywords (demasiado genéricas)
_STOP_WORDS = {
    "para", "pero", "como", "este", "esta", "esos", "esas", "unos", "unas",
    "algo", "todo", "toda", "cada", "otro", "otra", "mismo", "desde", "hasta",
    "sobre", "entre", "bajo", "segun", "durante", "mediante", "cuota", "pago",
    "gasto", "compra", "oficial", "primero", "ultimo", "nuevo", "nueva",
}

CAT_NAME_MAP = {
    "super": 1, "supermercado": 1, "almacen": 1,
    "transporte": 2, "nafta": 2, "uber": 2,
    "comida": 3, "restaurante": 3, "delivery": 3,
    "servicios": 4, "internet": 4, "luz": 4, "gas": 4,
    "entretenimiento": 5, "entret": 5, "netflix": 5,
    "salud": 6, "farmacia": 6, "medico": 6,
    "otros": 7,
    "ropa": 8, "indumentaria": 8,
    "educacion": 9, "educación": 9, "cursos": 9,
    "vivienda": 10, "hogar": 10,
    "mascotas": 11, "veterinaria": 11,
    "viajes": 12, "turismo": 12,
    "seguros": 13, "impuestos": 13,
    "inversiones": 14, "ahorro": 14,
    "compras": 15, "online": 15,
    "belleza": 16, "gym": 16, "gimnasio": 16,
    "suscripciones": 18, "suscripcion": 18, "suscripción": 18,
}

DOLLAR_KEYWORDS = {"dolar", "dolares", "dólares", "usd", "u$s", "us$", "dólar"}


# ── Helpers de Telegram ───────────────────────────────────────────────────────

def _category_keyboard(movement_id: int) -> dict:
    rows = []
    for i in range(0, len(CAT_BUTTONS), 4):
        row = [
            {"text": label, "callback_data": f"cat:{movement_id}:{cat_id}"}
            for cat_id, label in CAT_BUTTONS[i:i + 4]
        ]
        rows.append(row)
    return {"inline_keyboard": rows}


def _monto_keyboard(movement_id: int, monto: float) -> dict:
    monto_k = int(monto * 1000)
    return {"inline_keyboard": [[
        {"text": f"✓ Son ${monto:,.0f}", "callback_data": f"monto_ok:{movement_id}"},
        {"text": f"× Son ${monto_k:,}", "callback_data": f"monto_x1000:{movement_id}"},
    ]]}


def _cuota_fecha_keyboard(plan_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "📅 Este mes", "callback_data": f"cuota_fecha:{plan_id}:0"},
        {"text": "📅 Próximo mes", "callback_data": f"cuota_fecha:{plan_id}:1"},
    ]]}


def _recurrente_keyboard(rec_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✓ Sí, registrar", "callback_data": f"recurrente_si:{rec_id}"},
        {"text": "✗ No hoy", "callback_data": f"recurrente_no:{rec_id}"},
    ]]}


def _edit_submenu_keyboard(movement_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "💰 Editar monto", "callback_data": f"edit_monto:{movement_id}"},
        {"text": "📂 Cambiar categoría", "callback_data": f"edit_cat:{movement_id}"},
        {"text": "🗑️ Borrar", "callback_data": f"del:{movement_id}"},
    ]]}


def _del_confirm_keyboard(movement_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✓ Sí, borrar", "callback_data": f"del_ok:{movement_id}"},
        {"text": "✗ Cancelar", "callback_data": f"del_no:{movement_id}"},
    ]]}


async def _recent_movements_keyboard(
    user_id: str, action: str, limit: int = 8, q: str = "", mes: str = ""
) -> tuple[dict | None, int]:
    """Lista de botones con movimientos. Retorna (keyboard, total_encontrados)."""
    supabase = get_supabase()
    query = (
        supabase.table("movimientos")
        .select("id, fecha, descripcion, monto, tipo, categorias(emoji)")
        .eq("usuario_id", user_id)
        .neq("estado", "anulado")
        .order("fecha", desc=True)
        .order("id", desc=True)
    )
    if q:
        query = query.ilike("descripcion", f"%{q}%")
    if mes:
        start, end = mes_rango(mes)
        query = query.gte("fecha", start).lt("fecha", end)
    if not q:
        query = query.limit(limit)

    rows = query.execute()
    if not rows.data:
        return None, 0

    buttons = []
    for r in rows.data:
        cat = r.get("categorias") or {}
        emoji = cat.get("emoji", "📌")
        signo = "-" if r["tipo"] == "gasto" else "+"
        desc = r["descripcion"][:22] + "…" if len(r["descripcion"]) > 22 else r["descripcion"]
        dia = r["fecha"][8:10] + "/" + r["fecha"][5:7]
        label = f"{emoji} {signo}${r['monto']:,.0f} {desc} ({dia})"
        buttons.append([{"text": label, "callback_data": f"{action}:{r['id']}"}])
    return {"inline_keyboard": buttons}, len(rows.data)


async def _send(chat_id: int, text: str, token: str,
                parse_mode: str = "Markdown", reply_markup: dict | None = None) -> dict:
    import httpx
    payload: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json=payload
        )
        return r.json()


async def _answer_callback(callback_id: str, token: str, text: str | None = None) -> None:
    import httpx
    payload: dict = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json=payload,
        )


async def _edit_message(chat_id: int, message_id: int, text: str, token: str,
                        parse_mode: str = "Markdown", reply_markup: dict | None = None) -> None:
    import httpx
    payload: dict = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        import json as _json
        payload["reply_markup"] = _json.dumps(reply_markup)
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json=payload,
        )


# ── Servicios externos ────────────────────────────────────────────────────────

async def _transcribe_voice(file_id: str, token: str) -> str | None:
    import httpx
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
        )
        if r.status_code != 200:
            return None
        file_path = r.json()["result"]["file_path"]
        r = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
        if r.status_code != 200:
            return None
        r = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {groq_key}"},
            files={"file": ("audio.ogg", r.content, "audio/ogg")},
            data={"model": "whisper-large-v3-turbo", "language": "es"},
        )
        return r.json().get("text", "").strip() or None if r.status_code == 200 else None


async def _get_dolar_oficial() -> float | None:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://dolarapi.com/v1/dolares/oficial")
            if r.status_code == 200:
                return float(r.json()["venta"])
    except Exception:
        pass
    return None


# ── Presupuesto helpers ───────────────────────────────────────────────────────

async def _check_presupuesto_alert(
    *, usuario_id: str, categoria_id: int, chat_id: int, token: str
) -> None:
    if categoria_id in (7, 17):
        return
    mes = date.today().strftime("%Y-%m")
    supabase = get_supabase()

    pres = (
        supabase.table("presupuestos")
        .select("monto")
        .eq("usuario_id", usuario_id)
        .eq("categoria_id", categoria_id)
        .eq("mes", mes)
        .execute()
    )
    if not pres.data:
        return

    presupuestado = pres.data[0]["monto"]
    start, end = mes_rango(mes)
    gastos = (
        supabase.table("movimientos")
        .select("monto")
        .eq("usuario_id", usuario_id)
        .eq("categoria_id", categoria_id)
        .neq("estado", "anulado")
        .gte("fecha", start)
        .lt("fecha", end)
        .eq("tipo", "gasto")
        .execute()
    )
    total = sum(r["monto"] for r in (gastos.data or []))
    pct = (total / presupuestado * 100) if presupuestado else 0

    if pct < 80:
        return

    cat = supabase.table("categorias").select("nombre, emoji").eq("id", categoria_id).single().execute()
    c = cat.data or {"nombre": "?", "emoji": "📌"}
    if pct >= 100:
        await _send(chat_id,
            f"🚨 Superaste el presupuesto de {c['emoji']} *{c['nombre']}*\n"
            f"Gastado: ${total:,.0f} / Presupuesto: ${presupuestado:,.0f}",
            token, parse_mode="Markdown")
    else:
        await _send(chat_id,
            f"⚠️ {c['emoji']} *{c['nombre']}*: {pct:.0f}% del presupuesto\n"
            f"Quedan: ${presupuestado - total:,.0f}",
            token, parse_mode="Markdown")


async def _send_objetivos_keyboard(user_id: str, chat_id: int, token: str, supabase=None, edit_message_id: int | None = None) -> None:
    """Teclado multi-select de objetivos de inversión."""
    import json as _json
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


async def _send_activos_keyboard(user_id: str, chat_id: int, token: str, supabase=None, edit_message_id: int | None = None) -> None:
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


async def _handle_inversiones_cmd(user_id: str, chat_id: int, token: str) -> None:
    supabase = get_supabase()
    perfil_r = supabase.table("perfiles_inversion").select("*").eq("usuario_id", user_id).limit(1).execute()
    p = perfil_r.data[0] if perfil_r.data else None

    if not p:
        await _send_objetivos_keyboard(user_id, chat_id, token, supabase)
        return

    # Perfil existente → mostrar resumen
    import json as _json
    obj_labels = {
        "ingresos_pasivos": "💰 Ingresos pasivos",
        "crecimiento": "📈 Crecer capital",
        "cobertura": "🛡️ Cobertura inflación",
        "meta_especifica": "🎯 Meta específica",
    }
    plazo_labels = {"corto": "< 1 año", "mediano": "1-3 años", "largo": "+3 años"}
    perfil_emoji = {"conservador": "🛡️", "moderado": "⚖️", "arriesgado": "🚀"}.get(p.get("perfil", ""), "📈")
    plazo_txt = plazo_labels.get(p.get("plazo", ""), "")
    # Soporta objetivos como JSON array o string legacy
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


async def _handle_precios_cmd(chat_id: int, token: str) -> None:
    """Muestra precios actuales de BTC, dólar y una acción IOL de prueba."""
    from lib.market_data import fetch_coingecko_precio, fetch_dolar_precio, fetch_iol_debug

    await _send(chat_id, "📡 Consultando mercados...", token, parse_mode="")

    lines = ["📊 *Precios de mercado*\n"]

    # BTC via CoinGecko
    try:
        btc = await fetch_coingecko_precio("BTCUSDT")
        lines.append(f"₿ *BTC* — ${btc['precio']:,.0f} USD" if btc else "₿ *BTC* — sin datos")
    except Exception:
        lines.append("₿ *BTC* — error")

    # ETH via CoinGecko
    try:
        eth = await fetch_coingecko_precio("ETHUSDT")
        if eth:
            lines.append(f"   *ETH* — ${eth['precio']:,.0f} USD")
    except Exception:
        pass

    lines.append("")

    # Dólar via dolarapi
    for tipo, label in [("oficial", "Oficial"), ("blue", "Blue"), ("cripto", "Cripto")]:
        try:
            d = await fetch_dolar_precio(tipo)
            lines.append(f"💵 *{label}* — ${d['precio']:,.2f} ARS" if d else f"💵 {label} — sin datos")
        except Exception:
            lines.append(f"💵 {label} — error")

    lines.append("")

    # IOL (AAPL como prueba de conexión)
    try:
        iol = await fetch_iol_debug("AAPL")
        if not iol["token_ok"]:
            lines.append("🏢 *IOL* — sin token (verificar IOL\\_USER / IOL\\_PASSWORD)")
        else:
            ind = iol.get("individual", {})
            if ind.get("status") == 200 and isinstance(ind.get("body"), dict):
                body = ind["body"]
                precio = body.get("ultimoPrecio") or body.get("ultimo") or body.get("price") or "?"
                lines.append(f"🏢 *AAPL (CEDEAR)* — ${precio} ARS ✅")
            else:
                lines.append(f"🏢 *IOL* — token OK, AAPL status {ind.get('status', '?')}")
    except Exception:
        lines.append("🏢 *IOL* — error al consultar")

    lines.append("\nUsá /iol\\_debug para ver respuesta completa de IOL")
    await _send(chat_id, "\n".join(lines), token)


async def _handle_portafolio_cmd(user_id: str, chat_id: int, token: str) -> None:
    import json as _json
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


async def _handle_presupuesto_cmd(user_id: str, chat_id: int, args: str, token: str) -> None:
    mes = date.today().strftime("%Y-%m")
    supabase = get_supabase()

    # /presupuesto comida 20000 → crear/actualizar
    parts = args.strip().split() if args.strip() else []
    if len(parts) >= 2:
        cat_key = parts[0].lower()
        try:
            monto = float(parts[1].replace(".", "").replace(",", "."))
        except ValueError:
            await _send(chat_id, "Formato: `/presupuesto comida 20000`", token)
            return

        cat_id = CAT_NAME_MAP.get(cat_key)
        if not cat_id:
            await _send(chat_id, f"No reconozco la categoría *{parts[0]}*.\nUsá: super, comida, transporte, servicios, etc.", token)
            return

        existing = (
            supabase.table("presupuestos")
            .select("id")
            .eq("usuario_id", user_id)
            .eq("categoria_id", cat_id)
            .eq("mes", mes)
            .execute()
        )
        if existing.data:
            supabase.table("presupuestos").update({"monto": monto}).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase.table("presupuestos").insert({
                "usuario_id": user_id, "categoria_id": cat_id, "monto": monto, "mes": mes
            }).execute()

        cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", cat_id).single().execute()
        c = cat_row.data or {"nombre": "?", "emoji": "📌"}
        await _send(chat_id, f"✅ Presupuesto *{c['emoji']} {c['nombre']}*: ${monto:,.0f} para {mes}", token)
        return

    # /presupuesto → mostrar estado
    pres_rows = (
        supabase.table("presupuestos")
        .select("categoria_id, monto, categorias(nombre, emoji)")
        .eq("usuario_id", user_id)
        .eq("mes", mes)
        .execute()
    )

    if not pres_rows.data:
        await _send(chat_id,
            f"No tenés presupuestos para {mes}.\n\n"
            "Configurá uno con:\n`/presupuesto comida 20000`", token)
        return

    start, end = mes_rango(mes)
    mov_rows = (
        supabase.table("movimientos")
        .select("categoria_id, monto")
        .eq("usuario_id", user_id)
        .eq("tipo", "gasto")
        .neq("estado", "anulado")
        .gte("fecha", start)
        .lt("fecha", end)
        .execute()
    )
    gastos_por_cat: dict[int, float] = {}
    for r in (mov_rows.data or []):
        cid = r["categoria_id"]
        gastos_por_cat[cid] = gastos_por_cat.get(cid, 0) + r["monto"]

    mes_nombre = date(int(mes[:4]), int(mes[5:7]), 1).strftime("%B %Y")
    lines = [f"💰 *Presupuestos {mes_nombre}*\n"]
    for p in sorted(pres_rows.data, key=lambda x: -(gastos_por_cat.get(x["categoria_id"], 0) / x["monto"])):
        cat = p.get("categorias") or {}
        cid = p["categoria_id"]
        presup = p["monto"]
        gasto = gastos_por_cat.get(cid, 0)
        pct = gasto / presup * 100 if presup else 0
        barra = "▓" * int(min(pct, 100) / 10) + "░" * (10 - int(min(pct, 100) / 10))
        estado = " 🚨" if pct >= 100 else " ⚠️" if pct >= 80 else ""
        lines.append(
            f"{cat.get('emoji','📌')} *{cat.get('nombre','?')}*{estado}\n"
            f"{barra} {pct:.0f}%  ${gasto:,.0f} / ${presup:,.0f}"
        )
    await _send(chat_id, "\n\n".join(lines), token)


# ── Helpers de fecha ──────────────────────────────────────────────────────────

def _first_of_month(d: date) -> date:
    return d.replace(day=1)


# ── Lógica de cuotas ──────────────────────────────────────────────────────────

async def _create_cuota_movimientos(plan_id: int, primer_fecha: date, token: str) -> None:
    supabase = get_supabase()
    plan = supabase.table("cuotas_plan").select("*").eq("id", plan_id).single().execute()
    if not plan.data:
        return
    p = plan.data
    movimientos = [
        {
            "usuario_id": p["usuario_id"],
            "fecha": add_months(primer_fecha, i).isoformat(),
            "descripcion": f"{p['descripcion']} (cuota {i + 1}/{p['num_cuotas']})",
            "monto": p["monto_cuota"],
            "categoria_id": p["categoria_id"],
            "tipo": "gasto",
            "origen": "telegram",
            "estado": "confirmado",
        }
        for i in range(p["num_cuotas"])
    ]
    supabase.table("movimientos").insert(movimientos).execute()
    supabase.table("cuotas_plan").update(
        {"fecha_primera_cuota": primer_fecha.isoformat()}
    ).eq("id", plan_id).execute()

    chat_id = int(p["usuario_id"])
    ultima = add_months(primer_fecha, p["num_cuotas"] - 1)
    await _send(
        chat_id,
        f"✅ *{p['descripcion']}* en {p['num_cuotas']} cuotas\n"
        f"💳 ${p['monto_cuota']:,.0f}/mes · primera: {primer_fecha.strftime('%d/%m/%Y')}\n"
        f"📆 Última cuota: {ultima.strftime('%m/%Y')}",
        token,
    )


# ── Lógica principal ──────────────────────────────────────────────────────────

def _detect_currency(text: str) -> str:
    words = set(text.lower().split())
    return "USD" if words & DOLLAR_KEYWORDS else "ARS"


def _extract_keywords(descripcion: str) -> list[str]:
    """Extrae palabras útiles de una descripción para aprender a categorizar."""
    # Limpiar anotaciones automáticas añadidas por el bot
    clean = re.sub(r'\(cuota \d+/\d+\)', '', descripcion)
    clean = re.sub(r'\(USD.*?\)', '', clean)
    clean = re.sub(r'@ \$[\d.,]+.*', '', clean)
    words = re.findall(r'[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{4,}', clean.lower())
    return [w for w in words if w not in _STOP_WORDS]


async def _save_learned_keywords(descripcion: str, categoria_id: int, usuario_id: str) -> None:
    """Guarda las palabras de la descripción como keywords aprendidas para ese usuario."""
    words = _extract_keywords(descripcion)
    if not words:
        return
    supabase = get_supabase()
    for word in words[:6]:
        try:
            supabase.table("keywords_aprendidas").upsert(
                {"usuario_id": usuario_id, "keyword": word, "categoria_id": categoria_id},
                on_conflict="usuario_id,keyword",
            ).execute()
        except Exception:
            pass


async def _categorize(descripcion: str, usuario_id: str) -> int:
    """Categoriza usando keywords hardcodeadas primero, luego las aprendidas por el usuario."""
    cat_id = categorize_from_keywords(descripcion)
    if cat_id != 7:  # Si no es Otros, confiamos en el hardcoded
        return cat_id

    words = _extract_keywords(descripcion)
    if not words:
        return 7

    # Una sola query para todas las palabras en lugar de N queries
    supabase = get_supabase()
    r = (
        supabase.table("keywords_aprendidas")
        .select("keyword, categoria_id")
        .eq("usuario_id", usuario_id)
        .in_("keyword", words)
        .execute()
    )
    if r.data:
        kw_to_cat = {row["keyword"]: row["categoria_id"] for row in r.data}
        for word in words:
            if word in kw_to_cat:
                return kw_to_cat[word]

    return 7


async def _save_and_confirm(
    *,
    chat_id: int,
    token: str,
    user_id: str,
    descripcion: str,
    monto: float,
    tipo: str,
    estado: str = "confirmado",
    nota_monto_bajo: bool = False,
    fecha: str | None = None,
) -> None:
    categoria_id = 17 if tipo == "ingreso" else await _categorize(descripcion, user_id)

    supabase = get_supabase()
    result = supabase.table("movimientos").insert({
        "usuario_id": user_id,
        "fecha": fecha or date.today().isoformat(),
        "descripcion": descripcion,
        "monto": monto,
        "categoria_id": categoria_id,
        "tipo": tipo,
        "origen": "telegram",
        "estado": estado,
    }).execute()

    movement_id = result.data[0]["id"] if result.data else None

    if nota_monto_bajo and movement_id:
        await _send(
            chat_id,
            f"🤔 Registré *${monto:,.0f}* — ¿está bien o querías decir *${monto * 1000:,.0f}*?",
            token,
            reply_markup=_monto_keyboard(movement_id, monto),
        )
        return

    if categoria_id == 7 and tipo == "gasto" and movement_id:
        await _send(
            chat_id,
            f"📌 Guardé *${monto:,.0f}* — ¿en qué categoría va *{descripcion}*?",
            token,
            reply_markup=_category_keyboard(movement_id),
        )
        return

    cat_row = supabase.table("categorias").select("nombre, emoji").eq("id", categoria_id).single().execute()
    cat_name = cat_row.data.get("nombre", "Otros") if cat_row.data else "Otros"
    cat_emoji = cat_row.data.get("emoji", "📌") if cat_row.data else "📌"
    signo = "-" if tipo == "gasto" else "+"
    await _send(chat_id, f"✅ Registrado: {signo}${monto:,.0f} · {cat_emoji} {cat_name}", token, parse_mode="")

    if tipo == "gasto" and categoria_id not in (7, 17):
        await _check_presupuesto_alert(
            usuario_id=user_id, categoria_id=categoria_id, chat_id=chat_id, token=token
        )


async def _process_text(text: str, user_id: str, chat_id: int, token: str) -> None:
    # ── Edición de monto pendiente ──
    supabase = get_supabase()
    pending = (
        supabase.table("movimientos")
        .select("id, descripcion, monto")
        .eq("usuario_id", user_id)
        .eq("estado", "pendiente_edicion_monto")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if pending.data:
        mov = pending.data[0]
        # Intentar extraer un número del mensaje
        num_match = re.search(r"[\d]+(?:[.,]\d+)?", text.replace(".", ""))
        if num_match:
            nuevo_monto = float(num_match.group().replace(",", "."))
            supabase.table("movimientos").update(
                {"monto": nuevo_monto, "estado": "confirmado"}
            ).eq("id", mov["id"]).execute()
            await _send(chat_id,
                f"✅ *{mov['descripcion']}* actualizado: ${nuevo_monto:,.0f}", token)
            return
        # Si no es un número, continuar procesando como movimiento nuevo
        # (cancelar el estado pendiente para no quedar atrapado)
        supabase.table("movimientos").update({"estado": "confirmado"}).eq("id", mov["id"]).execute()

    dia_mes = parse_recurrente(text)
    num_cuotas = parse_cuotas(text)

    if dia_mes:
        clean = strip_recurrente(text)
    elif num_cuotas:
        clean = strip_cuotas(text)
    else:
        clean = text

    parsed = parse_movement(clean) or (parse_movement(text) if clean != text else None)
    if not parsed:
        await _send(chat_id, "No entendí 🤔\n\n" + AYUDA, token)
        return

    monto = parsed["monto"]
    descripcion = parsed["descripcion"]
    tipo = parsed["tipo"]

    if monto <= 0:
        await _send(chat_id, "El monto debe ser mayor a cero 🤔", token, parse_mode="")
        return

    # ── Gasto recurrente ──
    if dia_mes and tipo == "gasto":
        # Conversión USD si corresponde
        moneda = _detect_currency(text)
        if moneda == "USD":
            tasa = await _get_dolar_oficial()
            if not tasa:
                await _send(chat_id, "No pude obtener el tipo de cambio 😕 Intentá de nuevo.", token, parse_mode="")
                return
            # Limpiar "usd"/"dolar" del inicio de la descripción
            desc_limpia = re.sub(r"^(?:usd|dolar|dólares?)\s+", "", descripcion, flags=re.IGNORECASE).strip()
            monto = round(monto * tasa)
            descripcion = f"{desc_limpia} (USD @ ${tasa:,.0f} oficial)"

        categoria_id = await _categorize(descripcion, user_id)
        supabase = get_supabase()
        result = supabase.table("recurrentes").insert({
            "usuario_id": user_id,
            "descripcion": descripcion,
            "monto": monto,
            "categoria_id": categoria_id,
            "tipo": tipo,
            "dia_del_mes": dia_mes,
            "activo": True,
        }).execute()
        sufijo = {1: "ro", 2: "do", 3: "ro"}.get(dia_mes, "to")
        await _send(chat_id,
            f"🔁 Recordatorio configurado:\n*{descripcion}* — ${monto:,.0f} — todos los *{dia_mes}{sufijo}* del mes",
            token)
        return

    # ── Compra en cuotas ──
    if num_cuotas and tipo == "gasto":
        moneda = _detect_currency(text)
        if moneda == "USD":
            tasa = await _get_dolar_oficial()
            if not tasa:
                await _send(chat_id, "No pude obtener el tipo de cambio 😕 Intentá de nuevo.", token, parse_mode="")
                return
            desc_limpia = re.sub(r"^(?:usd|dolar|dólares?)\s+", "", descripcion, flags=re.IGNORECASE).strip()
            monto = round(monto * tasa)
            descripcion = f"{desc_limpia} (USD @ ${tasa:,.0f} oficial)"

        monto_cuota = round(monto / num_cuotas, 2)
        categoria_id = await _categorize(descripcion, user_id)
        supabase = get_supabase()
        result = supabase.table("cuotas_plan").insert({
            "usuario_id": user_id,
            "descripcion": descripcion,
            "monto_total": monto,
            "monto_cuota": monto_cuota,
            "num_cuotas": num_cuotas,
            "categoria_id": categoria_id,
        }).execute()
        plan_id = result.data[0]["id"] if result.data else None
        if not plan_id:
            await _send(chat_id, "Error guardando el plan 😕", token, parse_mode="")
            return
        await _send(chat_id,
            f"💳 *{descripcion}* en {num_cuotas} cuotas de *${monto_cuota:,.0f}*\n¿Primera cuota?",
            token, reply_markup=_cuota_fecha_keyboard(plan_id))
        return

    # ── Flujo normal ──
    moneda = _detect_currency(text)
    if moneda == "USD":
        tasa = await _get_dolar_oficial()
        if not tasa:
            await _send(chat_id, "No pude obtener el tipo de cambio 😕 Intentá de nuevo.", token, parse_mode="")
            return
        monto_ars = round(monto * tasa)
        descripcion = f"{descripcion} (USD {monto:,.0f} @ ${tasa:,.0f} oficial)"
        await _save_and_confirm(chat_id=chat_id, token=token, user_id=user_id,
                                descripcion=descripcion, monto=monto_ars, tipo=tipo)
        return

    monto_bajo = monto < 1000
    await _save_and_confirm(
        chat_id=chat_id, token=token, user_id=user_id,
        descripcion=descripcion, monto=monto, tipo=tipo,
        estado="pendiente_confirmacion" if monto_bajo else "confirmado",
        nota_monto_bajo=monto_bajo,
    )


# ── Webhook ───────────────────────────────────────────────────────────────────

@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not webhook_secret:
        return JSONResponse({"error": "TELEGRAM_WEBHOOK_SECRET no configurado"}, status_code=500)
    if request.headers.get("x-telegram-bot-api-secret-token", "") != webhook_secret:
        return JSONResponse({"error": "unauthorized"}, status_code=403)

    data = await request.json()
    token = os.environ.get("TELEGRAM_TOKEN", "")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    if "callback_query" in data:
        cq = data["callback_query"]
        callback_id = cq["id"]
        payload = cq.get("data", "")
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        callback_user_id = str(cq["from"]["id"])
        supabase = get_supabase()
        parts = payload.split(":")

        if parts[0] == "cat" and len(parts) == 3:
            movement_id, cat_id = int(parts[1]), int(parts[2])
            supabase.table("movimientos").update(
                {"categoria_id": cat_id, "estado": "confirmado"}
            ).eq("id", movement_id).eq("usuario_id", callback_user_id).execute()
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
                # Aprender keywords de esta categorización manual
                await _save_learned_keywords(desc, cat_id, uid)
                if token:
                    await _check_presupuesto_alert(
                        usuario_id=uid, categoria_id=cat_id, chat_id=chat_id, token=token
                    )

        elif parts[0] == "monto_ok" and len(parts) == 2:
            movement_id = int(parts[1])
            supabase.table("movimientos").update({"estado": "confirmado"}).eq("id", movement_id).eq("usuario_id", callback_user_id).execute()
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

        elif parts[0] == "monto_x1000" and len(parts) == 2:
            movement_id = int(parts[1])
            row = supabase.table("movimientos").select("monto, tipo, descripcion, usuario_id, categorias(nombre, emoji)").eq("id", movement_id).eq("usuario_id", callback_user_id).single().execute()
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
                }).eq("id", movement_id).eq("usuario_id", callback_user_id).execute()
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

        elif parts[0] == "cuota_fecha" and len(parts) == 3:
            plan_id, proximo = int(parts[1]), int(parts[2])
            plan_check = supabase.table("cuotas_plan").select("usuario_id").eq("id", plan_id).single().execute()
            if not plan_check.data or plan_check.data["usuario_id"] != callback_user_id:
                if token:
                    await _answer_callback(callback_id, token)
                return JSONResponse({"ok": True})
            hoy = date.today()
            # Si el usuario elige "este mes" pero ya pasó el día 1, usar el mes siguiente
            meses = proximo if (proximo > 0 or hoy.day == 1) else 1
            primer_fecha = _first_of_month(add_months(hoy, meses))
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"📅 Primera cuota: {primer_fecha.strftime('%d/%m/%Y')} — creando movimientos...", token)
                await _create_cuota_movimientos(plan_id, primer_fecha, token)

        elif parts[0] == "recurrente_si" and len(parts) == 2:
            rec_id = int(parts[1])
            rec = supabase.table("recurrentes").select("*").eq("id", rec_id).single().execute()
            if rec.data and rec.data["usuario_id"] != callback_user_id:
                if token:
                    await _answer_callback(callback_id, token)
                return JSONResponse({"ok": True})
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

        elif parts[0] == "recurrente_no" and len(parts) == 2:
            rec_id = int(parts[1])
            supabase.table("recurrentes").update(
                {"ultimo_recordatorio": date.today().isoformat()}
            ).eq("id", rec_id).eq("usuario_id", callback_user_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id, "⏭ Saltado por hoy.", token)

        # Seleccionar movimiento para editar → submenu
        elif parts[0] == "edit" and len(parts) == 2:
            movement_id = int(parts[1])
            row = supabase.table("movimientos").select("descripcion, monto, tipo").eq("id", movement_id).eq("usuario_id", callback_user_id).single().execute()
            if row.data and token:
                r = row.data
                signo = "-" if r["tipo"] == "gasto" else "+"
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"✏️ *{r['descripcion']}* — {signo}${r['monto']:,.0f}\n¿Qué querés hacer?", token)
                await _send(chat_id, "Elegí una opción:", token, parse_mode="",
                            reply_markup=_edit_submenu_keyboard(movement_id))

        # Editar monto: marcar como pendiente y pedir nuevo valor
        elif parts[0] == "edit_monto" and len(parts) == 2:
            movement_id = int(parts[1])
            supabase.table("movimientos").update(
                {"estado": "pendiente_edicion_monto"}
            ).eq("id", movement_id).eq("usuario_id", callback_user_id).execute()
            row = supabase.table("movimientos").select("descripcion").eq("id", movement_id).eq("usuario_id", callback_user_id).single().execute()
            desc = row.data["descripcion"] if row.data else "?"
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"💰 Enviá el nuevo monto para *{desc}*:", token)

        # Editar categoría: mostrar teclado de categorías
        elif parts[0] == "edit_cat" and len(parts) == 2:
            movement_id = int(parts[1])
            row = supabase.table("movimientos").select("descripcion").eq("id", movement_id).eq("usuario_id", callback_user_id).single().execute()
            desc = row.data["descripcion"] if row.data else "?"
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"📂 ¿A qué categoría movemos *{desc}*?", token)
                await _send(chat_id, "Elegí categoría:", token, parse_mode="",
                            reply_markup=_category_keyboard(movement_id))

        # Borrar: pedir confirmación
        elif parts[0] == "del" and len(parts) == 2:
            movement_id = int(parts[1])
            row = supabase.table("movimientos").select("descripcion, monto, tipo").eq("id", movement_id).eq("usuario_id", callback_user_id).single().execute()
            if row.data and token:
                r = row.data
                signo = "-" if r["tipo"] == "gasto" else "+"
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    f"🗑️ ¿Borrar *{r['descripcion']}* ({signo}${r['monto']:,.0f})?", token)
                await _send(chat_id, "¿Confirmar?", token, parse_mode="",
                            reply_markup=_del_confirm_keyboard(movement_id))

        # Confirmar borrado (soft delete: estado=anulado)
        elif parts[0] == "del_ok" and len(parts) == 2:
            movement_id = int(parts[1])
            row = supabase.table("movimientos").select("descripcion, monto").eq("id", movement_id).eq("usuario_id", callback_user_id).single().execute()
            supabase.table("movimientos").update({"estado": "anulado"}).eq("id", movement_id).eq("usuario_id", callback_user_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                desc = row.data["descripcion"] if row.data else "?"
                await _edit_message(chat_id, message_id, f"🗑️ *{desc}* eliminado.", token)

        # Cancelar borrado
        elif parts[0] == "del_no" and len(parts) == 2:
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id, "✕ Cancelado.", token)

        # Toggle de objetivo (multi-select, primer paso del setup)
        elif parts[0] == "inv_toggle_objetivo" and len(parts) == 2:
            import json as _json
            objetivo = parts[1]
            if objetivo not in ("ingresos_pasivos", "crecimiento", "cobertura", "meta_especifica"):
                return JSONResponse({"ok": True})

            perfil_r = supabase.table("perfiles_inversion").select("objetivos").eq("usuario_id", callback_user_id).limit(1).execute()
            if not perfil_r.data:
                supabase.table("perfiles_inversion").insert({
                    "usuario_id": callback_user_id,
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
                }).eq("usuario_id", callback_user_id).execute()

            if token:
                await _answer_callback(callback_id, token)
            await _send_objetivos_keyboard(callback_user_id, chat_id, token, supabase, edit_message_id=message_id)

        # Confirmar objetivos → ir a plazo
        elif parts[0] == "inv_confirmar_objetivos":
            import json as _json
            perfil_r = supabase.table("perfiles_inversion").select("objetivos").eq("usuario_id", callback_user_id).limit(1).execute()
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
                }).eq("usuario_id", callback_user_id).execute()
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

        # Elegir plazo (segundo paso)
        elif parts[0] == "inv_plazo" and len(parts) == 2:
            plazo = parts[1]
            if plazo in ("corto", "mediano", "largo"):
                supabase.table("perfiles_inversion").update({
                    "plazo": plazo,
                    "estado": "configurando_capital",
                    "actualizado_at": "now()",
                }).eq("usuario_id", callback_user_id).execute()
                plazo_label = {"corto": "< 1 año", "mediano": "1-3 años", "largo": "+ 3 años"}[plazo]
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id,
                        f"✅ Plazo: *{plazo_label}*\n\n"
                        "💰 *¿Cuánto capital tenés disponible para invertir?* (en ARS)\n"
                        "_Respondé con un número, ej: `500000`_\n"
                        "_O escribí `skip` para omitirlo_",
                        token)

        elif parts[0] == "inv_cambiar_perfil":
            if token:
                await _answer_callback(callback_id, token)
            # Limpiar objetivos para que empiece fresco
            supabase.table("perfiles_inversion").update({
                "objetivos": "[]",
                "estado": "configurando_objetivos",
                "actualizado_at": "now()",
            }).eq("usuario_id", callback_user_id).execute()
            await _send_objetivos_keyboard(callback_user_id, chat_id, token, supabase, edit_message_id=message_id)

        # Aceptar recomendación de inversión
        elif parts[0] == "inv_ok" and len(parts) == 2:
            rec_id = int(parts[1])
            rec_r = supabase.table("recomendaciones").select("*").eq("id", rec_id).eq("usuario_id", callback_user_id).limit(1).execute()
            rec = rec_r.data[0] if rec_r.data else None
            if rec and rec["estado"] == "pendiente":
                supabase.table("recomendaciones").update({
                    "estado": "aceptada", "decidido_at": "now()"
                }).eq("id", rec_id).execute()
                supabase.table("decisiones_inversion").insert({
                    "usuario_id": callback_user_id,
                    "recomendacion_id": rec_id,
                    "accion": "aceptada",
                    "precio_entrada": rec.get("precio_recomendacion"),
                }).execute()
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id,
                        "✅ *Recomendación aceptada* — acordate de ejecutar la orden en IOL/exchange.", token)

        # Rechazar recomendación de inversión
        elif parts[0] == "inv_no" and len(parts) == 2:
            rec_id = int(parts[1])
            rec_r = supabase.table("recomendaciones").select("id, estado").eq("id", rec_id).eq("usuario_id", callback_user_id).limit(1).execute()
            rec = rec_r.data[0] if rec_r.data else None
            if rec and rec["estado"] == "pendiente":
                supabase.table("recomendaciones").update({
                    "estado": "rechazada", "decidido_at": "now()"
                }).eq("id", rec_id).execute()
                supabase.table("decisiones_inversion").insert({
                    "usuario_id": callback_user_id,
                    "recomendacion_id": rec_id,
                    "accion": "rechazada",
                }).execute()
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id, "❌ Recomendación rechazada.", token)

        # Toggle de activo en selección de activos
        elif parts[0] == "inv_toggle" and len(parts) == 2:
            activo_id = int(parts[1])
            existe_r = supabase.table("usuario_activos").select("id").eq("usuario_id", callback_user_id).eq("activo_id", activo_id).limit(1).execute()
            if existe_r.data:
                supabase.table("usuario_activos").delete().eq("usuario_id", callback_user_id).eq("activo_id", activo_id).execute()
            else:
                supabase.table("usuario_activos").insert({"usuario_id": callback_user_id, "activo_id": activo_id}).execute()

            if token:
                await _answer_callback(callback_id, token)
            # Editar el mismo mensaje para actualizar los checkmarks
            await _send_activos_keyboard(callback_user_id, chat_id, token, supabase, edit_message_id=message_id)

        # Confirmar selección de activos → portafolio si hay capital, si no activo directo
        elif parts[0] == "inv_confirmar_activos":
            seleccionados_r = supabase.table("usuario_activos").select("activo_id").eq("usuario_id", callback_user_id).execute()
            n = len(seleccionados_r.data or [])
            if n == 0:
                if token:
                    await _answer_callback(callback_id, token, text="Seleccioná al menos un activo")
            else:
                perfil_r2 = supabase.table("perfiles_inversion").select("capital_disponible, perfil, objetivos, plazo").eq("usuario_id", callback_user_id).limit(1).execute()
                capital = perfil_r2.data[0].get("capital_disponible") if perfil_r2.data else None

                if capital and n > 1:
                    # Ir a configurar distribución de portafolio
                    supabase.table("perfiles_inversion").update({
                        "estado": "configurando_portafolio",
                        "actualizado_at": "now()",
                    }).eq("usuario_id", callback_user_id).execute()

                    # Obtener precios actuales de los activos seleccionados
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
                    }).eq("usuario_id", callback_user_id).execute()
                    if token:
                        await _answer_callback(callback_id, token)
                        await _edit_message(chat_id, message_id,
                            f"✅ *Perfil listo*\nVas a recibir señales para los {n} activo{'s' if n != 1 else ''} seleccionados.\n\n"
                            "Usá /inversiones o /portafolio para ver el estado.",
                            token)

        # Confirmar distribución de portafolio
        elif parts[0] == "inv_confirmar_portafolio":
            import json as _json
            portafolio_raw = supabase.table("perfiles_inversion").select("portafolio_pendiente").eq("usuario_id", callback_user_id).limit(1).execute()
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
                        }).eq("usuario_id", callback_user_id).eq("activo_id", activo_info["id"]).execute()

            supabase.table("perfiles_inversion").update({
                "estado": "activo",
                "portafolio_pendiente": None,
                "actualizado_at": "now()",
            }).eq("usuario_id", callback_user_id).execute()

            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✅ *Portafolio configurado*\n\nUsá /portafolio para ver tu distribución y precios actuales.",
                    token)

        elif parts[0] == "inv_cambiar_portafolio":
            supabase.table("perfiles_inversion").update({
                "portafolio_pendiente": None,
                "actualizado_at": "now()",
            }).eq("usuario_id", callback_user_id).execute()
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "✏️ Escribí cómo querés dividir el capital.\n"
                    "Ej: `40% BTC, 60% AAPL` o `vos decidí`.",
                    token)

        return JSONResponse({"ok": True})

    # ── Mensajes ───────────────────────────────────────────────────────────────
    if "message" not in data:
        return JSONResponse({"ok": True})

    message = data["message"]
    user_id = str(message["from"]["id"])
    chat_id = message["chat"]["id"]

    if "voice" in message or "audio" in message:
        if not token:
            return JSONResponse({"ok": True})
        file_id = message.get("voice", message.get("audio", {})).get("file_id")
        if not file_id:
            return JSONResponse({"ok": True})
        if not os.environ.get("GROQ_API_KEY"):
            await _send(chat_id, "🎤 Audios no configurados (falta GROQ_API_KEY).", token)
            return JSONResponse({"ok": True})
        await _send(chat_id, "🎤 Transcribiendo...", token, parse_mode="")
        transcribed = await _transcribe_voice(file_id, token)
        if not transcribed:
            await _send(chat_id, "No pude entender el audio 🙁", token, parse_mode="")
            return JSONResponse({"ok": True})
        await _send(chat_id, f'🗣 _"{transcribed}"_', token)
        # Si el usuario está en paso de descripción libre, el audio actúa como texto
        _perfil_estado_r = get_supabase().table("perfiles_inversion").select("estado").eq("usuario_id", user_id).limit(1).execute()
        _estado_inv = _perfil_estado_r.data[0].get("estado") if _perfil_estado_r.data else None
        if _estado_inv in ("configurando_capital", "configurando_descripcion", "configurando_activos"):
            text = transcribed
        else:
            await _process_text(transcribed, user_id, chat_id, token)
            return JSONResponse({"ok": True})

    text = message.get("text", "").strip() if "text" in message else (text if "voice" in message or "audio" in message else "")
    if not text:
        return JSONResponse({"ok": True})

    # ── Setup de perfil de inversión (respuestas de texto a pasos del wizard) ──
    if token and not text.startswith("/"):
        supabase_check = get_supabase()
        perfil_check = supabase_check.table("perfiles_inversion").select("*").eq("usuario_id", user_id).limit(1).execute()
        estado_perfil = perfil_check.data[0].get("estado") if perfil_check.data else None

        if estado_perfil == "configurando_capital":
            clean = text.replace(".", "").replace(",", "").replace("$", "").strip()
            if text.lower() in ("skip", "/skip"):
                capital = None
            else:
                try:
                    capital = float(clean)
                except ValueError:
                    await _send(chat_id,
                        "No entendí el monto. Enviá solo el número (ej: `500000`) o escribí `skip` para omitirlo.", token)
                    return JSONResponse({"ok": True})

            upd: dict = {"estado": "configurando_descripcion", "actualizado_at": "now()"}
            if capital is not None:
                upd["capital_disponible"] = capital
            supabase_check.table("perfiles_inversion").update(upd).eq("usuario_id", user_id).execute()

            await _send(chat_id,
                "📝 *Casi listo.*\n\n"
                "Contame en tus propias palabras qué buscás con tus inversiones. "
                "Por ejemplo: qué te preocupa, si querés cubrirte del dólar, si ya tenés algo invertido, etc.\n\n"
                "_También podés mandar un audio. Escribí `skip` para saltearlo._",
                token)
            return JSONResponse({"ok": True})

        if estado_perfil == "configurando_descripcion":
            import json as _json
            from lib.claude_invest import sugerir_activos_para_perfil
            descripcion = text if text.lower() not in ("skip", "/skip") else ""

            supabase_check.table("perfiles_inversion").update({
                "descripcion_libre": descripcion or None,
                "actualizado_at": "now()",
            }).eq("usuario_id", user_id).execute()

            await _send(chat_id, "🤖 Analizando tu perfil...", token, parse_mode="")

            perfil_data = perfil_check.data[0]
            activos_r = supabase_check.table("activos").select("id, codigo, nombre, tipo, moneda").eq("activo", True).execute()
            activos_disponibles = activos_r.data or []

            # Obtener objetivos como lista
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
            )

            if sugerencia:
                supabase_check.table("perfiles_inversion").update({
                    "perfil": sugerencia.get("perfil_riesgo", "moderado"),
                    "estado": "configurando_activos",
                    "actualizado_at": "now()",
                }).eq("usuario_id", user_id).execute()

                # Pre-seleccionar activos sugeridos
                activos_sugeridos = sugerencia.get("activos_sugeridos", [])
                codigos_sugeridos = {a["codigo"].upper() if isinstance(a, dict) else a.upper() for a in activos_sugeridos}
                for activo in activos_disponibles:
                    if activo["codigo"] in codigos_sugeridos:
                        try:
                            supabase_check.table("usuario_activos").insert({
                                "usuario_id": user_id, "activo_id": activo["id"]
                            }).execute()
                        except Exception:
                            pass

                # Armar mensaje con explicaciones por activo
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
                supabase_check.table("perfiles_inversion").update({
                    "estado": "configurando_activos",
                    "actualizado_at": "now()",
                }).eq("usuario_id", user_id).execute()
                await _send(chat_id, "No pude analizar el perfil ahora, pero podés elegir los activos manualmente:", token, parse_mode="")

            await _send_activos_keyboard(user_id, chat_id, token, supabase_check)
            return JSONResponse({"ok": True})

        if estado_perfil == "configurando_activos":
            import json as _json
            from lib.claude_invest import responder_pregunta_activos

            # Detectar "listo" → re-enviar keyboard
            _listo_keywords = {"listo", "ok", "dale", "bueno", "confirmar", "continuar", "siguiente", "ya", "confirmo"}
            if text.lower().strip() in _listo_keywords:
                await _send(chat_id, "👍 Tocá *Confirmar selección* en el teclado para avanzar 👆", token)
                await _send_activos_keyboard(user_id, chat_id, token, supabase_check)
                return JSONResponse({"ok": True})

            perfil_data = perfil_check.data[0]
            activos_r = supabase_check.table("activos").select("id, codigo, nombre, tipo, moneda").eq("activo", True).execute()
            activos_disponibles = activos_r.data or []

            _obj_raw = perfil_data.get("objetivos") or perfil_data.get("objetivo") or "[]"
            try:
                objetivos_lista = _json.loads(_obj_raw) if _obj_raw.startswith("[") else [_obj_raw] if _obj_raw else []
            except Exception:
                objetivos_lista = []

            ua_r = supabase_check.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
            seleccionados_ids = {row["activo_id"] for row in (ua_r.data or [])}
            seleccionados_codigos = [a["codigo"] for a in activos_disponibles if a["id"] in seleccionados_ids]

            # Cargar historial de chat
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
                # Guardar par pregunta/respuesta en historial (max 20 entradas)
                historial.append({"u": text, "b": respuesta})
                if len(historial) > 20:
                    historial = historial[-20:]
                supabase_check.table("perfiles_inversion").update({
                    "historial_chat": _json.dumps(historial),
                    "actualizado_at": "now()",
                }).eq("usuario_id", user_id).execute()

                await _send(chat_id,
                    f"{respuesta}\n\n_Escribí *listo* cuando termines de explorar 👆_",
                    token)
            else:
                await _send(chat_id, "No pude responder eso ahora. Probá más tarde.", token, parse_mode="")
            return JSONResponse({"ok": True})

        if estado_perfil == "configurando_portafolio":
            import json as _json
            from lib.claude_invest import sugerir_portafolio

            perfil_data = perfil_check.data[0]
            capital = perfil_data.get("capital_disponible")
            if not capital:
                supabase_check.table("perfiles_inversion").update({"estado": "activo"}).eq("usuario_id", user_id).execute()
                await _send(chat_id, "✅ Perfil listo. Usá /portafolio para ver tus activos.", token)
                return JSONResponse({"ok": True})

            # Cargar activos seleccionados con precios
            ua_r = supabase_check.table("usuario_activos").select("activo_id").eq("usuario_id", user_id).execute()
            activos_ids = [row["activo_id"] for row in (ua_r.data or [])]
            activos_r = supabase_check.table("activos").select("id, codigo, nombre, tipo, moneda, precio_actual, precio_ars").in_("id", activos_ids).execute()
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

            # Detectar si pide sugerencia o pasa distribución propia
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
                # Pasar texto a Claude para que lo parsee como distribución
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
                return JSONResponse({"ok": True})

            # Guardar como pendiente y mostrar para confirmación
            supabase_check.table("perfiles_inversion").update({
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
            return JSONResponse({"ok": True})

    if text.startswith("/id"):
        if token:
            await _send(chat_id,
                f"🪪 Tu Telegram ID es: `{user_id}`\n"
                "Usalo en *Configurar* del dashboard para vincular tu cuenta.", token)
        return JSONResponse({"ok": True})

    if text.lower().startswith(("/ayuda", "/start", "/help")):
        if token:
            await _send(chat_id, AYUDA, token)
        return JSONResponse({"ok": True})

    if text.lower().startswith("/inversiones"):
        if token:
            await _handle_inversiones_cmd(user_id, chat_id, token)
        return JSONResponse({"ok": True})

    if text.lower().startswith("/portafolio"):
        if token:
            await _handle_portafolio_cmd(user_id, chat_id, token)
        return JSONResponse({"ok": True})

    if text.lower().startswith("/precios"):
        if token:
            await _handle_precios_cmd(chat_id, token)
        return JSONResponse({"ok": True})

    if text.lower().startswith("/iol_debug"):
        if token:
            from lib.market_data import fetch_iol_debug
            import json as _json
            simbolo = text.split()[-1].upper() if len(text.split()) > 1 else "AAPL"
            await _send(chat_id, f"🔍 Consultando IOL para *{simbolo}*...", token)
            result = await fetch_iol_debug(simbolo)
            # Mostrar resultado de forma legible (truncar si es muy largo)
            txt = _json.dumps(result, indent=2, ensure_ascii=False)
            if len(txt) > 3800:
                txt = txt[:3800] + "\n...(truncado)"
            await _send(chat_id, f"```\n{txt}\n```", token)
        return JSONResponse({"ok": True})

    if text.lower().startswith("/recurrentes"):
        if token:
            supabase = get_supabase()
            rows = supabase.table("recurrentes").select("*").eq("usuario_id", user_id).eq("activo", True).execute()
            if not rows.data:
                await _send(chat_id, "No tenés gastos recurrentes configurados.", token, parse_mode="")
            else:
                lines = ["🔁 *Tus gastos recurrentes:*\n"]
                for r in rows.data:
                    lines.append(f"• {r['descripcion']} — ${r['monto']:,.0f} — día {r['dia_del_mes']}")
                await _send(chat_id, "\n".join(lines), token)
        return JSONResponse({"ok": True})

    if text.lower().startswith("/editar"):
        if token:
            q = text[len("/editar"):].strip()
            mes_actual = date.today().strftime("%Y-%m")
            if q:
                kb, total = await _recent_movements_keyboard(user_id, "edit", q=q, mes=mes_actual)
                if kb:
                    await _send(chat_id,
                        f"✏️ *{total}* movimiento{'s' if total != 1 else ''} con \"{q}\" en {mes_actual}:",
                        token, reply_markup=kb)
                else:
                    await _send(chat_id, f"No encontré movimientos con \"{q}\" este mes.", token, parse_mode="")
            else:
                kb, _ = await _recent_movements_keyboard(user_id, "edit")
                if kb:
                    await _send(chat_id, "✏️ ¿Qué movimiento querés editar?", token, reply_markup=kb)
                else:
                    await _send(chat_id, "No encontré movimientos recientes.", token, parse_mode="")
        return JSONResponse({"ok": True})

    if text.lower().startswith("/borrar"):
        if token:
            q = text[len("/borrar"):].strip()
            mes_actual = date.today().strftime("%Y-%m")
            if q:
                kb, total = await _recent_movements_keyboard(user_id, "del", q=q, mes=mes_actual)
                if kb:
                    await _send(chat_id,
                        f"🗑️ *{total}* movimiento{'s' if total != 1 else ''} con \"{q}\" en {mes_actual}:",
                        token, reply_markup=kb)
                else:
                    await _send(chat_id, f"No encontré movimientos con \"{q}\" este mes.", token, parse_mode="")
            else:
                kb, _ = await _recent_movements_keyboard(user_id, "del")
                if kb:
                    await _send(chat_id, "🗑️ ¿Qué movimiento querés borrar?", token, reply_markup=kb)
                else:
                    await _send(chat_id, "No encontré movimientos recientes.", token, parse_mode="")
        return JSONResponse({"ok": True})

    if text.lower().startswith("/presupuesto"):
        if token:
            args = text[len("/presupuesto"):].strip()
            await _handle_presupuesto_cmd(user_id, chat_id, args, token)
        return JSONResponse({"ok": True})

    if token:
        await _process_text(text, user_id, chat_id, token)

    return JSONResponse({"ok": True})
