# Billetera — Funcionalidades

Asistente de finanzas personales: registrás gastos e ingresos por Telegram y los visualizás en un dashboard web.

---

## Bot de Telegram

### Registrar gastos

```
5000 comida
gasté 3000 en nafta
```

El bot detecta la categoría automáticamente por palabras clave.  
Si no reconoce la categoría, muestra un teclado de 16 opciones para elegir.

### Registrar ingresos

```
sueldo 80000
ingreso 50000 freelance
cobré 30000 diseño
```

Las palabras de ingreso (sueldo, salario, cobré, honorarios, aguinaldo, bono, etc.) se detectan automáticamente y se asignan a la categoría Ingresos.

### Dólares

```
100 dolares supermercado
gasté 50 usd en ropa
```

Convierte automáticamente al tipo de cambio oficial del día (dolarapi.com). La descripción queda registrada con el detalle: `supermercado (USD 100 @ $1.250 oficial)`.

### Audios de voz

Mandás un mensaje de voz y el bot transcribe con Groq Whisper (español) y registra el movimiento igual que si fuera texto.

### Confirmación de monto bajo

Si el monto registrado es menor a $1.000 (ej: decís "80" queriendo decir "80.000"), el bot pregunta:

> ¿Eran $80 o $80.000?

Con dos botones para confirmar.

### Gastos recurrentes

```
40000 internet todos los 1 del mes
luz 8500 todos los 15
```

El bot guarda el recordatorio. Cada mes en esa fecha, te manda un mensaje preguntando si querés registrarlo:

> 🔁 Recordatorio del 1ro del mes: **internet** — $40.000  
> [✓ Sí, registrar] [✗ No hoy]

Ver todos tus recurrentes con `/recurrentes`.

### Compras en cuotas

```
15000 zapatillas 12 cuotas
180000 tele en 6 cuotas
```

El bot pregunta cuándo se paga la primera cuota (este mes o el próximo). Luego crea los N movimientos con fechas escalonadas mes a mes. Aparecen en el dashboard cada mes automáticamente.

### Comandos

| Comando | Descripción |
|---|---|
| `/id` | Muestra tu Telegram ID (para vincular con el dashboard) |
| `/recurrentes` | Lista tus gastos recurrentes activos |
| `/ayuda` o `/start` | Muestra la guía de uso |

---

## Dashboard Web

### Acceso

Login con magic link por email (Supabase Auth). Al ingresar la primera vez, vinculás tu cuenta con tu Telegram ID en la página de Configuración.

### Tarjetas resumen

Tres tarjetas con totales del mes seleccionado:
- **Gastos** (rojo)
- **Ingresos** (verde)
- **Saldo** (rojo o verde según resultado)

### Gráficos

- **Torta por categoría** — distribución de gastos del mes
- **Barras comparativas** — Gastos vs. Ingresos del mes

### Tabla de movimientos

Lista todos los movimientos del mes con fecha, descripción, categoría, origen y monto. Scroll horizontal en mobile.

### Filtro por mes

Selector de mes en el header para navegar a cualquier período histórico.

### Multi-usuario

Cada usuario ve únicamente sus propios movimientos. La vinculación Supabase ↔ Telegram aísla los datos por cuenta.

---

## Categorías automáticas

| # | Categoría | Palabras clave (ejemplos) |
|---|---|---|
| 1 | 🛒 Supermercado | super, carrefour, coto, verdulería, almacén |
| 2 | 🚗 Transporte | uber, taxi, sube, nafta, colectivo, peaje |
| 3 | 🍽️ Comida | resto, delivery, pedidosya, café, pizza, comida |
| 4 | 💡 Servicios | luz, gas, internet, movistar, expensas, alquiler |
| 5 | 🎬 Entretenimiento | netflix, spotify, cine, steam, recital |
| 6 | 🏥 Salud | farmacia, médico, dentista, psicólogo, análisis |
| 7 | 📌 Otros | fallback (pregunta categoría si monto ≥ $1.000) |
| 8 | 👕 Ropa | zapatillas, remera, campera, shopping |
| 9 | 📚 Educación | curso, universidad, udemy, clases, taller |
| 10 | 🏠 Vivienda | plomero, muebles, pintura, reforma |
| 11 | 🐾 Mascotas | veterinario, croquetas, perro, gato |
| 12 | ✈️ Viajes | vuelo, hotel, airbnb, excursión, pasaje |
| 13 | 🛡️ Seguros | seguro, póliza, AFIP, IIBB, ABL |
| 14 | 💰 Inversiones | acciones, crypto, plazo fijo, bonos, dólar |
| 15 | 💳 Compras Online | mercadolibre, amazon, andreani, envío |
| 16 | ✨ Belleza | gym, peluquería, uñas, spa, masaje, skincare |
| 17 | 💵 Ingresos | sueldo, salario, aguinaldo, cobré, honorarios |

---

## Stack técnico

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16 (App Router) |
| Backend | FastAPI (Python serverless en Vercel) |
| Base de datos | Supabase PostgreSQL |
| Auth | Supabase Auth (magic link) |
| Bot | Telegram Bot API (webhook) |
| Voz | Groq Whisper (`whisper-large-v3-turbo`) |
| Dólar | dolarapi.com (gratuito, sin auth) |
| Gráficos | Recharts v3 |
| Deploy | Vercel |
