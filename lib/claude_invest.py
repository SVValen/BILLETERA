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
    """
    Llama a Claude para generar una recomendación de compra/venta/mantener.

    Retorna:
    {
      "accion": "comprar" | "vender" | "mantener",
      "razon": str,
      "confianza": int (1-10),
      "porcentaje_capital": int,
      "riesgos": list[str]
    }
    """
    precio = activo.get("precio_actual") or activo.get("precio_ars")
    moneda = activo.get("moneda", "USD")

    perfil_desc = {
        "conservador": "prefiere preservar capital, acepta rendimientos bajos a cambio de menor riesgo",
        "moderado": "busca balance entre rendimiento y riesgo, acepta volatilidad media",
        "arriesgado": "prioriza máximo rendimiento, acepta alta volatilidad",
    }.get(perfil.get("perfil", "moderado"), "moderado")

    winrate_txt = f"{winrate:.0f}%" if winrate is not None else "sin historial aún"

    # Objetivos guardados como JSON array o string legacy
    objetivos_raw = perfil.get("objetivos") or perfil.get("objetivo") or ""
    if objetivos_raw and objetivos_raw.startswith("["):
        try:
            obj_list = json.loads(objetivos_raw)
            objetivos_txt = " y ".join(_OBJ_DESC.get(o, o) for o in obj_list)
        except Exception:
            objetivos_txt = objetivos_raw
    else:
        objetivos_txt = _OBJ_DESC.get(objetivos_raw, objetivos_raw) or "no especificado"

    prompt = f"""Sos un asistente financiero personal en Argentina. Analizá este activo y generá una recomendación concreta.

PERFIL DEL USUARIO:
- Tipo: {perfil.get("perfil", "moderado")} — {perfil_desc}
- Objetivos: {objetivos_txt}
- Capital disponible: {perfil.get("capital_disponible", "no especificado")}
- Winrate histórico: {winrate_txt}

ACTIVO:
- {activo.get("nombre")} ({activo.get("codigo")})
- Tipo: {activo.get("tipo")}
- Precio actual: {precio} {moneda}
- RSI (14): {rsi if rsi is not None else "no disponible"} → {interpretacion_rsi}
- EMA 20: {ema_20 if ema_20 else "no disponible"}
- EMA 50: {ema_50 if ema_50 else "no disponible"}
- Tendencia: {tendencia}

CONTEXTO:
- Activo argentino/regional — considerá el contexto macro de Argentina (inflación, tipo de cambio, cepo)
- No tenemos noticias en tiempo real, basate solo en los indicadores

Generá una recomendación ESPECÍFICA. Respondé SOLO en JSON válido, sin texto extra:
{{
  "accion": "comprar" | "vender" | "mantener",
  "razon": "<explicación de 2-3 oraciones en español argentino>",
  "confianza": <número del 1 al 10>,
  "porcentaje_capital": <porcentaje del capital disponible a invertir, entre 5 y 30>,
  "riesgos": ["<riesgo 1>", "<riesgo 2>"]
}}"""

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Claude devolvió JSON inválido: {e}")
        return None
    except Exception as e:
        logger.error(f"Error llamando Claude: {e}")
        return None


