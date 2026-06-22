from .constants import CAT_BUTTONS
from lib.supabase_client import get_supabase
from lib.date_utils import mes_rango


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


def _cuotas_pago_keyboard(mov_id: int, tarjeta_id: int) -> dict:
    p = f"tar_cuotas:{mov_id}:{tarjeta_id}"
    return {"inline_keyboard": [
        [{"text": "1 pago (sin cuotas)", "callback_data": f"{p}:1"}],
        [
            {"text": "3 cuotas", "callback_data": f"{p}:3"},
            {"text": "6 cuotas", "callback_data": f"{p}:6"},
            {"text": "12 cuotas", "callback_data": f"{p}:12"},
        ],
    ]}


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
