from datetime import date

from lib.email_parser_naranja import (
    identificar_tipo_email_naranja, parse_email_naranja, TIPO_NARANJA_COMPRA,
)

BODY = """Ver este email desde tu navegador.

¡Hola, Valentina !
Te compartimos el detalle de la compra
que ingresó en tu tarjeta de crédito:
TU COMPRA
$ 3.490,00
MERPAGO MELI
Titular - Valentina Sosa
Tarjeta NARANJA VIRTUAL
Plan 01   cuota  en PESOS
Sabado 03/OCT - 14:07 h
(S.E.U.O.)
¿No hiciste esta compra? Avisanos
"""
SUBJECT = "Valentina👉 Ingresó una compra en tu tarjeta crédito"


def test_compra_1_pago():
    assert identificar_tipo_email_naranja(SUBJECT, BODY) == TIPO_NARANJA_COMPRA
    p = parse_email_naranja(SUBJECT, BODY, date(2026, 10, 3))
    assert p == {
        "monto": 3490.0, "moneda": "ARS", "descripcion": "MERPAGO MELI",
        "fecha": "2026-10-03", "num_cuotas": 1,
        "tarjeta_nombre": "Naranja", "tarjeta_detalle": "NARANJA VIRTUAL",
    }


def test_compra_en_cuotas_html_aplanado():
    body = ("TU COMPRA $ 180.000,00 FRAVEGA SA Titular - Valentina Sosa "
            "Tarjeta NARANJA Plan 06 cuotas en PESOS Martes 14/OCT - 18:22 h")
    p = parse_email_naranja("Ingresó una compra", body, date(2026, 10, 14))
    assert p["monto"] == 180000.0
    assert p["num_cuotas"] == 6
    assert p["descripcion"] == "FRAVEGA SA"
    assert p["fecha"] == "2026-10-14"


def test_compra_en_dolares():
    body = ("TU COMPRA U$S 20,00 CLAUDE.AI Titular - Valentina Sosa "
            "Tarjeta NARANJA VIRTUAL Plan 01 cuota en DOLARES Viernes 02/OCT - 09:00 h")
    p = parse_email_naranja("Ingresó una compra", body, date(2026, 10, 2))
    assert p["moneda"] == "USD"
    assert p["monto"] == 20.0


def test_compra_de_diciembre_avisada_en_enero():
    body = "TU COMPRA $ 1.000,00 KIOSCO Titular - X Tarjeta NARANJA Plan 01 cuota en PESOS Miércoles 31/DIC - 23:50 h"
    p = parse_email_naranja("Ingresó una compra", body, date(2027, 1, 1))
    assert p["fecha"] == "2026-12-31"


def test_mail_que_no_es_compra():
    assert parse_email_naranja("Tu resumen", "Tu resumen ya está disponible", date(2026, 10, 1)) is None
