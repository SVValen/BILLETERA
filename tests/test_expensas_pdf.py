"""Prueba del lector de liquidaciones con un PDF sintético con el mismo layout (columnas
por posición). Los PDF reales no se suben al repo porque tienen datos de terceros."""
import io

import pytest

reportlab = pytest.importorskip("reportlab")
from reportlab.lib.pagesizes import landscape, A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from lib.expensas_pdf import parse_liquidacion  # noqa: E402

COLS = [("Exp.Ord.", 330), ("Exp.Extra.", 390), ("Res.Ord.", 450), ("Res.Extra.", 510),
        ("GAS", 560), ("AGUA", 610), ("Total", 680), ("Saldo", 760)]


def _pdf(filas):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    c.setFont("Helvetica", 7)
    c.drawString(500, 580, "Vencimiento: 10/10/2026 | Liquidación: 30/09/2026 | Impresión: 01/10/2026 08:56")
    c.drawString(20, 560, "Propietario")
    c.drawString(110, 560, "Unidad")
    c.drawString(170, 560, "Inquilino")
    for nombre, x in COLS:
        c.drawRightString(x, 560, nombre)
    y = 540
    for prop, unidad, inq, valores in filas:
        c.drawString(20, y, prop)
        c.drawString(110, y, unidad)
        c.drawString(170, y, inq)
        for (nombre, x) in COLS:
            v = valores.get(nombre)
            if v:
                c.drawRightString(x, y, v)
        y -= 14
    c.save()
    return buf.getvalue()


def test_suma_uf_y_cochera_y_descuenta_extraordinarias():
    pdf = _pdf([
        ("OTRO DUENO", "UF - 1° A", "", {"Exp.Ord.": "100,00", "Total": "100,00", "Saldo": "100,00"}),
        ("PINDO ALICIA", "UF - 5° D", "SOSA VALENTINA", {
            "Exp.Ord.": "158.081,51", "Res.Ord.": "23.712,23", "Res.Extra.": "10.626,00",
            "GAS": "11.920,00", "AGUA": "41.023,66", "Total": "245.363,40", "Saldo": "245.363,40"}),
        ("", "UC - 8", "SOSA VALENTINA", {
            "Exp.Ord.": "18.059,18", "Exp.Extra.": "23.717,58", "Res.Ord.": "6.266,52",
            "Res.Extra.": "1.254,00", "Total": "49.297,28", "Saldo": "49.297,28"}),
    ])
    r = parse_liquidacion(pdf)
    assert r["liquidacion"] == "2026-09"
    assert r["mes_pago"] == "2026-10"
    assert r["total"] == 294660.68
    assert r["exp_extra"] == 23717.58
    assert r["a_pagar"] == 270943.10
    assert r["gas"] == 11920.00 and r["agua"] == 41023.66
    assert r["expensas_sin_servicios"] == 217999.44
    assert r["cuadra"]


def test_sin_fila_del_inquilino():
    pdf = _pdf([("OTRO DUENO", "UF - 1° A", "", {"Exp.Ord.": "100,00", "Total": "100,00"})])
    assert parse_liquidacion(pdf) is None
