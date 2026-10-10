from datetime import date

from lib.gmail_sync import calcular_desde

HOY = date(2026, 10, 9)


def test_sin_marca_usa_cinco_dias():
    assert calcular_desde(HOY, None) == date(2026, 10, 4)


def test_corrida_reciente_igual_mira_cinco_dias():
    assert calcular_desde(HOY, "2026-10-09T16:34:58+00:00") == date(2026, 10, 4)


def test_cron_caido_mucho_tiempo_lee_desde_la_ultima_corrida():
    # el cron no corrió del 20/09 al 07/10: antes se perdían los mails de ese hueco
    assert calcular_desde(date(2026, 10, 7), "2026-09-20T21:33:56Z") == date(2026, 9, 19)


def test_tope_de_sesenta_dias():
    assert calcular_desde(HOY, "2026-01-01T00:00:00Z") == date(2026, 8, 10)


def test_backfill_manual_manda():
    assert calcular_desde(HOY, "2026-10-09T16:00:00Z", date(2026, 9, 19)) == date(2026, 9, 19)
