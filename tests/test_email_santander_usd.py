from lib.email_parser_santander import identificar_tipo_email, parse_email, TIPO_DEBITO_AUTOMATICO


def test_debito_automatico_en_dolares_se_marca_usd():
    body = (
        "Te informamos que se realizó un débito automático con tu tarjeta Santander Visa Crédito "
        "terminada en 2670.\nMonto U$S 20,00\nCuotas 1\nComercio CLAUDE.AI SUBSCRIPTION\n"
        "Fecha 03/10/2026\nHora 10:15"
    )
    tipo = identificar_tipo_email("Débito automático", body)
    assert tipo == TIPO_DEBITO_AUTOMATICO
    p = parse_email(tipo, "Débito automático", body)
    assert p["moneda"] == "USD"
    assert p["monto"] == 20.0
    assert p["descripcion"] == "CLAUDE.AI SUBSCRIPTION"
