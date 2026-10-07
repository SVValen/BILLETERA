AYUDA = (
    "💰 *Billetera — Guía rápida*\n\n"

    "📥 *Registrar un gasto:*\n"
    "  `5000 comida`\n"
    "  `gasté 3000 en nafta`\n"
    "  `15000 ropa` → te pregunta la categoría\n\n"

    "📤 *Registrar un ingreso:*\n"
    "  `sueldo 80000`\n"
    "  `ingreso 50000 freelance`\n\n"

    "💵 *En dólares* — al dólar BCRA (mayorista A 3500):\n"
    "  `100 dolares supermercado`\n"
    "  `2.49 usd spotify`\n"
    "  _Si mandás un monto de 100 o menos sin moneda, te pregunto si son dólares._\n\n"

    "🔁 *Gasto recurrente* — recordatorio mensual:\n"
    "  `40000 internet todos los 1 del mes`\n"
    "  `2.49 usd spotify todos los 15 del mes`\n\n"

    "💳 *Compra en cuotas:*\n"
    "  `150000 tele 12 cuotas`\n"
    "  `500 usd laptop 6 cuotas`\n\n"

    "🎤 *Audio* — mandá un mensaje de voz.\n\n"

    "💳 *Tarjetas de crédito:*\n"
    "  `/tarjeta_nueva` — agregar tarjeta (nombre + día de cierre)\n"
    "  `/tarjetas` — ver tus tarjetas configuradas\n"
    "  `/cierre santander 30/10` — fecha real de cierre (Santander y BBVA cierran distinto cada mes)\n"
    "  `/pagar_tarjeta` — calcula lo que corresponde pagar este mes por tarjeta (cuotas + compras en 1 pago) y registra el pago\n"
    "  _Al registrar un gasto te pregunto cómo lo pagaste._\n\n"

    "🏠 *Alquiler:*\n"
    "  `/alquiler` — alquiler, expensas, agua y gas del mes, con botones para marcar pagos\n"
    "  `descuento 28500 ducha` — descontar un arreglo del alquiler del mes\n"
    "  📄 Mandame el PDF de la liquidación de expensas y cargo expensas, agua y gas\n\n"

    "🏦 *Préstamos:*\n"
    "  `/prestamos` — ver estado del préstamo y pagar cuotas\n"
    "  `/transferencias` — clasificar transferencias del Santander (qué pagaste con cada una)\n"
    "  _Al pagar, te ofrezco adelantar cuotas (Capital × 1.25)._\n\n"

    "📋 *Otros comandos:*\n"
    "  `/presupuesto` — ver estado de tus presupuestos\n"
    "  `/presupuesto comida 20000` — fijar presupuesto mensual\n"
    "  `/editar` — editar un movimiento reciente\n"
    "  `/editar comida` — filtrar por palabra y editar\n"
    "  `/borrar` — borrar un movimiento reciente\n"
    "  `/borrar netflix` — filtrar por palabra y borrar\n"
    "  `/recurrentes` — ver tus gastos recurrentes activos\n"
    "  `/id` — tu Telegram ID (para vincular el dashboard)\n"
    "  `/ayuda` — esta guía"
)

CAT_BUTTONS = [
    (1,  "🛒 Super"),     (3,  "🍽️ Comida"),    (10, "🏠 Depto"),     (4,  "💡 Servicios"),
    (19, "🚗 Auto"),      (2,  "🚌 Transp."),   (18, "🔁 Suscrip."),  (6,  "💅 Cuidado"),
    (21, "💊 Farmacia"),  (8,  "👕 Ropa"),      (14, "💻 Tecno"),     (15, "👨‍👩‍👧 Familia"),
    (16, "🎁 Regalos"),   (5,  "🎉 Salidas"),   (9,  "📚 Educ."),     (11, "🐾 Mascotas"),
    (12, "✈️ Viajes"),    (13, "🛡️ Seguros"),   (22, "📦 Mudanza"),   (7,  "📌 Otros"),
]

_STOP_WORDS = {
    "para", "pero", "como", "este", "esta", "esos", "esas", "unos", "unas",
    "algo", "todo", "toda", "cada", "otro", "otra", "mismo", "desde", "hasta",
    "sobre", "entre", "bajo", "segun", "durante", "mediante", "cuota", "pago",
    "gasto", "compra", "oficial", "primero", "ultimo", "nuevo", "nueva",
}

CAT_NAME_MAP = {
    "super": 1, "supermercado": 1, "almacen": 1,
    "transporte": 2, "uber": 2,
    "comida": 3, "restaurante": 3, "delivery": 3,
    "servicios": 4, "internet": 4, "luz": 4,
    "salidas": 5, "entretenimiento": 5,
    "salud": 6, "cuidado": 6, "belleza": 6, "gym": 6, "gimnasio": 6,
    "otros": 7,
    "ropa": 8, "indumentaria": 8,
    "educacion": 9, "educación": 9, "cursos": 9,
    "departamento": 10, "depto": 10, "vivienda": 10, "hogar": 10, "alquiler": 10,
    "mascotas": 11, "veterinaria": 11,
    "viajes": 12, "turismo": 12,
    "seguros": 13, "impuestos": 13,
    "tecnologia": 14, "tecnología": 14, "tecno": 14,
    "familia": 15, "compras familia": 15,
    "regalos": 16, "regalo": 16,
    "suscripciones": 18, "suscripcion": 18, "suscripción": 18,
    "auto": 19, "nafta": 19,
    "farmacia": 21,
    "mudanza": 22,
}

DOLLAR_KEYWORDS = {"dolar", "dolares", "dólares", "usd", "u$s", "us$", "dólar"}
