"""
Registro de pagos compartido entre el bot y el dashboard:
  - pago del resumen de una tarjeta (monto calculado vs. monto realmente pagado)
  - pago de la cuota de un préstamo
"""
from __future__ import annotations

from datetime import date

from lib.supabase_client import get_supabase

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _mes_label(mes: str) -> str:
    y, m = mes.split("-")
    return f"{_MESES[int(m) - 1]} {y}"


def nombre_tarjeta(tarjeta_id: int) -> str:
    r = get_supabase().table("tarjetas").select("nombre").eq("id", tarjeta_id).limit(1).execute()
    return r.data[0]["nombre"] if r.data else "Tarjeta"


def total_resumen_tarjeta(usuario_id: str, tarjeta_id: int, mes: str) -> float:
    """Lo que corresponde pagar del resumen: compras y cuotas con ese mes_resumen (sin el pago en sí)."""
    rows = (
        get_supabase().table("movimientos").select("monto")
        .eq("usuario_id", str(usuario_id)).eq("tarjeta_id", tarjeta_id).eq("mes_resumen", mes)
        .eq("tipo", "gasto").neq("estado", "anulado").neq("es_pago_tarjeta", True)
        .execute()
    )
    return round(sum(float(r["monto"]) for r in (rows.data or [])), 2)


def registrar_pago_tarjeta(usuario_id: str, tarjeta_id: int, mes: str,
                           monto_calculado: float, monto_pagado: float) -> int | None:
    """Inserta (o reemplaza) el movimiento de pago del resumen y actualiza tarjeta_pagos.
    Devuelve el id del movimiento de pago."""
    supabase = get_supabase()
    nombre = nombre_tarjeta(tarjeta_id)

    previo = (
        supabase.table("tarjeta_pagos").select("movimiento_id")
        .eq("usuario_id", int(usuario_id)).eq("tarjeta_id", tarjeta_id).eq("mes_resumen", mes)
        .limit(1).execute()
    )
    if previo.data and previo.data[0].get("movimiento_id"):
        supabase.table("movimientos").update({"estado": "anulado"}).eq("id", previo.data[0]["movimiento_id"]).execute()

    cat_r = supabase.table("categorias").select("id").eq("nombre", "Pago Tarjeta").limit(1).execute()
    cat_id = cat_r.data[0]["id"] if cat_r.data else None
    hoy = date.today().isoformat()

    mov_r = supabase.table("movimientos").insert({
        "usuario_id": str(usuario_id),
        "fecha": hoy,
        "descripcion": f"Pago tarjeta {nombre} — resumen {_mes_label(mes)}",
        "monto": monto_pagado,
        "categoria_id": cat_id,
        "tipo": "gasto",
        "origen": "pago",
        "estado": "confirmado",
        "tarjeta_id": tarjeta_id,
        "es_pago_tarjeta": True,
    }).execute()
    movimiento_id = mov_r.data[0]["id"] if mov_r.data else None

    supabase.table("tarjeta_pagos").upsert({
        "usuario_id": int(usuario_id),
        "tarjeta_id": tarjeta_id,
        "mes_resumen": mes,
        "monto_calculado": monto_calculado,
        "monto_pagado": monto_pagado,
        "fecha_pago": hoy,
        "movimiento_id": movimiento_id,
    }, on_conflict="usuario_id,tarjeta_id,mes_resumen").execute()
    return movimiento_id


def pagar_cuota_prestamo(usuario_id: str, cuota_id: int) -> dict | None:
    """Marca pagada una cuota de préstamo. Si la cuota ya tiene su movimiento cargado
    (v2 genera los movimientos por adelantado) no crea otro. Devuelve la cuota actualizada."""
    supabase = get_supabase()
    cuota_r = (
        supabase.table("prestamo_cuotas").select("*")
        .eq("id", cuota_id).eq("usuario_id", int(usuario_id)).limit(1).execute()
    )
    if not cuota_r.data:
        return None
    cuota = cuota_r.data[0]
    monto = cuota.get("monto_ordinario") or cuota["capital"]
    hoy = date.today().isoformat()
    mov_id = cuota.get("movimiento_id")

    if mov_id:
        mov = supabase.table("movimientos").select("monto").eq("id", mov_id).limit(1).execute()
        if mov.data:
            monto = float(mov.data[0]["monto"])
        supabase.table("movimientos").update({"pagado": True}).eq("id", mov_id).execute()
    else:
        prest = supabase.table("prestamos").select("nombre, total_cuotas").eq("id", cuota["prestamo_id"]).limit(1).execute()
        nombre = prest.data[0]["nombre"] if prest.data else "Préstamo"
        total = prest.data[0]["total_cuotas"] if prest.data else None
        cat = supabase.table("categorias").select("id").eq("nombre", "Auto").limit(1).execute()
        mes = cuota.get("mes_previsto") or hoy[:7]
        ins = supabase.table("movimientos").insert({
            "usuario_id": str(usuario_id),
            "fecha": hoy,
            "descripcion": f"{nombre} — cuota {cuota['numero_cuota']}",
            "monto": monto,
            "categoria_id": cat.data[0]["id"] if cat.data else 7,
            "tipo": "gasto",
            "origen": "pago",
            "estado": "confirmado",
            "mes_resumen": mes,
            "grupo": "Préstamo",
            "prestamo_id": cuota["prestamo_id"],
            "cuota_nro": cuota["numero_cuota"],
            "cuota_total": total,
        }).execute()
        mov_id = ins.data[0]["id"] if ins.data else None

    upd = supabase.table("prestamo_cuotas").update({
        "pagado": True,
        "tipo_pago": "ordinaria",
        "monto_pagado": monto,
        "fecha_pago": hoy,
        "movimiento_id": mov_id,
    }).eq("id", cuota_id).execute()
    return upd.data[0] if upd.data else cuota
