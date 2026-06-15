def mes_rango(mes: str) -> tuple[str, str]:
    """Retorna (fecha_inicio, fecha_fin_exclusive) para un mes en formato YYYY-MM."""
    year, month = int(mes[:4]), int(mes[5:7])
    start = f"{year}-{month:02d}-01"
    end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
    return start, end
