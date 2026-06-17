# Billetera — Funcionalidades

Asistente de finanzas personales: registrás gastos, ingresos e inversiones por Telegram y los visualizás en un dashboard web.

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

Las palabras de ingreso (sueldo, salario, cobré, honorarios, aguinaldo, bono, etc.) se detectan automáticamente.

### Dólares

```
100 dolares supermercado
gasté 50 usd en ropa
```

Convierte automáticamente al tipo de cambio oficial del día (dolarapi.com). La descripción queda con el detalle: `supermercado (USD 100 @ $1.450 oficial)`.

### Audios de voz

Mandás un mensaje de voz y el bot transcribe con Groq Whisper (español) y registra igual que si fuera texto.

### Confirmación de monto bajo

Si el monto es menor a $1.000 (ej: decís "80" queriendo decir "80.000"), el bot pregunta:

> ¿Eran $80 o $80.000?

### Gastos recurrentes

```
40000 internet todos los 1 del mes
luz 8500 todos los 15
```

Cada mes en esa fecha, el bot te manda un recordatorio con botones para confirmar o saltar.

Ver todos tus recurrentes con `/recurrentes`.

### Compras en cuotas

```
15000 zapatillas 12 cuotas
180000 tele en 6 cuotas
```

El bot crea los N movimientos con fechas escalonadas mes a mes. Aparecen en el dashboard cada mes automáticamente.

---

## Módulo de Inversiones — Renta Variable

### Configuración (wizard)

`/inversiones` inicia el wizard si no tenés perfil:

1. **Objetivos** — ingresos pasivos, crecimiento, cobertura inflación, meta específica
2. **Plazo** — corto (< 1 año), mediano (1-3 años), largo (+ 3 años)
3. **Moneda preferida** — Pesos (ARS), Dólares (USD), Ambas
4. **Capital** — cuánto tenés en USD para invertir
5. **% Renta Fija** — qué % querés mantener en liquidez (cauciones/letras)
6. **Descripción libre** — contexto adicional (también acepta audio)
7. **Selección de activos** — Claude sugiere activos según tu perfil; podés modificar
8. **Distribución del portafolio** — escribís "40% BTC, 60% AAPL" o "vos decidí"

### Activos disponibles (renta variable)

| Activo | Tipo | Fuente |
|---|---|---|
| BTC — Bitcoin | Crypto | CoinGecko |
| ETH — Ethereum | Crypto | CoinGecko |
| AAPL — Apple (CEDEAR) | CEDEAR | IOL |
| GOOGL — Google (CEDEAR) | CEDEAR | IOL |
| MSFT — Microsoft (CEDEAR) | CEDEAR | IOL |
| GGAL — Grupo Galicia | Acción AR | IOL |
| YPF (YPFD) | Acción AR | IOL |
| USDT — Dólar cripto | Dólar | dolarapi |

### Recomendaciones automáticas

El cron (cada ~30 min via GitHub Actions) calcula RSI y EMA sobre los últimos precios:
- **RSI < 35** → sobreventa → posible señal de compra
- **RSI > 65** → sobrecompra → posible señal de venta
- Claude Haiku analiza el contexto (perfil, objetivos, winrate) y genera una recomendación con acción + razón + confianza (1-10)
- Se envía por Telegram con botones ✅ Aceptar / ❌ Rechazar
- No genera spam: si ya hay una recomendación pendiente para ese activo, no genera otra

### Comandos de inversiones (RV)

| Comando | Descripción |
|---|---|
| `/inversiones` | Resumen del perfil + recomendaciones pendientes |
| `/portafolio` | Distribución de activos, precios actuales, P&L estimado |
| `/precios` | Cotizaciones en tiempo real de tus activos + BTC/dólar |
| `/como_funciona` | Explicación del algoritmo RSI/EMA/carry trade |

---

## Módulo de Inversiones — Renta Fija y Liquidez

### Instrumentos soportados

| Tipo | Ejemplos | Moneda |
|---|---|---|
| Cauciones | 1D, 7D, 30D | ARS |
| Letras del Tesoro (Lecaps) | S28F6, S30J6, etc. | ARS |
| Bonos soberanos | AL30, GD30, AE38, GD35 | USD |
| ONs | Tickers específicos | ARS / USD |

