import re

# Palabras clave por categoria_id (Fase 1: sin IA)
KEYWORDS: dict[int, list[str]] = {
    1: ["super", "dia", "carrefour", "jumbo", "walmart", "verduleria", "almacen", "chino"],
    2: ["uber", "taxi", "bus", "colectivo", "gasolina", "nafta", "sube", "remis"],
    3: ["pizza", "resto", "restaurant", "delivery", "cafe", "burger", "mcdonald", "rappi", "pedidosya"],
    4: ["luz", "agua", "internet", "telefono", "gas", "expensas", "alquiler"],
    5: ["cine", "netflix", "spotify", "juego", "steam", "teatro", "concert"],
    6: ["farmacia", "doctor", "medico", "clinica", "hospital", "medicamento"],
}


def categorize_from_keywords(text: str) -> int:
    text_lower = text.lower()
    for cat_id, keywords in KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return cat_id
    return 7  # Otros


def parse_movement(text: str) -> dict | None:
    """Parsea un mensaje de texto y extrae monto, descripción y tipo.

    Formatos aceptados:
    - "Gasté 25000 en supermercado"
    - "gaste 25.000 supermercado"
    - "25000 supermercado"
    - "Ingreso 50000 sueldo"
    """
    text = text.strip()

    # Normalizar separadores de miles: 25.000 → 25000
    cleaned = re.sub(r"(\d)\.(\d{3})\b", r"\1\2", text)

    patterns = [
        # "gasté/gaste 25000 [en] descripcion"
        (r"gast[eé]\s+([\d]+(?:[.,]\d+)?)\s+(?:en\s+)?(.+)", "gasto"),
        # "ingreso 50000 [descripcion]"
        (r"ingreso\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso"),
        # "25000 descripcion"
        (r"([\d]+(?:[.,]\d+)?)\s+(.+)", "gasto"),
    ]

    for pattern, tipo in patterns:
        match = re.search(pattern, cleaned.lower())
        if match:
            raw_monto = match.group(1).replace(",", ".")
            monto = float(raw_monto)
            descripcion = (match.group(2) or text).strip() or text
            return {"monto": monto, "descripcion": descripcion, "tipo": tipo}

    return None
