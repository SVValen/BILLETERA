"""
Utilidades para tarjetas de crédito y cálculo de mes de resumen.
"""
from datetime import date
import calendar


def calcular_mes_resumen(fecha_compra: date, dia_cierre: int) -> str:
    """
    Dado el día de la compra y el día de cierre de la tarjeta,
    retorna el mes del resumen en que cae el gasto ('YYYY-MM') — el mes en
    que el usuario ve y paga ese resumen, no el mes en que cierra el ciclo.

    Regla:
      Si dia(fecha_compra) <= dia_cierre → mes_resumen = mes siguiente al de la compra
      Si dia(fecha_compra) > dia_cierre  → mes_resumen = dos meses después de la compra
    """
    mes_compra = fecha_compra.strftime("%Y-%m")
    if fecha_compra.day <= dia_cierre:
        return mes_siguiente(mes_compra)
    return mes_siguiente(mes_siguiente(mes_compra))


def mes_siguiente(mes: str) -> str:
    """'2026-06' → '2026-07'"""
    year, month = int(mes[:4]), int(mes[5:])
    if month == 12:
        return f"{year + 1}-01"
    return f"{year}-{month + 1:02d}"


def mes_label(mes: str) -> str:
    """'2026-07' → 'julio 2026'"""
    _MESES = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    year, month = int(mes[:4]), int(mes[5:])
    return f"{_MESES[month - 1]} {year}"


def mes_resumen_tarjeta(tarjeta_id: int, fecha_compra: date, dia_cierre: int | None) -> str:
    """Mes de resumen de una compra. Si la tarjeta tiene cierres reales cargados
    (tarjeta_cierres, para las de cierre variable), usa el primer cierre >= la fecha de compra;
    si no, la regla por día de cierre fijo."""
    try:
        from lib.supabase_client import get_supabase
        r = (
            get_supabase().table("tarjeta_cierres").select("mes_resumen, fecha_cierre")
            .eq("tarjeta_id", tarjeta_id).not_.is_("fecha_cierre", "null")
            .gte("fecha_cierre", fecha_compra.isoformat())
            .order("fecha_cierre").limit(1).execute()
        )
        if r.data:
            # solo vale si el cierre encontrado es del ciclo de esta compra (≤ ~35 días después)
            cierre = date.fromisoformat(r.data[0]["fecha_cierre"])
            if (cierre - fecha_compra).days <= 35:
                return r.data[0]["mes_resumen"]
    except Exception:
        pass
    if dia_cierre:
        return calcular_mes_resumen(fecha_compra, dia_cierre)
    return mes_siguiente(fecha_compra.strftime("%Y-%m"))


# ── Cierres variables (Santander, BBVA) ───────────────────────────────────────

def registrar_cierre(tarjeta_id: int, mes_resumen: str, fecha_cierre: date) -> int:
    """Guarda la fecha real de cierre del resumen que se paga en `mes_resumen` y recalcula
    el mes de resumen de las compras en 1 pago alrededor de esa fecha. Devuelve cuántas cambió."""
    from datetime import timedelta
    from lib.supabase_client import get_supabase
    sb = get_supabase()
    sb.table("tarjeta_cierres").upsert(
        {"tarjeta_id": tarjeta_id, "mes_resumen": mes_resumen, "fecha_cierre": fecha_cierre.isoformat()},
        on_conflict="tarjeta_id,mes_resumen",
    ).execute()
    tar = sb.table("tarjetas").select("dia_cierre").eq("id", tarjeta_id).limit(1).execute()
    dia = tar.data[0]["dia_cierre"] if tar.data else None
    movs = (
        sb.table("movimientos").select("id, fecha, fecha_compra, mes_resumen")
        .eq("tarjeta_id", tarjeta_id).is_("cuota_plan_id", "null").neq("es_pago_tarjeta", True)
        .neq("estado", "anulado")
        .gte("fecha", (fecha_cierre - timedelta(days=40)).isoformat())
        .lte("fecha", (fecha_cierre + timedelta(days=35)).isoformat())
        .execute()
    )
    cambiados = 0
    for m in (movs.data or []):
        ref = date.fromisoformat(m.get("fecha_compra") or m["fecha"])
        nuevo = mes_resumen_tarjeta(tarjeta_id, ref, dia)
        if nuevo != m.get("mes_resumen"):
            sb.table("movimientos").update({"mes_resumen": nuevo}).eq("id", m["id"]).execute()
            cambiados += 1
    return cambiados


def cierres_a_preguntar(hoy: date) -> list[dict]:
    """Tarjetas de cierre variable a las que todavía no se les cargó el cierre del resumen
    que se paga el mes que viene. Se pregunta desde el día 25, como mucho una vez cada 2 días."""
    from datetime import datetime, timedelta, timezone
    from lib.supabase_client import get_supabase
    if hoy.day < 25:
        return []
    sb = get_supabase()
    mes_pago = mes_siguiente(hoy.strftime("%Y-%m"))
    try:
        tarjetas = sb.table("tarjetas").select("id, nombre, usuario_id").eq("activa", True).eq("cierre_variable", True).execute()
    except Exception:
        return []  # migración schema_v2_cierres.sql todavía no aplicada
    out = []
    for t in (tarjetas.data or []):
        r = sb.table("tarjeta_cierres").select("fecha_cierre, preguntado_at").eq("tarjeta_id", t["id"]).eq("mes_resumen", mes_pago).limit(1).execute()
        fila = r.data[0] if r.data else None
        if fila and fila.get("fecha_cierre"):
            continue
        if fila and fila.get("preguntado_at"):
            ultima = datetime.fromisoformat(fila["preguntado_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - ultima < timedelta(days=2):
                continue
        out.append({**t, "mes_resumen": mes_pago})
    return out


def marcar_preguntado(tarjeta_id: int, mes_resumen: str) -> None:
    from datetime import datetime, timezone
    from lib.supabase_client import get_supabase
    get_supabase().table("tarjeta_cierres").upsert(
        {"tarjeta_id": tarjeta_id, "mes_resumen": mes_resumen, "preguntado_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="tarjeta_id,mes_resumen",
    ).execute()


def opciones_cierre(mes_resumen: str) -> list[date]:
    """Fechas posibles de cierre para el resumen que se paga en `mes_resumen`: del 27 del
    mes anterior al 3 de ese mes."""
    from datetime import timedelta
    y, m = int(mes_resumen[:4]), int(mes_resumen[5:])
    inicio_pago = date(y, m, 1)
    return [inicio_pago + timedelta(days=d) for d in range(-4, 3)]
