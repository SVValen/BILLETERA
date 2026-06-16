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

    prompt = f"""Sos un asistente financiero personal en Argentina. Analizá este activo y generá una recomendación concreta.

PERFIL DEL USUARIO:
- Tipo: {perfil.get("perfil", "moderado")} — {perfil_desc}
- Objetivo: {perfil.get("objetivo", "no especificado")}
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
        # Extraer JSON si viene con texto extra
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
