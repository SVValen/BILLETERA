import re

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
