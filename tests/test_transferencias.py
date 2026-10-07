from lib.email_parser_santander import TIPO_TRANSFERENCIA, identificar_tipo_email, parse_email

BODY = """Transferencia realizada
Destinatario
NARANJA DIGITAL COMPANIA FINANCIERA
Cuenta de origen
Cuenta Unica $ 000-123456/7
CBU de Destino
3220001805000012345678
Importe
$ 382.000,00
Número de comprobante
123456789
"""


def test_transferencia_destinatario_y_cbu():
    assert identificar_tipo_email("Aviso de transferencia", BODY) == TIPO_TRANSFERENCIA
    p = parse_email(TIPO_TRANSFERENCIA, "Aviso de transferencia", BODY)
    assert p["monto"] == 382000.0
    assert p["destinatario"] == "NARANJA DIGITAL COMPANIA FINANCIERA"
    assert p["cbu"] == "3220001805000012345678"


def test_transferencia_en_una_linea():
    body = "Destinatario: Juan Perez Cuenta de origen: CA $ 1 CBU de Destino: 0110000000000000000001 Importe $ 120.000,00"
    p = parse_email(TIPO_TRANSFERENCIA, "", body)
    assert p["destinatario"] == "Juan Perez"
    assert p["cbu"] == "0110000000000000000001"
    assert p["monto"] == 120000.0


REAL = """Información sobre tu transferencia

Se realizó la siguiente transferencia a tu nombre:

Destinatario 27000000001
Cuenta de origen Cuenta en Pesos XXX-XXX 0000
CBU de Destino 0000003100000000000001
Importe $ 840.543,80
Número de comprobante 1
"""


def test_formato_real_santander():
    from lib.transferencias import entidad
    assert identificar_tipo_email("Aviso de transferencia", REAL) == TIPO_TRANSFERENCIA
    p = parse_email(TIPO_TRANSFERENCIA, "Aviso de transferencia", REAL)
    assert p["monto"] == 840543.80
    assert p["destinatario"] == "27000000001"
    assert p["cbu"] == "0000003100000000000001"
    assert entidad(p["cbu"]) == "Mercado Pago"
    assert entidad("0170218940000000000000") == "BBVA"
    assert entidad("0110000000000000000000") == "Banco Nación"
