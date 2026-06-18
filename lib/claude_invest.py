"""
Integración con Claude API para recomendaciones de inversión.
Requiere: pip install anthropic
"""
import os
import json
import logging
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_client: Anthropic | None = None

_OBJ_DESC = {
    "ingresos_pasivos": "generar ingresos pasivos regulares",
    "crecimiento":      "hacer crecer el capital a largo plazo",
    "cobertura":        "protegerse de la inflación / preservar valor en dólares",
    "meta_especifica":  "ahorrar para una meta específica",
}

_PLAZO_DESC = {
    "corto":   "menos de 1 año",
    "mediano": "entre 1 y 3 años",
    "largo":   "más de 3 años",
}


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _parse_json(text: str) -> dict | None:
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def generar_recomendacion(
    perfil: dict,
    activo: dict,
    rsi: float | None,
    ema_20: float | None,
    ema_50: float | None,
    tendencia: str,
    interpretacion_rsi: str,
    winrate: float | None = None,
) -> dict | None:
    precio = activo.get("precio_actual") or activo.get("precio_ars")
    moneda = activo.get("moneda", "USD")

    perfil_desc = {
        "conservador": "prefiere preservar capital, acepta rendimientos bajos a cambio de menor riesgo",
        "moderado": "busca balance entre rendimiento y riesgo, acepta volatilidad media",
        "arriesgado": "prioriza máximo rendimiento, acepta alta volatilidad",
    }.get(perfil.get("perfil", "moderado"), "moderado")

    winrate_txt = f"{winrate:.0f}%" if winrate is not None else "sin historial aún"

    _obj_raw = perfil.get("objetivos") or perfil.get("objetivo") or ""
    if _obj_raw and _obj_raw.startswith("["):
        try:
            objetivos_txt = " y ".join(_OBJ_DESC.get(o, o) for o in json.loads(_obj_raw))
        except Exception:
            objetivos_txt = _obj_raw
    else:
        objetivos_txt = _OBJ_DESC.get(_obj_raw, _obj_raw) or "no especificado"

    prompt = f"""Sos un asistente financiero personal en Argentina. Analizá este activo y generá una recomendación concreta.

PERFIL DEL USUARIO:
- Tipo: {perfil.get("perfil", "moderado")} — {perfil_desc}
- Objetivos: {objetivos_txt}
- Capital USD: {perfil.get("capital_usd", "no especificado")}
- Winrate histórico: {winrate_txt}

ACTIVO:
- {activo.get("nombre")} ({activo.get("codigo")})
- Tipo: {activo.get("tipo")}
- Precio actual: {precio} {moneda}
- RSI (14): {rsi if rsi is not None else "no disponible"} → {interpretacion_rsi}
- EMA 20: {ema_20 if ema_20 else "no disponible"}
- EMA 50: {ema_50 if ema_50 else "no disponible"}
- Tendencia: {tendencia}

CONTEXTO: Argentina — inflación, tipo de cambio, cepo. Sin noticias en tiempo real.

Respondé SOLO en JSON válido, sin texto extra:
{{
  "accion": "comprar" | "vender" | "mantener",
  "razon": "<2-3 oraciones en español argentino>",
  "confianza": <1-10>,
  "porcentaje_capital": <5-30>,
  "riesgos": ["<riesgo 1>", "<riesgo 2>"]
}}"""

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json(response.content[0].text)
    except Exception as e:
        logger.error(f"Error en generar_recomendacion: {e}")
        return None


def sugerir_activos_para_perfil(
    objetivos: list[str],
    plazo: str,
    capital: float | None,
    descripcion: str,
    activos_disponibles: list[dict],
    moneda_preferida: str = "ARS",
) -> dict | None:
    """
    Retorna:
    {
      "perfil_riesgo": "conservador" | "moderado" | "arriesgado",
      "activos_sugeridos": [{"codigo": "BTC", "razon": "...", "explicacion": "..."}, ...],
      "otros_disponibles": ["ETH", "GOOGL"],
      "resumen": "texto breve"
    }
    """
    obj_txt = " y ".join(_OBJ_DESC.get(o, o) for o in objetivos) if objetivos else "no especificado"
    plazo_txt = _PLAZO_DESC.get(plazo, plazo or "no especificado")
    capital_txt = f"${capital:,.0f} ARS" if capital else "no especificado"

    _moneda_desc = {
        "ARS": "prefiere activos en pesos (acciones argentinas, activos locales)",
        "USD": "prefiere activos en dólares (CEDEARs de empresas USA, crypto)",
        "ambas": "abierto a activos en pesos y dólares, busca diversificar monedas",
    }
    moneda_txt = _moneda_desc.get(moneda_preferida, moneda_preferida)

    activos_txt = "\n".join(
        f"- {a['codigo']}: {a['nombre']} (tipo: {a['tipo']}, moneda: {a['moneda']})"
        for a in activos_disponibles
    )

    prompt = f"""Sos un asesor financiero personal en Argentina. Un usuario está configurando su perfil de inversión.

PERFIL:
- Objetivos: {obj_txt}
- Plazo: {plazo_txt}
- Capital: {capital_txt}
- Preferencia de moneda: {moneda_txt}
- En sus palabras: "{descripcion or 'no especificó'}"

ACTIVOS DISPONIBLES:
{activos_txt}

Tarea:
1. Derivá el perfil de riesgo (conservador/moderado/arriesgado).
2. Seleccioná 2-4 activos principales RESPETANDO la preferencia de moneda del usuario. Para cada uno:
   - "razon": por qué encaja (1 línea, informal)
   - "explicacion": qué es y cómo funciona en Argentina (2-3 oraciones simples)
3. Listá otros activos no seleccionados que podrían interesar (máx 3).
4. Resumen general (1-2 oraciones, español informal).

Reglas: CEDEARs = cobertura cambiaria (moneda USD). Crypto = volatilidad alta (moneda USD). Acciones AR = pesos.
Plazo corto → evitar crypto. Si prefiere ARS → priorizar acciones argentinas. Si prefiere USD → priorizar CEDEARs/crypto.
Múltiples objetivos → diversificar.

Respondé SOLO en JSON válido:
{{
  "perfil_riesgo": "moderado",
  "activos_sugeridos": [
    {{"codigo": "BTC", "razon": "...", "explicacion": "..."}}
  ],
  "otros_disponibles": ["ETH"],
  "resumen": "..."
}}"""

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json(response.content[0].text)
    except Exception as e:
        logger.error(f"Error en sugerir_activos_para_perfil: {e}")
        return None