### Carry trade automático

El cron diario (L-V 12:00 AR) calcula:

```
carry = (TNA_caución / 12) - devaluación_MEP_mensual
```

- **carry > 2%** → ENTRAR (ARS rinde más que la devaluación)
- **carry < 0%** → SALIR (conviene quedarse en USD)
- **carry 0-2%** → Claude evalúa contexto del perfil y posiciones

### Registro de posiciones

Escribís en texto libre:
```
puse 500000 en caución 7 días
lecap 300000 S28F6
AL30 200000
```

El bot confirma con un botón antes de registrar. Podés ver y rescatar posiciones desde `/liquidez`.

### Alertas automáticas (cron diario)

- **Vencimiento próximo** (≤ 3 días): avisa con P&L actual en ARS y USD
- **Carry favorable**: si tenés menos del % objetivo en RF y el carry es positivo, sugiere colocar
- **Carry desfavorable**: si el dólar sube más de lo que rinde la caución, sugiere no renovar
- **Rotación RF → RV**: si hay señal fuerte de RV (confianza ≥ 7) y tenés mucho en RF, sugiere rotar

### Comando de liquidez

| Comando | Descripción |
|---|---|
| `/liquidez` | Estado actual: carry trade, posiciones abiertas, P&L en USD, allocation RF vs RV |

---

## Dashboard Web

### Acceso

Login con magic link por email (Supabase Auth). Al ingresar la primera vez, vinculás tu cuenta con tu Telegram ID en la página de Configuración.

### Tabs

| Tab | Contenido |
|---|---|
| Resumen | Tarjetas gasto/ingreso/saldo, torta por categoría, barras mensuales, cuotas activas, recurrentes próximos |
| Movimientos | Tabla del mes con filtros; editar/borrar |
| Presupuestos | Límites por categoría vs. gasto real del mes |
| Objetivos | Objetivos de ahorro con progreso |
| Inversiones | Perfil RV, activos monitoreados con RSI/tendencia, recomendaciones pendientes, historial de decisiones |

### Endpoints del dashboard (API Python)

| Endpoint | Datos |
|---|---|
| `/api/stats?mes=&usuario=` | Gastos/ingresos por categoría |
| `/api/cuotas?usuario=` | Cuotas activas con progreso |
| `/api/recurrentes?usuario=&dias=` | Recurrentes próximos |
| `/api/presupuestos` | CRUD presupuestos |
| `/api/objetivos` | CRUD objetivos |
| `/api/movements` | Lectura/edición de movimientos |
| `/api/inversiones?resource=perfil` | Perfil de inversión |
| `/api/inversiones?resource=activos` | Activos disponibles con indicadores |
| `/api/inversiones?resource=recomendaciones` | Recomendaciones (filtrable por estado) |
| `/api/inversiones?resource=decisiones` | Decisiones con stats y winrate |
| `/api/inversiones?resource=liquidez` | Posiciones RF + carry trade + allocation |
| `/api/inversiones?resource=allocation` | Distribución total capital USD: RF vs RV |

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
| 7 | 📌 Otros | fallback si no reconoce categoría |
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
| Frontend | Next.js (App Router, TypeScript) |
| Backend | FastAPI (Python serverless en Vercel) |
| Base de datos | Supabase PostgreSQL |
| Auth | Supabase Auth (magic link) |
| Bot | Telegram Bot API (webhook) |
| Voz | Groq Whisper (`whisper-large-v3-turbo`) |
| IA inversiones | Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) |
| Precios crypto | CoinGecko API (sin auth, sin geo-block) |
| Precios acciones/bonos | IOL (Invertir Online) API (OAuth2 password grant) |
| Dólar | dolarapi.com (gratuito, sin auth) |
| Gráficos | Recharts |
| Deploy | Vercel |
| Crons inversiones | GitHub Actions (`*/30 * * * *` y `0 15 * * 1-5`) |
| Cron recurrentes | Vercel Cron (12:00 UTC diario) |
