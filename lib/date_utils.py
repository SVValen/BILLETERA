import re
import calendar
from datetime import date as _date


def validate_mes(mes: str) -> bool:
    """Valida que mes tenga formato YYYY-MM con mes entre 01 y 12."""
    return bool(re.match(r'^\d{4}-(0[1-9]|1[0-2])$', mes))


def mes_rango(mes: str) -> tuple[str, str]:
    """Retorna (fecha_inicio, fecha_fin_exclusive) para un mes en formato YYYY-MM."""
    year, month = int(mes[:4]), int(mes[5:7])
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    return start, end


def add_months(d: _date, months: int) -> _date:
    """Avanza d por N meses, ajustando el día si el mes destino es más corto."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return _date(year, month, day)
