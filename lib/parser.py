import re

# Palabras que indican tipo=ingreso sin importar el patrón de texto
INCOME_KEYWORDS = [
    "sueldo", "salario", "cobré", "cobre", "ingresé", "ingrese",
    "honorarios", "freelance", "facturé", "facture", "aguinaldo",
    "bono", "comision", "comisión", "venta", "vendí", "vendi",
    "prestamo", "préstamo", "me pagaron", "me transfirieron",
    "reintegro", "reembolso", "dividendo", "alquiler cobrado",
    "renta", "quiniela", "premio", "ganancia",
]

# Palabras clave por categoria_id
KEYWORDS: dict[int, list[str]] = {
    1: [  # Supermercado
        "super", "supermercado", "dia", "carrefour", "jumbo", "walmart",
        "coto", "disco", "vea", "verduleria", "almacen", "chino",
        "minimarket", "kiosco", "kiosko", "despensa", "mercado",
    ],
    2: [  # Transporte
        "uber", "taxi", "bus", "colectivo", "gasolina", "nafta", "sube",
        "remis", "cabify", "didi", "subte", "tren", "bici", "patente",
        "peaje", "estacionamiento", "cochera", "vtv", "gnc", "autopista",
        "flota", "flete", "moto",
    ],
    3: [  # Comida
        "pizza", "resto", "restaurant", "restaurante", "delivery", "cafe",
        "cafeteria", "burger", "mcdonald", "rappi", "pedidosya", "comida",
        "almuerzo", "cena", "desayuno", "medialunas", "facturas", "empanadas",
        "sushi", "taco", "sandwich", "sandwiche", "milanesa", "pasta",
        "fideos", "parrilla", "asado", "hamburguesa", "hamburgesa", "bife",
        "helado", "heladeria", "pasteleria", "panaderia", "bar", "cerveza",
        "vino", "tragos", "minutas", "tenedor", "comer", "almorcé", "cené",
        "desayuné", "almorce", "cene", "desayune", "bifes",
    ],
    4: [  # Servicios
        "luz", "agua", "internet", "telefono", "teléfono", "gas",
        "expensas", "alquiler", "electricidad", "edesur", "edenor",
        "aysa", "claro", "personal", "movistar", "directv", "cable",
        "metrogas", "seguro", "obra social", "mutual", "prepaga",
        "netflix mensual", "spotify mensual",
    ],
    5: [  # Entretenimiento
        "cine", "netflix", "spotify", "juego", "steam", "teatro",
        "concierto", "show", "evento", "entrada", "disney", "hbo",
        "amazon prime", "prime video", "youtube premium", "twitch",
        "playstation", "xbox", "nintendo", "boliche", "antro", "disco",
        "recital", "futbol", "partido",
    ],
    6: [  # Salud
        "farmacia", "doctor", "medico", "médico", "clinica", "clínica",
        "hospital", "medicamento", "medicina", "consulta", "turno",
        "dentista", "odontologo", "odontólogo", "psicologo", "psicólogo",
        "terapia", "analisis", "análisis", "laboratorio", "optica",
        "óptica", "lentes", "guardia",
    ],
    7: [],  # Otros (fallback)
    8: [  # Ropa / Shopping
        "ropa", "zapatillas", "indumentaria", "shopping", "zara", "h&m",
        "adidas", "nike", "remera", "pantalon", "pantalón", "vestido",
        "camisa", "campera", "calzado", "zapatos", "buzo", "jean",
    ],
    9: [  # Educación
        "curso", "libro", "escuela", "universidad", "facultad", "udemy",
        "coursera", "clase", "seminario", "taller", "capacitacion",
        "capacitación", "estudio",
    ],
}


def categorize_from_keywords(text: str) -> int:
    text_lower = text.lower()
    for cat_id, keywords in KEYWORDS.items():
        if cat_id == 7:
            continue  # Otros siempre es el fallback
        if any(kw in text_lower for kw in keywords):
            return cat_id
    return 7  # Otros


def is_income_by_keywords(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in INCOME_KEYWORDS)


def parse_movement(text: str) -> dict | None:
    """Parsea un mensaje de texto y extrae monto, descripción y tipo.

    Formatos aceptados:
    - "Gasté 25000 en supermercado"
    - "gaste 25.000 supermercado"
    - "25000 supermercado"
    - "Ingreso 50000 sueldo"
    - "sueldo 50000"  ← auto-detectado como ingreso por keyword
    """
    text = text.strip()

    # Normalizar separadores de miles: 25.000 → 25000
    cleaned = re.sub(r"(\d)\.(\d{3})\b", r"\1\2", text)

    patterns = [
        # "gasté/gaste 25000 [en] descripcion"
        (r"gast[eé]\s+([\d]+(?:[.,]\d+)?)\s+(?:en\s+)?(.+)", "gasto"),
        # "ingreso/ingresé 50000 [descripcion]"
        (r"ingres[oóeé]\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso"),
        # "cobré/cobré 50000 [descripcion]"
        (r"cobr[eé]\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso"),
        # "sueldo 50000" / "salario 50000"
        (r"(sueldo|salario|aguinaldo|bono)\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso_keyword"),
        # "25000 descripcion"
        (r"([\d]+(?:[.,]\d+)?)\s+(.+)", "gasto"),
    ]

    for pattern, tipo_base in patterns:
        match = re.search(pattern, cleaned.lower())
        if match:
            if tipo_base == "ingreso_keyword":
                # Grupos: (keyword)(monto)(descripcion)
                keyword = match.group(1)
                raw_monto = match.group(2).replace(",", ".")
                descripcion = (match.group(3) or keyword).strip() or keyword
                tipo = "ingreso"
            else:
                raw_monto = match.group(1).replace(",", ".")
                descripcion = (match.group(2) if match.lastindex >= 2 else text) or text
                descripcion = descripcion.strip()
                tipo = tipo_base

            monto = float(raw_monto)

            # Auto-detectar ingresos por keywords en la descripción
            if tipo == "gasto" and is_income_by_keywords(descripcion):
                tipo = "ingreso"

            return {"monto": monto, "descripcion": descripcion or text, "tipo": tipo}

    return None
