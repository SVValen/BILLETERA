import re

# ── Detección de aportes a portafolios ────────────────────────────────────────

_APORTE_RE = re.compile(
    r"(?:sumé|sume|sumo|agrego|agregué|agregue|deposité|deposite|añadí|añadi|cargué|cargue)"
    r"\s+\$?([\d.,]+)"
    r"(?:\s+(USD|u\$s|usd|dólares?|dolares?|ARS|pesos?))?"
    r"(?:\s+(?:al?|a\s+(?:mi\s+)?|en(?:\s+(?:el?\s+)?|(?:\s+mi\s+)?))\s*(.+))?",
    re.IGNORECASE,
)
_MONEDA_USD_RE = re.compile(r"USD|u\$s|usd|dólares?|dolares?", re.IGNORECASE)
_MONEDA_ARS_RE = re.compile(r"ARS|pesos?", re.IGNORECASE)


def parse_aporte(text: str) -> dict | None:
    """
    Detecta aportes de capital a portafolios.
    Retorna {"monto": float, "moneda": "USD"|"ARS", "hint": str|None} o None.

    Ejemplos:
      "sumé 500 USD"                     → monto=500, moneda=USD
      "agregué 200000 pesos al conservador" → monto=200000, moneda=ARS, hint="conservador"
      "deposité 1000 a mi portafolio"    → monto=1000, moneda=USD (heurística)
    """
    m = _APORTE_RE.search(text.strip())
    if not m:
        return None

    monto_raw = m.group(1).replace(".", "").replace(",", ".")
    try:
        monto = float(monto_raw)
    except ValueError:
        return None
    if monto <= 0:
        return None

    moneda_str = m.group(2) or ""
    hint = (m.group(3) or "").strip().lower() or None

    if _MONEDA_ARS_RE.match(moneda_str):
        moneda = "ARS"
    elif _MONEDA_USD_RE.match(moneda_str):
        moneda = "USD"
    elif hint:
        # Sin moneda explícita pero con destino: heurística por magnitud
        moneda = "ARS" if monto >= 50_000 else "USD"
    else:
        # Sin moneda ni destino: no es un aporte ("agregué 3000 nafta")
        return None

    return {"monto": monto, "moneda": moneda, "hint": hint}


# ── Detección de gastos recurrentes y cuotas ─────────────────────────────────

