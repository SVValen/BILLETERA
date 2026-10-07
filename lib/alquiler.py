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


def _conceptos_nuevos(usuario_id: str, mes: str, existentes: set[str]) -> list[dict]:
    contrato = get_contrato(usuario_id)
    if not contrato or mes < contrato["inicio"][:7]:
        return []
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
    return nuevos


def asegurar_mes(usuario_id: str, mes: str) -> list[dict]:
    """Crea los conceptos fijos del mes que falten (pendientes). Idempotente."""
    existentes = {i["concepto"] for i in items_mes(usuario_id, mes)}
    nuevos = _conceptos_nuevos(usuario_id, mes, existentes)
    if nuevos:
        get_supabase().table("movimientos").insert(nuevos).execute()
    return nuevos


def proyectar_mes(usuario_id: str, mes: str) -> list[dict]:
    """Lo que se va a pagar de alquiler en un mes futuro que todavía no tiene filas cargadas
    (no inserta nada): canon vigente + último valor de expensas, agua y gas, todo estimado."""
    filas = _conceptos_nuevos(usuario_id, mes, set())
    for f in filas:
        f["estimado"] = True
    return filas


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


def aplicar_liquidacion(usuario_id: str, liq: dict) -> dict:
    """Carga los importes reales de una liquidación de expensas en el mes en que se pagan
    (la liquidación de septiembre se paga en octubre). Reemplaza los estimados de
    expensas, agua y gas de ese mes; si no existen, los crea como pendientes."""
    mes = liq["mes_pago"]
    asegurar_mes(usuario_id, mes)
    valores = {
        "expensas": liq["expensas_sin_servicios"],
        "agua": liq["agua"],
        "gas": liq["gas"],
    }
    existentes = {i["concepto"]: i for i in items_mes(usuario_id, mes)}
    sb = get_supabase()
    cambios = {}
    for concepto, monto in valores.items():
        if not monto:
            continue
        if concepto in existentes:
            sb.table("movimientos").update({
                "monto": round(monto, 2), "estimado": False, "origen": f"expensas:{liq['liquidacion']}",
            }).eq("id", existentes[concepto]["id"]).execute()
        else:
            sb.table("movimientos").insert({
                "usuario_id": str(usuario_id), "fecha": f"{mes}-01", "descripcion": ETIQUETAS[concepto],
                "monto": round(monto, 2), "categoria_id": CAT_DEPARTAMENTO, "tipo": "gasto",
                "origen": f"expensas:{liq['liquidacion']}", "estado": "confirmado", "mes_resumen": mes,
                "grupo": "Alquiler", "concepto": concepto, "pagado": False, "estimado": False,
            }).execute()
        cambios[concepto] = round(monto, 2)
    # Los meses siguientes que todavía tengan estimados arrastran el valor nuevo
    for concepto, monto in cambios.items():
        (
            sb.table("movimientos").update({"monto": monto})
            .eq("usuario_id", str(usuario_id)).eq("grupo", "Alquiler").eq("concepto", concepto)
            .eq("estimado", True).gt("mes_resumen", mes).execute()
        )
    return {"mes": mes, **cambios}


# ── Ajuste del canon por IPC ──────────────────────────────────────────────────
# Serie INDEC "IPC Nivel general nacional, base dic-2016" (datos.gob.ar).
IPC_SERIE = "148.3_INIVELNAL_DICI_M_26"
IPC_URL = "https://apis.datos.gob.ar/series/api/series/"


def meses_de_ajuste(contrato: dict, hasta: str) -> list[str]:
    out, mes = [], contrato["primer_mes_ajuste"]
    while mes <= hasta:
        out.append(mes)
        mes = sumar_meses(mes, int(contrato.get("meses_ajuste") or 4))
    return out


def proximo_ajuste(contrato: dict, desde: str) -> str:
    mes = contrato["primer_mes_ajuste"]
    while mes < desde:
        mes = sumar_meses(mes, int(contrato.get("meses_ajuste") or 4))
    return mes


async def ipc_mensual(desde: str) -> dict[str, float]:
    """{'YYYY-MM': índice} desde el mes dado."""
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(IPC_URL, params={
            "ids": IPC_SERIE, "start_date": f"{desde}-01", "format": "json", "limit": 100,
        })
        r.raise_for_status()
        return {fila[0][:7]: float(fila[1]) for fila in r.json().get("data", []) if fila[1] is not None}


def _canon_base(contrato: dict, mes_ajuste: str) -> dict | None:
    r = (
        get_supabase().table("alquiler_canon").select("*")
        .eq("contrato_id", contrato["id"]).lt("desde_mes", mes_ajuste).eq("estimado", False)
        .order("desde_mes", desc=True).limit(1).execute()
    )
    return r.data[0] if r.data else None


async def actualizar_ajuste_ipc(usuario_id: str) -> dict | None:
    """Si el próximo ajuste (o el del mes en curso) todavía está estimado y ya están publicados
    los IPC necesarios, calcula el canon nuevo, lo guarda y actualiza los alquileres de ese
    período. Criterio: variación del IPC de los 4 meses anteriores ya publicados
    (para un ajuste en diciembre: julio a octubre = IPC oct / IPC jun).
    Devuelve el detalle del ajuste si lo aplicó."""
    contrato = get_contrato(usuario_id)
    if not contrato:
        return None
    hoy = mes_actual()
    mes_aj = proximo_ajuste(contrato, hoy)
    paso = int(contrato.get("meses_ajuste") or 4)
    sb = get_supabase()

    actual = (
        sb.table("alquiler_canon").select("*").eq("contrato_id", contrato["id"])
        .eq("desde_mes", mes_aj).limit(1).execute()
    )
    if actual.data and not actual.data[0]["estimado"]:
        return None  # ya calculado
    base = _canon_base(contrato, mes_aj)
    if not base:
        return None

    m_fin, m_ini = sumar_meses(mes_aj, -2), sumar_meses(mes_aj, -2 - paso)
    try:
        ipc = await ipc_mensual(m_ini)
    except Exception:
        return None
    if m_fin not in ipc or m_ini not in ipc:
        return None  # todavía no se publicó el IPC necesario

    variacion = ipc[m_fin] / ipc[m_ini] - 1
    nuevo = round(float(base["monto"]) * (1 + variacion), 2)
    detalle = f"IPC {m_ini}→{m_fin}: {variacion * 100:+.2f}% sobre ${float(base['monto']):,.0f}"
    sb.table("alquiler_canon").upsert({
        "contrato_id": contrato["id"], "desde_mes": mes_aj, "monto": nuevo,
        "estimado": False, "detalle": detalle,
    }, on_conflict="contrato_id,desde_mes").execute()

    # Alquileres del período [mes_aj, próximo ajuste)
    fin = sumar_meses(mes_aj, paso)
    (
        sb.table("movimientos").update({"monto": nuevo, "estimado": False})
        .eq("usuario_id", str(usuario_id)).eq("grupo", "Alquiler").eq("concepto", "alquiler")
        .gte("mes_resumen", mes_aj).lt("mes_resumen", fin).execute()
    )
    # El ajuste siguiente queda estimado con este monto hasta que se pueda calcular
    sb.table("alquiler_canon").upsert({
        "contrato_id": contrato["id"], "desde_mes": fin, "monto": nuevo, "estimado": True,
        "detalle": "Estimado hasta tener el IPC",
    }, on_conflict="contrato_id,desde_mes", ignore_duplicates=True).execute()
    return {"mes": mes_aj, "monto_anterior": float(base["monto"]), "monto": nuevo,
            "variacion": variacion, "detalle": detalle}
