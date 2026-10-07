"""
Parsing de los avisos de compra de Naranja X ("Ingresó una compra en tu tarjeta crédito").

Formato (texto plano o HTML convertido a texto, con saltos de línea variables):

    TU COMPRA
    $ 3.490,00
    MERPAGO MELI
    Titular - Valentina Sosa
    Tarjeta NARANJA VIRTUAL
    Plan 01   cuota  en PESOS
    Sabado 03/OCT - 14:07 h

El monto es el total de la compra; el plan indica la cantidad de cuotas.
La fecha no trae año: se toma del encabezado Date del mail.
"""
from __future__ import annotations

import re
from datetime import date

NARANJA_SENDER = "naranjax.com"
TIPO_NARANJA_COMPRA = "naranja_compra"

_MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
          "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12}

_RE_MONTO = re.compile(r"TU\s+COMPRA\s*(U\$S|US\$|USD|\$)\s*([\d.,]+)", re.IGNORECASE)
_RE_COMERCIO = re.compile(r"TU\s+COMPRA\s*(?:U\$S|US\$|USD|\$)\s*[\d.,]+\s*(.+?)\s*Titular", re.IGNORECASE | re.DOTALL)
_RE_TARJETA = re.compile(r"Tarjeta\s+(NARANJA[A-ZÁÉÍÓÚÑ ]*?)\s*(?:Plan|\n|$)", re.IGNORECASE)
_RE_PLAN = re.compile(r"Plan\s*(\d+)\s*cuotas?\s*en\s*(PESOS|D[OÓ]LARES)", re.IGNORECASE)
_RE_FECHA = re.compile(r"(\d{1,2})\s*/\s*([A-Z]{3})\b", re.IGNORECASE)


def identificar_tipo_email_naranja(subject: str, body: str) -> str | None:
    texto = f"{subject}\n{body}".lower()
    if "ingresó una compra" in texto or "ingreso una compra" in texto or "tu compra" in texto:
        return TIPO_NARANJA_COMPRA
    return None


def _parse_monto_ar(raw: str) -> float:
    """'3.490,00' -> 3490.0"""
    return float(raw.replace(".", "").replace(",", "."))


def _fecha(dia: int, mes_abrev: str, fecha_mail: date) -> str | None:
    mes = _MESES.get(mes_abrev.upper())
    if not mes:
        return None
    anio = fecha_mail.year
    # Un aviso de enero puede traer una compra del 31/DIC del año anterior
    if mes > fecha_mail.month + 1:
        anio -= 1
    try:
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return None


def parse_email_naranja(subject: str, body: str, fecha_mail: date) -> dict | None:
    """Campos: monto, moneda, descripcion, fecha (ISO), num_cuotas, tarjeta_nombre ('Naranja'),
    tarjeta_detalle ('NARANJA VIRTUAL'). None si falta algo esencial."""
    monto_m = _RE_MONTO.search(body)
    comercio_m = _RE_COMERCIO.search(body)
    if not (monto_m and comercio_m):
        return None

    simbolo = monto_m.group(1).upper()
    plan_m = _RE_PLAN.search(body)
    moneda = "USD" if simbolo != "$" or (plan_m and plan_m.group(2).upper().startswith("D")) else "ARS"

    fecha_m = _RE_FECHA.search(body)
    fecha = _fecha(int(fecha_m.group(1)), fecha_m.group(2), fecha_mail) if fecha_m else None

    comercio = re.sub(r"\s+", " ", comercio_m.group(1)).strip()
    tarjeta_m = _RE_TARJETA.search(body)

    return {
        "monto": _parse_monto_ar(monto_m.group(2)),
        "moneda": moneda,
        "descripcion": comercio,
        "fecha": fecha or fecha_mail.isoformat(),
        "num_cuotas": int(plan_m.group(1)) if plan_m else 1,
        "tarjeta_nombre": "Naranja",
        "tarjeta_detalle": re.sub(r"\s+", " ", tarjeta_m.group(1)).strip() if tarjeta_m else "NARANJA",
    }
