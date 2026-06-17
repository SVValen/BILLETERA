from datetime import date
from lib.supabase_client import get_supabase
from lib.date_utils import mes_rango
from ..tg import _send
from ..constants import CAT_NAME_MAP


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


async def _handle_presupuesto_cmd(user_id: str, chat_id: int, args: str, token: str) -> None:
    mes = date.today().strftime("%Y-%m")
    supabase = get_supabase()

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