def parse_recurrente(text: str) -> int | None:
    """Detecta si el texto configura un gasto recurrente. Retorna el día del mes (1-31)."""
    patterns = [
        r"todos?\s+los?\s+(\d{1,2})(?:\s+del?\s+mes)?",
        r"el\s+(\d{1,2})\s+de\s+cada\s+mes",
        r"cada\s+mes\s+el\s+(\d{1,2})",
        r"mensual(?:mente)?\s+el\s+(\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, text.lower())
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                return day
    return None


def parse_cuota_progreso(text: str) -> tuple[int, int] | None:
    """Detecta cuotas en progreso. Retorna (cuota_actual, total_cuotas) o None.
    Ejemplos: 'cuota 3/12', '3/12 cuotas', 'cuota 3 de 12'."""
    t = text.lower()
    patterns = [
        r"cuota\s+(\d+)\s*/\s*(\d+)",
        r"(\d+)\s*/\s*(\d+)\s+cuotas?",
        r"cuota\s+(\d+)\s+de\s+(\d+)",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            actual, total = int(m.group(1)), int(m.group(2))
            if 1 <= actual <= total and total > 1:
                return actual, total
    return None


def parse_cuotas(text: str) -> int | None:
    """Detecta si el texto menciona cuotas. Retorna el número de cuotas."""
    if parse_cuota_progreso(text):
        return None
    m = re.search(r"(?:en\s+)?(\d+)\s*cuotas?\b", text.lower())
    if m:
        n = int(m.group(1))
        return n if n > 1 else None
    return None


def strip_recurrente(text: str) -> str:
    """Elimina el patrón recurrente del texto para parsear monto/descripción limpio."""
    cleaned = re.sub(r"todos?\s+los?\s+\d{1,2}(?:\s+del?\s+mes)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"el\s+\d{1,2}\s+de\s+cada\s+mes", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"cada\s+mes\s+el\s+\d{1,2}", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"mensual(?:mente)?\s+el\s+\d{1,2}", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def strip_cuotas(text: str) -> str:
    """Elimina la mención de cuotas del texto para parsear monto/descripción limpio."""
    cleaned = re.sub(r"cuota\s+\d+\s*/\s*\d+", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d+\s*/\s*\d+\s+cuotas?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"cuota\s+\d+\s+de\s+\d+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:en\s+)?\d+\s*cuotas?\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


# Palabras que indican tipo=ingreso independientemente del patrón
INCOME_KEYWORDS = [
    "sueldo", "salario", "cobré", "cobre", "ingresé", "ingrese",
    "honorarios", "freelance", "facturé", "facture", "aguinaldo",
    "bono", "comision", "comisión", "venta", "vendí", "vendi",
    "me pagaron", "me transfirieron", "reintegro", "reembolso",
    "dividendo", "renta", "quiniela", "premio", "ganancia",
]

# ── Categorías (IDs = IDs reales de la tabla categorias en Supabase) ──
KEYWORDS: dict[int, list[str]] = {
    1: [  # Supermercado 🛒
        "super", "supermercado", "almacen", "almacén", "carrefour", "disco",
        "dia", "día", "jumbo", "coto", "chino", "verduleria", "verdulería",
        "granja", "dietetica", "dietética", "mercadito", "bazar", "despensa",
        "maxixe", "walmart", "vea",
    ],
    2: [  # Transporte 🚗
        "uber", "bolt", "taxi", "remis", "colectivo", "bondi", "subte",
        "metro", "tren", "sube", "boleto", "nafta", "gasolina", "gnc",
        "combustible", "carga nafta", "estacionamiento", "cochera",
        "patente", "vtv", "mecanico", "mecánico", "gomeria", "gomerÃ­a",
        "lavadero", "autopista", "peaje", "cabify", "didi", "bici",
        "molinete", "viaje", "viajes", "estacion", "estación",
    ],
    3: [  # Comida 🍽️
        "resto", "restaurant", "restaurante", "asado", "pizza", "milanesa",
        "burger", "delivery", "pedidosya", "rappi", "cafe", "café",
        "cafeteria", "bar", "chopp", "birra", "cerveza", "vino", "cena",
        "almuerzo", "desayuno", "sandwich", "sandwiche", "sándwich",
        "empanada", "locro", "pollo", "carne", "parrilla", "pizzeria",
        "pizzería", "sushi", "kebab", "medialunas", "facturas",
        "hamburguesa", "asador", "grill", "fideos", "pasta", "noquis",
        "ñoquis", "tallarin", "tallarín", "canelones", "comida",
        "almorcé", "cené", "desayuné", "almorce", "cene", "desayune",
        "tacos", "mcdonald", "minutas", "helado", "heladeria", "panaderia",
    ],
    4: [  # Servicios 💡
        "luz", "edenor", "edesur", "agua", "aysa", "aysam", "gas",
        "metrogas", "internet", "movistar", "personal", "claro", "telecom",
        "fibertel", "speedy", "telefono", "teléfono", "cablevisión",
        "cablevision", "directv", "flow", "expensas", "alquiler",
        "monotributo", "impuesto", "registro", "afiliacion", "afiliación",
        "obra social", "pami", "sindicato", "aportes", "contribucion",
        "contribución", "servicios",
    ],
    5: [  # Entretenimiento 🎬
        "netflix", "spotify", "prime", "disney", "hulu", "cine",
        "pelicula", "película", "teatro", "concierto", "show", "entrada",
        "boleteria", "boleterÃ­a", "videojuegos", "steam", "playstation",
        "xbox", "nintendo", "juego", "libro", "audiolibro", "kindle",
        "streaming", "musica", "música", "recital", "boliche", "antro",
        "disco", "partido", "futbol",
    ],
    6: [  # Salud 🏥
        "farmacia", "medicamento", "medicina", "remedios", "doctor",
        "medico", "médico", "odontologo", "odontólogo", "dentista",
        "clinica", "clínica", "hospital", "optica", "óptica", "lentes",
        "psicologo", "psicólogo", "terapia", "kinesio", "kinésio",
        "analisis", "análisis", "laboratorio", "radiologia", "radiología",
        "resonancia", "estudio medico", "sangre", "receta", "consulta",
        "turno medico", "guardia", "emergencia", "ambulancia",
    ],
    7: [],  # Otros 📌 — fallback, sin keywords
    8: [  # Ropa 👕
        "ropa", "remera", "pantalon", "pantalón", "zapatos", "zapatillas",
        "bolso", "cartera", "cinturon", "cinturón", "bufanda", "gorro",
        "buzo", "campera", "abrigo", "vestido", "falda", "medias",
        "sombrero", "anteojos", "gafas", "reloj", "accesorios", "tienda",
        "shopping", "outlet", "traje", "camisa", "corbata", "calcetines",
        "bikini", "boxers", "calzado", "marca", "boutique", "local ropa",
    ],
    9: [  # Educación 📚
        "escuela", "colegio", "universidad", "facultad", "arancel",
        "curso", "clases", "profesor", "tutorias", "tutorías",
        "maestria", "maestría", "carrera", "diplomado", "taller",
        "idioma", "ingles", "inglés", "frances", "francés", "aleman",
        "alemán", "portugues", "portugués", "utiles", "útiles",
        "cuadernos", "lapices", "lápices", "laptop", "tablet",
        "academia", "instituto", "formacion", "formación",
        "capacitacion", "capacitación", "seminario", "workshop",
        "masterclass", "udemy", "coursera",
    ],
    10: [  # Vivienda 🏠
        "pintura", "carpintero", "plomero", "electricista", "vidrio",
        "cerradura", "puerta", "ventana", "muebles", "mueble", "cortinas",
        "alfombra", "lampara", "lámpara", "decoracion", "decoración",
        "reforma", "arreglo", "reparacion", "reparación", "mantenimiento",
        "limpieza hogar", "pintor", "albanil", "albañil", "herramientas",
        "construccion", "construcción", "depto", "departamento",
        "inmueble", "propiedad", "garantia", "garantía",
    ],
    11: [  # Mascotas 🐾
        "perro", "gato", "mascota", "veterinario", "vet", "veterinaria",
        "croquetas", "alimento perro", "alimento gato", "collar", "correa",
        "transportin", "transportín", "vacuna", "desparasitante",
        "peluqueria mascota", "baño mascota", "antiparasitario",
        "grooming", "accesorios mascota", "mascotera", "mascoteria",
    ],
    12: [  # Viajes ✈️
        "vuelo", "avion", "avión", "pasaje", "aereo", "aéreo", "hotel",
        "alojamiento", "hospedaje", "airbnb", "booking", "hostel",
        "motel", "excursion", "excursión", "turismo", "tour",
        "museo", "playa", "montana", "montaña", "camping", "cabana",
        "cabaña", "resort", "estancia", "albergue", "vacaciones",
        "destino", "pasaje aereo",
    ],
    13: [  # Seguros & Impuestos 🛡️
        "seguro", "poliza", "póliza", "iibb", "ingresos brutos",
        "ganancias", "iva", "afip", "abl", "inmobiliario", "tenencia",
        "seguro auto", "seguro vivienda", "seguro salud", "seguro vida",
        "responsabilidad civil", "contribuyente",
    ],
    14: [  # Inversiones 💰
        "inversion", "inversión", "acciones", "bolsa", "crypto",
        "bitcoin", "ethereum", "plazo fijo", "fondo mutuo", "fci",
        "compra dolares", "compra dólares", "dolar", "dólar", "blue",
        "mep", "ccl", "bonos", "cedear", "merval", "broker",
        "cotizacion", "cotización", "divisa", "cambio",
        "operacion financiera", "aporte fondo", "rescate fondo",
    ],
    15: [  # Compras Online 💳
        "amazon", "mercado libre", "mercadolibre", "meli", "shop",
        "tienda online", "e-commerce", "envio", "envío", "paquete",
        "encomienda", "dhl", "correo argentino", "andreani",
        "seguimiento pedido", "devolucion", "devolución",
    ],
    18: [  # Suscripciones 📱
        "google", "apple", "claude", "openai", "chatgpt", "copilot",
        "spotify", "netflix", "disney", "hulu", "hbo", "max", "paramount",
        "youtube", "prime", "amazon prime", "crunchyroll", "twitch",
        "dropbox", "icloud", "drive", "onedrive", "mega",
        "microsoft", "office", "adobe", "canva", "figma", "notion",
        "slack", "zoom", "github", "gitlab", "vercel", "heroku",
        "duolingo", "headspace", "calm", "blinkist",
        "suscripcion", "suscripción", "membresia", "membresía",
        "plan mensual", "plan anual", "renovacion", "renovación",
        "autopago", "débito automático", "debito automatico",
    ],
    16: [  # Belleza & Bienestar ✨
        "gym", "gimnasio", "gimnasia", "entrenador", "personal trainer",
        "fitness", "pilates", "yoga", "membresia", "membresía",
        "actividad fisica", "actividad física",
        "peluqueria", "peluquería", "barberia", "barbería",
        "corte de pelo", "corte pelo", "tintura", "tinte", "mechas",
        "alisado", "keratina", "keratin", "botox capilar",
        "pedicura", "manicura", "uñas", "unas", "gel uñas",
        "acrilico", "acrílico", "nail",
        "spa", "masaje", "masajista", "relajacion", "relajación",
        "depilacion", "depilación", "cera depilatoria", "rasuradora",
        "skincare", "facial", "crema", "serum", "hidratante",
        "mascarilla", "esfoliante", "tratamiento facial",
        "cosmetologia", "cosmetología", "cosmetica", "cosmética",
        "maquillaje", "maquilladora", "perfume", "desodorante",
        "jabon", "jabón", "champu", "champú", "shampoo",
        "acondicionador", "tratamiento capilar", "microblading",
        "tatuaje",
    ],
}

# ID del fallback "Otros"
OTROS_ID = 7


def categorize_from_keywords(text: str) -> int:
    text_lower = text.lower()
    for cat_id, keywords in KEYWORDS.items():
        if cat_id == OTROS_ID:
            continue
        if any(kw in text_lower for kw in keywords):
            return cat_id
    return OTROS_ID


def is_income_by_keywords(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in INCOME_KEYWORDS)


def parse_movement(text: str) -> dict | None:
    """Parsea un mensaje y extrae monto, descripción y tipo.

    Formatos aceptados:
    - "Gasté 25000 en supermercado"
    - "gaste 25.000 supermercado"
    - "25000 supermercado"
    - "Ingreso 50000 sueldo"
    - "sueldo 80000"  ← auto-detectado como ingreso
    """
    text = text.strip()
    # Normalizar separadores de miles: 25.000 → 25000
    cleaned = re.sub(r"(\d)\.(\d{3})\b", r"\1\2", text)

    patterns = [
        (r"gast[eé]\s+([\d]+(?:[.,]\d+)?)\s+(?:en\s+)?(.+)", "gasto"),
        (r"ingres[oóeé]\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso"),
        (r"cobr[eé]\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso"),
        (r"(sueldo|salario|aguinaldo|bono|honorarios)\s+([\d]+(?:[.,]\d+)?)\s*(.*)", "ingreso_kw"),
        (r"([\d]+(?:[.,]\d+)?)\s+(.+)", "gasto"),
    ]

    for pattern, tipo_base in patterns:
        match = re.search(pattern, cleaned.lower())
        if not match:
            continue

        if tipo_base == "ingreso_kw":
            keyword = match.group(1)
            raw_monto = match.group(2).replace(",", ".")
            descripcion = (match.group(3) or keyword).strip() or keyword
            tipo = "ingreso"
        else:
            raw_monto = match.group(1).replace(",", ".")
            descripcion = ((match.group(2) if match.lastindex >= 2 else "") or text).strip()
            tipo = tipo_base

        monto = float(raw_monto)
        if not descripcion:
            descripcion = text

        # Auto-promover a ingreso si la descripción contiene palabras clave de ingreso
        if tipo == "gasto" and is_income_by_keywords(descripcion):
            tipo = "ingreso"

        return {"monto": monto, "descripcion": descripcion, "tipo": tipo}

    return None