def responder_pregunta_activos(
    pregunta: str,
    objetivos: list[str],
    plazo: str,
    activos_disponibles: list[dict],
    activos_seleccionados: list[str],
    historial: list[dict] | None = None,
) -> str | None:
    """
    Responde preguntas del usuario sobre activos durante el setup.
    historial: lista de {"u": pregunta, "b": respuesta} (últimas N interacciones)
    """
    obj_txt = " y ".join(_OBJ_DESC.get(o, o) for o in objetivos) if objetivos else "no especificado"
    plazo_txt = _PLAZO_DESC.get(plazo, plazo or "no especificado")

    activos_txt = "\n".join(
        f"- {a['codigo']}: {a['nombre']} (tipo: {a['tipo']}, moneda: {a['moneda']})"
        for a in activos_disponibles
    )
    seleccionados_txt = ", ".join(activos_seleccionados) if activos_seleccionados else "ninguno"

    hist_txt = ""
    if historial:
        lines = []
        for h in historial[-6:]:
            lines.append(f"Usuario: {h.get('u', '')}")
            lines.append(f"Asesor: {h.get('b', '')}")
        hist_txt = "\nCONVERSACIÓN PREVIA:\n" + "\n".join(lines) + "\n"

    prompt = f"""Sos un asesor financiero personal en Argentina, respondiendo en Telegram.
El usuario está eligiendo activos para monitorear.

PERFIL: objetivos={obj_txt}, plazo={plazo_txt}
Activos seleccionados: {seleccionados_txt}

ACTIVOS DISPONIBLES:
{activos_txt}
{hist_txt}
PREGUNTA ACTUAL: "{pregunta}"

Respondé claro, breve (máx 4 oraciones), español informal argentino.
Si pregunta por un activo: explicá qué es, cómo funciona, si encaja con su perfil.
Si dice que quiere confirmar/listo/ok: indicale que use el teclado de arriba.
Solo *negrita* cuando sea necesario."""

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Error en responder_pregunta_activos: {e}")
        return None


def sugerir_portafolio(
    objetivos: list[str],
    perfil_riesgo: str,
    plazo: str,
    capital_ars: float,
    activos_con_precios: list[dict],
    historial: list[dict] | None = None,
) -> list[dict] | None:
    """
    Sugiere cómo distribuir el capital entre los activos seleccionados.

    activos_con_precios: [{codigo, nombre, tipo, moneda, precio_actual, precio_ars}, ...]

    Retorna: [{"codigo": "BTC", "porcentaje": 40, "monto_ars": 200000, "razon": "..."}, ...]
    """
    obj_txt = " y ".join(_OBJ_DESC.get(o, o) for o in objetivos) if objetivos else "no especificado"
    plazo_txt = _PLAZO_DESC.get(plazo, plazo or "no especificado")

    activos_txt = "\n".join(
        f"- {a['codigo']}: {a['nombre']} | precio: {a.get('precio_actual') or a.get('precio_ars')} {a['moneda']}"
        for a in activos_con_precios
    )

    hist_txt = ""
    if historial:
        comentarios = [h.get("u", "") for h in historial[-4:] if h.get("u")]
        if comentarios:
            hist_txt = f"\nComentarios del usuario durante el setup: {' | '.join(comentarios)}\n"

    prompt = f"""Sos un asesor financiero en Argentina. Sugerí cómo distribuir el capital entre estos activos.

PERFIL:
- Objetivos: {obj_txt}
- Perfil de riesgo: {perfil_riesgo}
- Plazo: {plazo_txt}
- Capital total: ${capital_ars:,.0f} ARS
{hist_txt}
ACTIVOS A DISTRIBUIR:
{activos_txt}

Consideraciones:
- Los porcentajes deben sumar 100
- Adaptá la distribución al perfil de riesgo y objetivos
- Para activos en USD, el monto_ars es el equivalente al tipo de cambio actual (aproximado)

Respondé SOLO en JSON válido:
[
  {{"codigo": "BTC", "porcentaje": 40, "monto_ars": 200000, "razon": "mayor exposición crypto por perfil arriesgado"}},
  {{"codigo": "AAPL", "porcentaje": 60, "monto_ars": 300000, "razon": "base estable en CEDEAR"}}
]"""

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return result if isinstance(result, list) else None
    except Exception as e:
        logger.error(f"Error en sugerir_portafolio: {e}")
        return None


