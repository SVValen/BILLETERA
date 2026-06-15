import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from lib.parser import (
    parse_movement,
    categorize_from_keywords,
    parse_recurrente,
    parse_cuotas,
)
from lib.date_utils import mes_rango, validate_mes, add_months
from datetime import date


# ── parse_movement ─────────────────────────────────────────────────────────────

class TestParseMovement:
    def test_gasto_simple(self):
        r = parse_movement("5000 comida")
        assert r is not None
        assert r["monto"] == 5000.0
        assert r["tipo"] == "gasto"

    def test_gasto_con_prefijo(self):
        r = parse_movement("gasté 3000 en nafta")
        assert r is not None
        assert r["monto"] == 3000.0
        assert r["tipo"] == "gasto"

    def test_gasto_prefijo_sin_tilde(self):
        r = parse_movement("gaste 1500 super")
        assert r is not None
        assert r["tipo"] == "gasto"

    def test_ingreso_explicito(self):
        r = parse_movement("ingreso 50000 freelance")
        assert r is not None
        assert r["tipo"] == "ingreso"
        assert r["monto"] == 50000.0

    def test_ingreso_cobré(self):
        r = parse_movement("cobré 20000")
        assert r is not None
        assert r["tipo"] == "ingreso"

    def test_ingreso_keyword_sueldo(self):
        r = parse_movement("sueldo 80000")
        assert r is not None
        assert r["tipo"] == "ingreso"
        assert r["monto"] == 80000.0

    def test_ingreso_por_descripcion(self):
        # "500 sueldo extra" → descripción contiene keyword de ingreso
        r = parse_movement("500 sueldo extra")
        assert r is not None
        assert r["tipo"] == "ingreso"

    def test_separador_miles(self):
        r = parse_movement("25.000 supermercado")
        assert r is not None
        assert r["monto"] == 25000.0

    def test_monto_decimal(self):
        r = parse_movement("2,49 spotify")
        assert r is not None
        assert r["monto"] == pytest.approx(2.49)

    def test_texto_sin_monto_retorna_none(self):
        assert parse_movement("hola como estás") is None

    def test_solo_numero_retorna_none(self):
        # "500" solo, sin descripción, no matchea el patrón que requiere texto después
        assert parse_movement("500") is None

    def test_descripcion_preservada(self):
        r = parse_movement("15000 ropa remera nueva")
        assert r is not None
        assert "ropa" in r["descripcion"]


# ── categorize_from_keywords ───────────────────────────────────────────────────

class TestCategorize:
    def test_supermercado(self):
        assert categorize_from_keywords("carrefour compras") == 1

    def test_transporte(self):
        assert categorize_from_keywords("uber viaje al trabajo") == 2

    def test_comida(self):
        assert categorize_from_keywords("pizza delivery pedidosya") == 3

    def test_servicios(self):
        assert categorize_from_keywords("edenor luz mes") == 4

    def test_entretenimiento(self):
        assert categorize_from_keywords("netflix") == 5

    def test_salud(self):
        assert categorize_from_keywords("farmacia remedios") == 6

    def test_fallback_otros(self):
        assert categorize_from_keywords("xyzzy algo raro") == 7

    def test_suscripciones(self):
        # "suscripcion" es keyword exclusiva de cat 18; "spotify" matchea cat 5 primero
        assert categorize_from_keywords("suscripcion plan mensual") == 18

    def test_case_insensitive(self):
        assert categorize_from_keywords("NETFLIX") == 5


# ── parse_recurrente ───────────────────────────────────────────────────────────

class TestParseRecurrente:
    def test_todos_los_N(self):
        assert parse_recurrente("internet todos los 15 del mes") == 15

    def test_el_N_de_cada_mes(self):
        assert parse_recurrente("alquiler el 5 de cada mes") == 5

    def test_cada_mes_el_N(self):
        assert parse_recurrente("cada mes el 1") == 1

    def test_mensualmente_el_N(self):
        assert parse_recurrente("mensualmente el 20") == 20

    def test_sin_patron_retorna_none(self):
        assert parse_recurrente("5000 comida") is None

    def test_dia_invalido_ignorado(self):
        assert parse_recurrente("todos los 32 del mes") is None


# ── parse_cuotas ───────────────────────────────────────────────────────────────

class TestParseCuotas:
    def test_cuotas_al_final(self):
        assert parse_cuotas("150000 tele 12 cuotas") == 12

    def test_en_cuotas(self):
        assert parse_cuotas("500 laptop en 6 cuotas") == 6

    def test_sin_cuotas_retorna_none(self):
        assert parse_cuotas("5000 comida") is None

    def test_una_cuota_ignorada(self):
        assert parse_cuotas("5000 en 1 cuota") is None


# ── mes_rango ──────────────────────────────────────────────────────────────────

class TestMesRango:
    def test_mes_normal(self):
        start, end = mes_rango("2026-03")
        assert start == "2026-03-01"
        assert end == "2026-04-01"

    def test_mes_diciembre(self):
        start, end = mes_rango("2026-12")
        assert start == "2026-12-01"
        assert end == "2027-01-01"

    def test_mes_enero(self):
        start, end = mes_rango("2026-01")
        assert start == "2026-01-01"
        assert end == "2026-02-01"


# ── validate_mes ───────────────────────────────────────────────────────────────

class TestValidateMes:
    def test_formato_valido(self):
        assert validate_mes("2026-06") is True

    def test_mes_01(self):
        assert validate_mes("2026-01") is True

    def test_mes_12(self):
        assert validate_mes("2026-12") is True

    def test_mes_13_invalido(self):
        assert validate_mes("2026-13") is False

    def test_mes_00_invalido(self):
        assert validate_mes("2026-00") is False

    def test_formato_incorrecto(self):
        assert validate_mes("invalid") is False

    def test_formato_sin_guion(self):
        assert validate_mes("202606") is False

    def test_vacio(self):
        assert validate_mes("") is False


# ── add_months ─────────────────────────────────────────────────────────────────

class TestAddMonths:
    def test_mes_normal(self):
        assert add_months(date(2026, 3, 15), 1) == date(2026, 4, 15)

    def test_salto_de_anio(self):
        assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)

    def test_dia_31_a_mes_corto(self):
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_cero_meses(self):
        assert add_months(date(2026, 6, 15), 0) == date(2026, 6, 15)

    def test_multiples_meses(self):
        assert add_months(date(2026, 1, 1), 12) == date(2027, 1, 1)
