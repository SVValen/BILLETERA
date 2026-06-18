"""
Cron de Renta Fija — ejecutar diariamente en días hábiles (L-V 15:00 UTC).
1. Actualiza TNA/precios de instrumentos RF (cauciones, letras, bonos, ONs).
2. Para cada usuario con capital_usd configurado:
   - Evalúa carry trade ARS vs USD
   - Alerta vencimientos próximos
   - Sugiere rotación RF↔RV si hay señales fuertes de RV
   - Envía resumen solo si hay algo relevante (sin spam si todo neutral)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lib.supabase_client import get_supabase
from lib.market_data import fetch_caucion_tna, fetch_iol_rf, fetch_dolar_precio
from lib.rf_analysis import (
    analizar_carry_trade,
    evaluar_vencimientos,
    calcular_rendimiento_usd,
    calcular_allocation,
)
from lib.claude_invest import analizar_oportunidad_rf

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")


async def _send_telegram(chat_id: str, text: str, reply_markup: dict | None = None) -> bool:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        import json
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json=payload,
            )
            return r.json().get("ok", False)
    except Exception:
        return False


async def _actualizar_instrumentos(supabase) -> int:
    """Actualiza TNA y precios de instrumentos RF activos. Retorna cantidad actualizada."""
    instrumentos_r = supabase.table("instrumentos_rf").select("*").eq("activo", True).execute()
    instrumentos = instrumentos_r.data or []
    actualizados = 0

    for inst in instrumentos:
        upd = {}

        if inst["tipo"] == "caucion":
            tna = await fetch_caucion_tna(inst.get("plazo_dias") or 1)
            if tna:
                upd["tna_actual"] = tna

        elif inst.get("ticker_iol"):
            datos = await fetch_iol_rf(inst["ticker_iol"])
            if datos:
                upd["precio_actual"] = datos["precio"]
                if datos.get("tir"):
                    upd["tir"] = datos["tir"]
                if datos.get("paridad"):
                    upd["paridad"] = datos["paridad"]
                # Para letras: calcular TNA aproximada desde variacion/precio si disponible
                if inst["tipo"] == "letra" and datos.get("precio"):
                    upd["tna_actual"] = inst.get("tna_actual")  # mantener hasta tener cálculo preciso

        if upd:
            upd["ultimo_update"] = "now()"
            supabase.table("instrumentos_rf").update(upd).eq("id", inst["id"]).execute()
            actualizados += 1

    return actualizados


def _tna_caucion_referencia(instrumentos: list[dict]) -> float | None:
    """Retorna la TNA de caución 7D o 1D como referencia para el carry trade."""
    for cod in ("CAUCION_7D", "CAUCION_1D", "CAUCION_30D"):
        for inst in instrumentos:
            if inst["codigo"] == cod and inst.get("tna_actual"):
                return float(inst["tna_actual"])
    return None


async def _procesar_usuario(usuario_id: str, perfil: dict, supabase, dolar_mep: float, dolar_mep_30d: float | None, instrumentos: list[dict]) -> list[str]:
    """
    Analiza la situación RF del usuario y retorna lista de mensajes a enviar.
    """
    mensajes = []

    # Posiciones activas
    pos_r = supabase.table("posiciones_rf").select("*").eq("usuario_id", usuario_id).eq("estado", "activa").execute()
    posiciones = pos_r.data or []

    # 1. Alertas de vencimiento (siempre enviar)
    proximas = evaluar_vencimientos(posiciones, dias_alerta=3)
    for p in proximas:
        inst_nombre = next((i["nombre"] for i in instrumentos if i["id"] == p.get("instrumento_id")), "posición")
        dias = p["dias_restantes"]
        rdto = calcular_rendimiento_usd(p, dolar_mep)

        rdto_txt = (
            f"Rendimiento estimado: {rdto['rendimiento_ars_pct']:.1f}% ARS "
            f"/ {rdto['rendimiento_usd_pct']:+.1f}% USD"
        )
        if dias <= 0:
            dias_txt = "vence HOY"
        elif dias == 1:
            dias_txt = "vence MAÑANA"
        else:
            dias_txt = f"vence en {dias} días"

        mensajes.append(
            f"⏰ *Vencimiento próximo*\n\n"
            f"📄 {inst_nombre} — ${p['monto_ars']:,.0f} ARS\n"
            f"📅 {dias_txt.upper()}\n"
            f"📈 {rdto_txt}\n\n"
            f"¿Qué hacés? /liquidez para ver opciones."
        )

    # 2. Análisis carry trade (solo si hay TNA disponible)
    tna_ref = _tna_caucion_referencia(instrumentos)
    if not tna_ref:
        return mensajes  # Sin TNA, no podemos analizar

    carry = analizar_carry_trade(tna_ref, dolar_mep, dolar_mep_30d)
    allocation = calcular_allocation(posiciones, perfil.get("capital_usd") or 0, dolar_mep)
    asignacion_objetivo = perfil.get("asignacion_rf_pct") or 30

    # 3. Recomendación de carry
    if carry["accion"] == "entrar" and allocation["pct_rf"] < asignacion_objetivo - 5:
        # Carry favorable y usuario tiene menos RF de lo que quiere
        mensajes.append(
            f"💹 *Carry trade favorable*\n\n"
            f"{carry['razon']}\n\n"
            f"📊 Tenés {allocation['pct_rf']:.0f}% en RF (objetivo: {asignacion_objetivo}%). "
            f"Libre: ~${allocation['total_usd_libre']:,.0f} USD.\n\n"
            f"Considerá colocar en caución. Usá /liquidez para registrar."
        )

    elif carry["accion"] == "salir" and posiciones:
        # Carry negativo y tiene posiciones abiertas
        total_usd_rf = allocation["total_usd_rf"]
        mensajes.append(
            f"⚠️ *Carry trade desfavorable*\n\n"
            f"{carry['razon']}\n\n"
            f"Tenés ~${total_usd_rf:,.0f} USD equivalente en ARS. "
            f"Si vencen pronto, considerá no renovar y quedarte en USD.\n\n"
            f"Usá /liquidez para ver tus posiciones."
        )

    elif carry["accion"] == "neutral":
        # Zona gris: consultar Claude solo si hay algo relevante (tiene posiciones o capital libre)
        if allocation["total_usd_libre"] > 500 or posiciones:
            caucion_inst = next((i for i in instrumentos if i["tipo"] == "caucion" and i.get("tna_actual")), None)
            if caucion_inst:
                analisis = analizar_oportunidad_rf(caucion_inst, carry, perfil, posiciones)
                if analisis and analisis.get("confianza", 0) >= 6:
                    accion_txt = {"entrar": "ENTRAR", "no_entrar": "NO ENTRAR", "mantener": "MANTENER"}.get(
                        analisis.get("accion", ""), analisis.get("accion", "").upper()
                    )
                    mensajes.append(
                        f"🤖 *Análisis RF — {accion_txt}*\n\n"
                        f"{analisis['razon']}\n\n"
                        f"Confianza: {analisis['confianza']}/10 | Usá /liquidez para actuar."
                    )

    # 4. Cruce RV: si hay señal fuerte de RV, sugerir rotar
    if posiciones and allocation["pct_rf"] > asignacion_objetivo + 10:
        recs_rv_r = (
            supabase.table("recomendaciones")
            .select("activo_id, accion, confianza, activos(nombre)")
            .eq("usuario_id", usuario_id)
            .eq("estado", "pendiente")
            .gte("confianza", 7)
            .execute()
        )
        recs_rv = recs_rv_r.data or []
        if recs_rv:
            nombres = [r.get("activos", {}).get("nombre", "") for r in recs_rv[:2]]
            mensajes.append(
                f"🔄 *Oportunidad de rotación RF → RV*\n\n"
                f"Tenés {allocation['pct_rf']:.0f}% en RF (objetivo {asignacion_objetivo}%) "
                f"y hay señales fuertes en: {', '.join(n for n in nombres if n)}.\n\n"
                f"Considerá rescatar parte de la caución. Usá /liquidez y /portafolio."
            )

    return mensajes


@app.get("/api/cron_rf")
@app.get("/")
async def cron_rf(request: Request):
    cron_secret = os.getenv("CRON_SECRET", "")
    if not cron_secret or request.headers.get("authorization") != f"Bearer {cron_secret}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    supabase = get_supabase()

    # 1. Actualizar instrumentos RF
    instrumentos_actualizados = await _actualizar_instrumentos(supabase)

    # Recargar instrumentos con datos frescos
    inst_r = supabase.table("instrumentos_rf").select("*").eq("activo", True).execute()
    instrumentos = inst_r.data or []

    # 2. Obtener dólar MEP actual y hace 30 días
    dolar_mep_data = await fetch_dolar_precio("bolsa")
    dolar_mep = dolar_mep_data["precio"] if dolar_mep_data else None

    if not dolar_mep:
        return JSONResponse({
            "ok": True,
            "instrumentos_actualizados": instrumentos_actualizados,
            "alertas_enviadas": 0,
            "warning": "dólar MEP no disponible, saltando análisis de usuarios",
        })

    # Dólar MEP hace ~30 días: buscar en precios históricos del activo USDT
    dolar_mep_30d = None
    try:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        hist_r = (
            supabase.table("precios_historicos")
            .select("precio, timestamp")
            .eq("activo_id",
                supabase.table("activos").select("id").eq("codigo", "USDT").limit(1).execute().data[0]["id"]
            )
            .lte("timestamp", cutoff)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if hist_r.data:
            dolar_mep_30d = float(hist_r.data[0]["precio"])
    except Exception:
        pass  # Sin dato histórico: rf_analysis usa devaluación conservadora por defecto

    # 3. Procesar cada usuario con capital_usd configurado (un mensaje por usuario, no por portafolio)
    portafolios_r = (
        supabase.table("portafolios")
        .select("*")
        .eq("activo", True)
        .eq("estado_wizard", "activo")
        .not_.is_("capital_usd", "null")
        .execute()
    )
    portafolios = portafolios_r.data or []

    # Agrupar portafolios por usuario → usar el de mayor capital como referencia
    usuarios_portafolio: dict[str, dict] = {}
    for p in portafolios:
        uid = str(p["usuario_id"])
        if uid not in usuarios_portafolio or (p.get("capital_usd") or 0) > (usuarios_portafolio[uid].get("capital_usd") or 0):
            usuarios_portafolio[uid] = p

    alertas_enviadas = 0
    usuarios_procesados = 0
    for usuario_id, perfil in usuarios_portafolio.items():
        mensajes = await _procesar_usuario(usuario_id, perfil, supabase, dolar_mep, dolar_mep_30d, instrumentos)
        usuarios_procesados += 1
        for msg in mensajes:
            ok = await _send_telegram(usuario_id, msg)
            if ok:
                alertas_enviadas += 1

    return JSONResponse({
        "ok": True,
        "instrumentos_actualizados": instrumentos_actualizados,
        "usuarios_procesados": usuarios_procesados,
        "alertas_enviadas": alertas_enviadas,
        "dolar_mep": dolar_mep,
    })
