"""
Módulo de alquiler: contrato, canon vigente por mes y conceptos mensuales.

Cada mes el grupo "Alquiler" tiene movimientos con `concepto`:
  alquiler | expensas | agua | gas | luz | descuento (monto negativo)
Se crean como pendientes (`pagado = FALSE`); los variables arrastran el último
valor conocido con `estimado = TRUE` hasta que llega la liquidación real.
"""
from __future__ import annotations

from datetime import date

from lib.supabase_client import get_supabase

CONCEPTOS_FIJOS = ("alquiler", "expensas", "agua", "gas")
ETIQUETAS = {
    "alquiler": "Alquiler",
    "expensas": "Expensas",
    "agua": "Agua",
    "gas": "Gas",
    "luz": "Luz",
    "descuento": "Descuento",
}
EMOJI = {"alquiler": "🏠", "expensas": "🏢", "agua": "💧", "gas": "🔥", "luz": "💡", "descuento": "🔧"}
CAT_DEPARTAMENTO = 10
CAT_SERVICIOS = 4


def mes_actual() -> str:
    return date.today().strftime("%Y-%m")


def sumar_meses(mes: str, n: int) -> str:
    y, m = map(int, mes.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def get_contrato(usuario_id: str) -> dict | None:
    r = (
        get_supabase().table("alquiler_contrato")
        .select("*").eq("usuario_id", str(usuario_id)).eq("activo", True)
        .order("id", desc=True).limit(1).execute()
    )
    return r.data[0] if r.data else None


def canon_para_mes(contrato: dict, mes: str) -> dict | None:
    """Registro de alquiler_canon vigente para `mes` (el último con desde_mes <= mes)."""
    r = (
        get_supabase().table("alquiler_canon")
        .select("*").eq("contrato_id", contrato["id"]).lte("desde_mes", mes)
        .order("desde_mes", desc=True).limit(1).execute()
    )
    return r.data[0] if r.data else None


def items_mes(usuario_id: str, mes: str) -> list[dict]:
    r = (
        get_supabase().table("movimientos")
        .select("id, descripcion, monto, concepto, pagado, estimado, mes_resumen")
        .eq("usuario_id", str(usuario_id)).eq("grupo", "Alquiler").eq("mes_resumen", mes)
        .neq("estado", "anulado").order("monto", desc=True).execute()
    )
    return r.data or []


def _ultimo_valor(usuario_id: str, concepto: str, antes_de: str) -> float | None:
    r = (
        get_supabase().table("movimientos")
        .select("monto").eq("usuario_id", str(usuario_id)).eq("grupo", "Alquiler")
        .eq("concepto", concepto).lt("mes_resumen", antes_de).neq("estado", "anulado")
        .order("mes_resumen", desc=True).limit(1).execute()
    )
    return float(r.data[0]["monto"]) if r.data else None


def asegurar_mes(usuario_id: str, mes: str) -> list[dict]:
    """Crea los conceptos fijos del mes que falten (pendientes). Idempotente."""
    contrato = get_contrato(usuario_id)
    if not contrato or mes < contrato["inicio"][:7]:
        return []
    existentes = {i["concepto"] for i in items_mes(usuario_id, mes)}
    nuevos = []
    for concepto in CONCEPTOS_FIJOS:
        if concepto in existentes:
            continue
        if concepto == "alquiler":
            canon = canon_para_mes(contrato, mes)
            if not canon:
                continue
            monto, estimado = float(canon["monto"]), bool(canon["estimado"])
        else:
            monto = _ultimo_valor(usuario_id, concepto, mes)
            if not monto:
                continue
            estimado = True
        nuevos.append({
            "usuario_id": str(usuario_id),
            "fecha": f"{mes}-01",
            "descripcion": ETIQUETAS[concepto],
            "monto": round(monto, 2),
            "categoria_id": CAT_DEPARTAMENTO,
            "tipo": "gasto",
            "origen": "alquiler",
            "estado": "confirmado",
            "mes_resumen": mes,
            "grupo": "Alquiler",
            "concepto": concepto,
            "pagado": False,
            "estimado": estimado,
        })
    if nuevos:
        get_supabase().table("movimientos").insert(nuevos).execute()
    return nuevos


def marcar_pagado(usuario_id: str, mov_id: int | None = None, mes: str | None = None) -> int:
    """Marca un concepto (por id) o todo el mes como pagado. Devuelve cuántos cambió."""
    q = (
        get_supabase().table("movimientos")
        .update({"pagado": True})
        .eq("usuario_id", str(usuario_id)).eq("grupo", "Alquiler").eq("pagado", False)
    )
    if mov_id is not None:
        q = q.eq("id", mov_id)
    elif mes:
        q = q.eq("mes_resumen", mes)
    else:
        return 0
    r = q.execute()
    return len(r.data or [])


def agregar_descuento(usuario_id: str, mes: str, monto: float, detalle: str) -> dict:
    row = {
        "usuario_id": str(usuario_id),
        "fecha": f"{mes}-01",
        "descripcion": f"Descuento: {detalle.strip().capitalize()}",
        "monto": -abs(round(monto, 2)),
        "categoria_id": CAT_DEPARTAMENTO,
        "tipo": "gasto",
        "origen": "alquiler",
        "estado": "confirmado",
        "mes_resumen": mes,
        "grupo": "Alquiler",
        "concepto": "descuento",
        "pagado": True,
        "estimado": False,
    }
    r = get_supabase().table("movimientos").insert(row).execute()
    return r.data[0] if r.data else row


def resumen_mes(usuario_id: str, mes: str) -> dict:
    items = items_mes(usuario_id, mes)
    total = sum(float(i["monto"]) for i in items)
    pendiente = sum(float(i["monto"]) for i in items if not i["pagado"])
    return {
        "mes": mes,
        "items": items,
        "total": round(total, 2),
        "pendiente": round(pendiente, 2),
        "hay_estimados": any(i["estimado"] for i in items),
    }
