AYUDA = (
    "💰 *Billetera — Guía rápida*\n\n"

    "📥 *Registrar un gasto:*\n"
    "  `5000 comida`\n"
    "  `gasté 3000 en nafta`\n"
    "  `15000 ropa` → te pregunta la categoría\n\n"

    "📤 *Registrar un ingreso:*\n"
    "  `sueldo 80000`\n"
    "  `ingreso 50000 freelance`\n\n"

    "💵 *En dólares* — convertidos al oficial:\n"
    "  `100 dolares supermercado`\n"
    "  `2.49 usd spotify`\n\n"

    "🔁 *Gasto recurrente* — recordatorio mensual:\n"
    "  `40000 internet todos los 1 del mes`\n"
    "  `2.49 usd spotify todos los 15 del mes`\n\n"

    "💳 *Compra en cuotas:*\n"
    "  `150000 tele 12 cuotas`\n"
    "  `500 usd laptop 6 cuotas`\n\n"

    "🎤 *Audio* — mandá un mensaje de voz.\n\n"

    "📊 *Inversiones — Renta Variable:*\n"
    "  `/inversiones` — configurar perfil / ver recomendaciones\n"
    "  `/inversiones reset` — reiniciar el wizard de configuración\n"
    "  `/portafolio` — distribución de activos y P&L\n"
    "  `/precios` — cotizaciones en tiempo real\n"
    "  `/como_funciona` — cómo se calculan las señales\n\n"

    "💼 *Renta Fija y Liquidez:*\n"
    "  `/liquidez` — carry trade, posiciones abiertas, P&L en USD\n"
    "  `puse 500000 en caución 7 días` — registrar posición\n"
    "  `AL30 200000` — registrar bono\n"
    "  `lecap 300000 S28F6` — registrar letra\n\n"

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
    (1,  "🛒 Super"),    (3,  "🍽️ Comida"),  (2,  "🚗 Trans."),  (4,  "💡 Servicios"),
    (5,  "🎬 Entret."),  (6,  "🏥 Salud"),   (8,  "👕 Ropa"),    (10, "🏠 Vivienda"),
    (9,  "📚 Educ."),    (11, "🐾 Mascotas"), (12, "✈️ Viajes"),  (13, "🛡️ Seguros"),
    (14, "💰 Invers."),  (15, "💳 Compras"),  (16, "✨ Belleza"), (18, "📱 Suscripc."),
    (7,  "📌 Otros"),
]

_STOP_WORDS = {
    "para", "pero", "como", "este", "esta", "esos", "esas", "unos", "unas",
    "algo", "todo", "toda", "cada", "otro", "otra", "mismo", "desde", "hasta",
    "sobre", "entre", "bajo", "segun", "durante", "mediante", "cuota", "pago",
    "gasto", "compra", "oficial", "primero", "ultimo", "nuevo", "nueva",
}

CAT_NAME_MAP = {
    "super": 1, "supermercado": 1, "almacen": 1,
    "transporte": 2, "nafta": 2, "uber": 2,
    "comida": 3, "restaurante": 3, "delivery": 3,
    "servicios": 4, "internet": 4, "luz": 4, "gas": 4,
    "entretenimiento": 5, "entret": 5, "netflix": 5,
    "salud": 6, "farmacia": 6, "medico": 6,
    "otros": 7,
    "ropa": 8, "indumentaria": 8,
    "educacion": 9, "educación": 9, "cursos": 9,
    "vivienda": 10, "hogar": 10,
    "mascotas": 11, "veterinaria": 11,
    "viajes": 12, "turismo": 12,
    "seguros": 13, "impuestos": 13,
    "inversiones": 14, "ahorro": 14,
    "compras": 15, "online": 15,
    "belleza": 16, "gym": 16, "gimnasio": 16,
    "suscripciones": 18, "suscripcion": 18, "suscripción": 18,
}

DOLLAR_KEYWORDS = {"dolar", "dolares", "dólares", "usd", "u$s", "us$", "dólar"}
