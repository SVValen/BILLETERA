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
