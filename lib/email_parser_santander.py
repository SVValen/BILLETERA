"""
Parsing de los 4 tipos de mail de aviso de Santander (Fase 1):
  a) débito automático en tarjeta de crédito (ej. suscripciones USD)
  b) pago con tarjeta de crédito en 1 pago
  c) pago con tarjeta de crédito en cuotas
  d) pago con tarjeta de débito

Todos comparten el mismo layout de campos (Monto / Cuotas / Comercio / Fecha / Hora),
con o sin saltos de línea entre el label y el valor según el cliente de mail.
"""
import re
from datetime import date

TIPO_DEBITO_AUTOMATICO = "debito_automatico"
TIPO_PAGO_1_PAGO = "pago_1_pago"
TIPO_PAGO_CUOTAS = "pago_cuotas"
TIPO_PAGO_DEBITO = "pago_debito"

_RE_LAST4 = re.compile(r"terminada en\s*(\d{4})", re.IGNORECASE)
_RE_MONTO = re.compile(r"Monto\s*(U\$S|\$)\s*([\d.,]+)", re.IGNORECASE)
_RE_CUOTAS = re.compile(r"Cuotas\s*(\d+)", re.IGNORECASE)
_RE_COMERCIO = re.compile(r"Comercio\s*(.+?)\s*(?=Fecha)", re.IGNORECASE)
_RE_FECHA = re.compile(r"Fecha\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


def identificar_tipo_email(subject: str, body: str) -> str | None:
    """Identifica el tipo de mail de Santander según subject/body. None si no matchea ninguno."""
    texto = f"{subject}\n{body}"
    texto_low = texto.lower()

    if "débito automático" in texto_low:
        return TIPO_DEBITO_AUTOMATICO

    if "tarjeta santander visa débito" in texto_low:
        return TIPO_PAGO_DEBITO

    if "tarjeta santander visa crédito" in texto_low:
        m = _RE_CUOTAS.search(body)
        if m and int(m.group(1)) > 1:
            return TIPO_PAGO_CUOTAS
        return TIPO_PAGO_1_PAGO

    return None


def _parse_monto_ar(raw: str) -> float:
    """'356.000,00' -> 356000.0 (separador de miles '.', decimal ',')"""
    return float(raw.replace(".", "").replace(",", "."))


def _parse_fecha_ar(raw: str) -> str:
    """'02/05/2026' -> '2026-05-02'"""
    dd, mm, yyyy = raw.split("/")
    return date(int(yyyy), int(mm), int(dd)).isoformat()


def parse_email(tipo: str, subject: str, body: str) -> dict | None:
    """
    Extrae los campos comunes de un mail ya identificado. Retorna None si faltan
    campos requeridos (mail con formato inesperado).
    Campos: monto (float), moneda ('ARS'|'USD'), descripcion (str), fecha (ISO str),
    last4 (str de 4 dígitos), num_cuotas (int, solo para TIPO_PAGO_CUOTAS).
    """
    last4_m = _RE_LAST4.search(body)
    monto_m = _RE_MONTO.search(body)
    comercio_m = _RE_COMERCIO.search(body)
    fecha_m = _RE_FECHA.search(body)

    if not (last4_m and monto_m and comercio_m and fecha_m):
        return None

    moneda = "USD" if monto_m.group(1).upper() == "U$S" else "ARS"
    monto = _parse_monto_ar(monto_m.group(2))
    comercio = comercio_m.group(1).strip()

    result = {
        "monto": monto,
        "moneda": moneda,
        "descripcion": comercio,
        "fecha": _parse_fecha_ar(fecha_m.group(1)),
        "last4": last4_m.group(1),
    }

    if tipo == TIPO_PAGO_CUOTAS:
        cuotas_m = _RE_CUOTAS.search(body)
        if not cuotas_m:
            return None
        result["num_cuotas"] = int(cuotas_m.group(1))

    return result
