"""
Lectura de la liquidación de expensas (PDF de la administración, ej. Edificio Nuria II).

Busca las filas de la unidad del inquilino (columna Inquilino = 'SOSA VALENTINA', una por
UF y otra por la cochera UC) y arma, por columna, la suma de esas filas. Las columnas se
reconocen por la posición horizontal de su encabezado, así que funciona aunque cambie el
set de columnas de un mes a otro (p. ej. aparece 'Res.Extra.' o 'Partic.').

A cargo del inquilino: todo menos las expensas extraordinarias ('Exp.Extra.').
"""
from __future__ import annotations

import io
import re
from datetime import date

import pdfplumber

_NUM_RE = re.compile(r"^-?[\d.]+,\d{2}$")
_LIQ_RE = re.compile(r"Liquidaci[oó]n:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)
_VTO_RE = re.compile(r"Vencimiento:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)

# Encabezado → clave
_COLUMNAS = {
    "exp.ord.": "exp_ord", "exp.extra.": "exp_extra", "res.ord.": "res_ord", "res.extra.": "res_extra",
    "gas": "gas", "agua": "agua", "partic.": "partic", "total": "total",
    "deuda": "deuda_ant", "intereses": "intereses", "saldo": "saldo",
}


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _headers(words: list[dict]) -> dict[str, float]:
    """Centro x de cada encabezado de columna conocido (primera aparición en la página)."""
    out: dict[str, float] = {}
    for w in words:
        key = _COLUMNAS.get(w["text"].lower())
        if key and key not in out:
            out[key] = (w["x0"] + w["x1"]) / 2
    return out


def _filas_inquilino(words: list[dict], inquilino: str) -> list[float]:
    """Coordenadas 'top' de las filas que contienen el nombre del inquilino."""
    partes = inquilino.upper().split()
    tops = []
    for i, w in enumerate(words):
        if w["text"].upper() == partes[0]:
            sig = [x["text"].upper() for x in words[i:i + len(partes)]]
            if sig == partes:
                tops.append(w["top"])
    return tops


def parse_liquidacion(pdf_bytes: bytes, inquilino: str = "SOSA VALENTINA") -> dict | None:
    """Devuelve los importes de la unidad del inquilino:
    {liquidacion: 'YYYY-MM', mes_pago: 'YYYY-MM', vencimiento, exp_ord, exp_extra, res_ord, res_extra,
     gas, agua, partic, total, a_pagar, expensas_sin_servicios}
    a_pagar = total − exp_extra; expensas_sin_servicios = a_pagar − gas − agua."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        texto_p1 = pdf.pages[0].extract_text() or ""
        sumas: dict[str, float] = {}
        encontrado = False
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            tops = _filas_inquilino(words, inquilino)
            if not tops:
                continue
            heads = _headers(words)
            if "total" not in heads:
                continue
            encontrado = True
            for top in tops:
                fila = [w for w in words if abs(w["top"] - top) < 3 and _NUM_RE.match(w["text"])]
                for w in fila:
                    # columna cuyo encabezado queda más cerca del número
                    key = min(heads, key=lambda k: abs(heads[k] - (w["x0"] + w["x1"]) / 2))
                    sumas[key] = sumas.get(key, 0.0) + _num(w["text"])
        if not encontrado:
            return None

    liq = _LIQ_RE.search(texto_p1)
    vto = _VTO_RE.search(texto_p1)
    if not liq:
        return None
    liq_mes = f"{liq.group(3)}-{liq.group(2)}"
    y, m = int(liq.group(3)), int(liq.group(2))
    mes_pago = f"{y + (m // 12):04d}-{(m % 12) + 1:02d}"

    r = {k: round(v, 2) for k, v in sumas.items()}
    for k in ("exp_ord", "exp_extra", "res_ord", "res_extra", "gas", "agua", "partic", "total"):
        r.setdefault(k, 0.0)
    a_pagar = round(r["total"] - r["exp_extra"], 2)
    componentes = sum(r[k] for k in ("exp_ord", "exp_extra", "res_ord", "res_extra", "gas", "agua", "partic"))
    return {
        "cuadra": abs(componentes - r["total"]) < 1,
        "liquidacion": liq_mes,
        "mes_pago": mes_pago,
        "vencimiento": date(int(vto.group(3)), int(vto.group(2)), int(vto.group(1))).isoformat() if vto else None,
        **{k: r[k] for k in ("exp_ord", "exp_extra", "res_ord", "res_extra", "gas", "agua", "partic", "total")},
        "a_pagar": a_pagar,
        "expensas_sin_servicios": round(a_pagar - r["gas"] - r["agua"], 2),
    }