def sugerir_activos_para_perfil(
    objetivos: list[str],
    plazo: str,
    capital: float | None,
    descripcion: str,
    activos_disponibles: list[dict],
) -> dict | None:
    """
    Analiza el perfil del usuario y sugiere qué activos monitorear + perfil de riesgo.

    Retorna:
    {
      "perfil_riesgo": "conservador" | "moderado" | "arriesgado",
      "activos_sugeridos": [
        {"codigo": "BTC", "razon": "...", "explicacion": "..."},
        ...
      ],
      "otros_disponibles": ["ETH", "GOOGL"],
      "resumen": "texto breve para el usuario"
    }
    """
    obj_txt = " y ".join(_OBJ_DESC.get(o, o) for o in objetivos) if objetivos else "no especificado"
    plazo_txt = _PLAZO_DESC.get(plazo, plazo or "no especificado")
    capital_txt = f"${capital:,.0f} ARS" if capital else "no especificado"

    activos_txt = "\n".join(
        f"- {a['codigo']}: {a['nombre']} (tipo: {a['tipo']}, moneda: {a['moneda']})"
        for a in activos_disponibles
    )

    prompt = f"""Sos un asesor financiero personal en Argentina. Un usuario está configurando su perfil de inversión.

PERFIL DEL USUARIO:
- Objetivos: {obj_txt}
- Plazo: {plazo_txt}
- Capital disponible: {capital_txt}
- En sus propias palabras: "{descripcion or 'no especificó'}"

ACTIVOS DISPONIBLES:
{activos_txt}

Tu tarea:
1. Derivar el perfil de riesgo (conservador/moderado/arriesgado).
2. Seleccionar 2-4 activos principales. Para cada uno escribí:
   - "razon": por qué encaja con sus objetivos (1 línea, informal)
   - "explicacion": qué es y cómo funciona en el contexto argentino (2-3 oraciones simples, sin jerga)
3. Listar otros activos disponibles no seleccionados que podrían interesarle (máx 3).
4. Resumen general (1-2 oraciones, español informal).

Reglas para Argentina:
- CEDEARs = acciones extranjeras que cotizan en pesos, buena cobertura cambiaria
- Acciones AR = exposición local, más volátiles
- BTC/ETH = cripto, alta volatilidad, útil para largo plazo y dolarización
- Plazo corto → evitar cripto, preferir cobertura/CEDEARs
- Múltiples objetivos → diversificar tipos de activo

Respondé SOLO en JSON válido, sin texto extra:
{{
  "perfil_riesgo": "moderado",
  "activos_sugeridos": [
    {{"codigo": "BTC", "razon": "...", "explicacion": "..."}},
    {{"codigo": "AAPL", "razon": "...", "explicacion": "..."}}
  ],
  "otros_disponibles": ["ETH", "GOOGL"],
  "resumen": "..."
}}"""

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Claude devolvió JSON inválido en sugerencia de activos: {e}")
        return None
    except Exception as e:
        logger.error(f"Error llamando Claude para sugerencia de activos: {e}")
        return None


def responder_pregunta_activos(
    pregunta: str,
    objetivos: list[str],
    plazo: str,
    activos_disponibles: list[dict],
    activos_seleccionados: list[str],
) -> str | None:
    """
    Responde preguntas del usuario sobre activos durante el setup.
    Retorna texto plano para Telegram (sin JSON).
    """
    obj_txt = " y ".join(_OBJ_DESC.get(o, o) for o in objetivos) if objetivos else "no especificado"
    plazo_txt = _PLAZO_DESC.get(plazo, plazo or "no especificado")

    activos_txt = "\n".join(
        f"- {a['codigo']}: {a['nombre']} (tipo: {a['tipo']}, moneda: {a['moneda']})"
        for a in activos_disponibles
    )
    seleccionados_txt = ", ".join(activos_seleccionados) if activos_seleccionados else "ninguno aún"

    prompt = f"""Sos un asesor financiero personal en Argentina, respondiendo en un chat de Telegram.
El usuario está eligiendo qué activos monitorear para invertir.

PERFIL DEL USUARIO:
- Objetivos: {obj_txt}
- Plazo: {plazo_txt}
- Activos seleccionados hasta ahora: {seleccionados_txt}

ACTIVOS DISPONIBLES EN LA APP:
{activos_txt}

PREGUNTA DEL USUARIO: "{pregunta}"

Respondé de forma clara, breve (máximo 4 oraciones) y en español informal argentino.
Si pregunta por un activo específico, explicá qué es, cómo funciona y si encaja con su perfil.
Si pregunta algo que no es sobre inversiones, redirigí amablemente al tema.
No uses markdown complejo, solo *negrita* cuando sea necesario."""

    try:
        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Error en responder_pregunta_activos: {e}")
        return None


def formatear_mensaje_telegram(activo: dict, rec: dict, recomendacion_id: int) -> tuple[str, list]:
    """
    Arma el texto y los botones inline para enviar por Telegram.
    Retorna (texto, reply_markup)
    """
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
            {"text": "✅ Aceptar", "callback_data": f"inv_ok_{recomendacion_id}"},
            {"text": "❌ Rechazar", "callback_data": f"inv_no_{recomendacion_id}"},
        ]]
    }

    return texto, reply_markup
