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


async def _answer_callback(callback_id: str, token: str) -> None:
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
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


async def _handle_inversiones_cmd(user_id: str, chat_id: int, token: str) -> None:
    supabase = get_supabase()
    perfil_r = supabase.table("perfiles_inversion").select("*").eq("usuario_id", user_id).limit(1).execute()
    p = perfil_r.data[0] if perfil_r.data else None

    if not p:
        await _send(chat_id,
            "📈 *Módulo de Inversiones*\n\n"
            "Elegí tu perfil de riesgo para empezar:",
            token,
            reply_markup={
                "inline_keyboard": [[
                    {"text": "🛡️ Conservador", "callback_data": "inv_perfil:conservador"},
                    {"text": "⚖️ Moderado",    "callback_data": "inv_perfil:moderado"},
                    {"text": "🚀 Arriesgado",  "callback_data": "inv_perfil:arriesgado"},
                ]]
            })
        return

    # Perfil existente → mostrar resumen
    perfil_emoji = {"conservador": "🛡️", "moderado": "⚖️", "arriesgado": "🚀"}.get(p["perfil"], "📈")
    lines = [f"📈 *Inversiones* — {perfil_emoji} {p['perfil'].capitalize()}"]
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

        # Elegir / cambiar perfil de inversión
        elif parts[0] == "inv_perfil" and len(parts) == 2:
            tipo = parts[1]
            if tipo in ("conservador", "moderado", "arriesgado"):
                supabase.table("perfiles_inversion").upsert({
                    "usuario_id": callback_user_id,
                    "perfil": tipo,
                    "estado": "configurando_capital",
                    "actualizado_at": "now()",
                }, on_conflict="usuario_id").execute()
                perfil_emoji = {"conservador": "🛡️", "moderado": "⚖️", "arriesgado": "🚀"}[tipo]
                if token:
                    await _answer_callback(callback_id, token)
                    await _edit_message(chat_id, message_id,
                        f"✅ Perfil *{perfil_emoji} {tipo}* guardado.\n\n"
                        "💰 ¿Cuánto capital tenés disponible para invertir? (en ARS)\n"
                        "_Respondé con un número, ej: 500000_\n"
                        "_O escribí /skip para omitir_", token)

        elif parts[0] == "inv_cambiar_perfil":
            if token:
                await _answer_callback(callback_id, token)
                await _edit_message(chat_id, message_id,
                    "📈 Elegí tu nuevo perfil de riesgo:", token,
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": "🛡️ Conservador", "callback_data": "inv_perfil:conservador"},
                            {"text": "⚖️ Moderado",    "callback_data": "inv_perfil:moderado"},
                            {"text": "🚀 Arriesgado",  "callback_data": "inv_perfil:arriesgado"},
                        ]]
                    })

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
        await _process_text(transcribed, user_id, chat_id, token)
        return JSONResponse({"ok": True})

    text = message.get("text", "").strip()
    if not text:
        return JSONResponse({"ok": True})

    # ── Capital de inversión (respuesta al setup de perfil) ───────────────────
    if token and not text.startswith("/"):
        supabase_check = get_supabase()
        perfil_check = supabase_check.table("perfiles_inversion").select("estado").eq("usuario_id", user_id).limit(1).execute()
        if perfil_check.data and perfil_check.data[0].get("estado") == "configurando_capital":
            if text.lower() == "/skip" or text.lower() == "skip":
                supabase_check.table("perfiles_inversion").update({"estado": "activo"}).eq("usuario_id", user_id).execute()
                await _send(chat_id, "✅ Perfil configurado. Vas a recibir recomendaciones cuando haya señales.", token)
            else:
                # Intentar parsear como número
                clean = text.replace(".", "").replace(",", "").replace("$", "").strip()
                try:
                    capital = float(clean)
                    supabase_check.table("perfiles_inversion").update({
                        "capital_disponible": capital,
                        "estado": "activo",
                        "actualizado_at": "now()",
                    }).eq("usuario_id", user_id).execute()
                    await _send(chat_id,
                        f"✅ *Perfil completo*\n"
                        f"💰 Capital: ${capital:,.0f}\n\n"
                        "El sistema va a analizar activos cada 30 minutos y te va a avisar cuando haya señales.\n"
                        "Usá /inversiones para ver el estado en cualquier momento.", token)
                except ValueError:
                    await _send(chat_id,
                        "No entendí el monto. Enviá solo el número (ej: `500000`) o escribí `skip` para omitirlo.", token)
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