def analizar_oportunidad_rf(
    instrumento: dict,
    carry: dict,
    perfil: dict,
    posiciones_activas: list[dict],
) -> dict | None:
    """
    Consulta a Claude sobre una oportunidad de RF en la zona gris (carry 0-2%).
    Solo se llama cuando el análisis cuantitativo no es concluyente.

    instrumento: datos del instrumento (tipo, nombre, tna_actual, etc.)
    carry: resultado de analizar_carry_trade
    perfil: perfil de inversión del usuario
    posiciones_activas: posiciones RF actualmente abiertas

    Returns: {accion, razon, confianza} o None si falla
    """
    _perfil_desc = {
        "conservador": "prefiere preservar capital, baja tolerancia al riesgo cambiario",
        "moderado": "acepta algo de riesgo, busca rendimiento razonable",
        "arriesgado": "busca maximizar retorno, acepta volatilidad cambiaria",
    }.get(perfil.get("perfil", "moderado"), "moderado")

    capital_usd = perfil.get("capital_usd") or "no especificado"
    asignacion_rf_pct = perfil.get("asignacion_rf_pct") or 30
    total_ars_rf = sum(p.get("monto_ars", 0) for p in posiciones_activas)
    n_posiciones = len(posiciones_activas)

    prompt = f"""Sos un asesor financiero en Argentina. Evaluá si conviene entrar a este instrumento de renta fija.

CONTEXTO CARRY TRADE:
- TNA mensual del instrumento: {carry['tna_mensual']}%
- Devaluación mensual reciente del MEP: {carry['devaluacion_mensual']}%
- Carry neto: {carry['carry_mensual']}% (zona gris — no concluyente automáticamente)

INSTRUMENTO:
- Nombre: {instrumento.get('nombre')}
- Tipo: {instrumento.get('tipo')}
- TNA actual: {instrumento.get('tna_actual')}%
- Moneda: {instrumento.get('moneda')}
- Vencimiento: {instrumento.get('vencimiento') or 'sin fecha fija'}

PERFIL DEL USUARIO:
- Tipo: {perfil.get('perfil', 'moderado')} — {_perfil_desc}
- Capital total en USD: {capital_usd}
- Objetivo de allocación RF: {asignacion_rf_pct}%
- Posiciones RF activas: {n_posiciones} (ARS ${total_ars_rf:,.0f} en total)

Evaluá: ¿conviene entrar, mantener o no entrar?
Considerá: perfil de riesgo, carry en zona gris, contexto cambiario argentino, si ya tiene mucha exposición ARS.

Respondé SOLO en JSON válido:
{{"accion": "entrar" | "no_entrar" | "mantener", "razon": "<2-3 oraciones>", "confianza": <1-10>}}"""

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json(response.content[0].text)
    except Exception as e:
        logger.error(f"Error en analizar_oportunidad_rf: {e}")
        return None


def formatear_mensaje_telegram(activo: dict, rec: dict, recomendacion_id: int) -> tuple[str, dict]:
    emoji_accion = {"comprar": "🟢", "vender": "🔴", "mantener": "🟡"}.get(rec["accion"], "⚪")
    emoji_conf = "🔥" if rec["confianza"] >= 8 else "✅" if rec["confianza"] >= 6 else "⚠️"

    texto = (
        f"{emoji_accion} *SEÑAL: {rec['accion'].upper()}* — {activo['nombre']}\n\n"
        f"💬 {rec['razon']}\n\n"
        f"📊 RSI: {activo.get('rsi', '?')} | Tendencia: {activo.get('tendencia', '?')}\n"
        f"💰 Precio: {activo.get('precio_actual') or activo.get('precio_ars')} {activo.get('moneda', '')}\n"
        f"{emoji_conf} Confianza: {rec['confianza']}/10 | Capital sugerido: {rec['porcentaje_capital']}%\n\n"
        f"⚠️ *Riesgos:* {' • '.join(rec.get('riesgos', []))}"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Aceptar", "callback_data": f"inv_ok:{recomendacion_id}"},
            {"text": "❌ Rechazar", "callback_data": f"inv_no:{recomendacion_id}"},
        ]]
    }

    return texto, reply_markup
