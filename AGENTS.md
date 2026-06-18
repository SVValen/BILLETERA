# Contexto de Proyecto — BILLETERA
> Leer al inicio de cada sesión de trabajo y antes de ejecutar /review.

## Descripción
Aplicación de finanzas personales con interfaz principal via Telegram bot.
El usuario registra ingresos, gastos e inversiones mediante comandos y texto libre.
El dashboard web muestra reportes, categorías, presupuestos, suscripciones e inversiones.

## Stack
- Next.js (App Router, TypeScript)
- Supabase (PostgreSQL + Auth)
- Vercel (hosting)
- Telegram Bot API (interfaz principal de carga)
- Python / FastAPI (API del bot — módulos bajo `api/bot/`)
- Anthropic Claude API (análisis de inversiones — Haiku)
- GitHub Actions (crons de inversiones — Vercel Free solo permite 1 cron/día)

## Modelo de datos
- Usuarios individuales (no multi-tenant de empresas)
- Movimientos: ingreso o gasto, categoría, monto, fecha, descripción
- Categorías: con aprendizaje automático de keywords por usuario
- Recurrentes: gastos/ingresos que se repiten mensualmente
- Suscripciones: servicios con fecha de vencimiento y monto en USD
- Presupuestos: límites por categoría con alertas
- Portafolios: tipo + capital (USD y/o ARS) + % asignación RF + estado_wizard
- Aportes: historial de aportes de capital por portafolio con tipo de cambio MEP
- Portafolio_activos: activos RV asignados a cada portafolio con % y monto objetivo
- Activos (renta variable): crypto via CoinGecko, CEDEARs/acciones via IOL; con RSI, EMA, tendencia
- Recomendaciones: señales RV generadas por el cron con acción/confianza/razón
- Decisiones_inversion: respuestas del usuario (aceptar/rechazar) con seguimiento de resultado
- Instrumentos RF: cauciones, letras, bonos soberanos, ONs con TNA y precios IOL
- Posiciones RF: posiciones abiertas con monto ARS, equivalente USD en entrada, TNA contratada

## Comandos del bot (Telegram)

### Finanzas personales
| Comando / Texto | Acción |
|---|---|
| `5000 comida` / `gasté 3000 nafta` | Registrar gasto |
| `sueldo 80000` / `ingreso 50000 freelance` | Registrar ingreso |
| `100 dolares supermercado` | Gasto en USD (convierte al oficial) |
| `40000 internet todos los 1 del mes` | Configurar recurrente mensual |
| `150000 tele 12 cuotas` / `cuota 2/3 ...` | Cuotas (inicio o en progreso) |
| `/editar [query]` | Editar movimiento reciente |
| `/borrar [query]` | Borrar (anular) movimiento reciente |
| `/presupuesto` | Ver estado de presupuestos |
| `/presupuesto comida 20000` | Fijar presupuesto mensual |
| `/recurrentes` | Ver gastos recurrentes activos |

### Portafolios e inversiones
| Comando / Texto | Acción |
|---|---|
| `/portafolio_nuevo` | Wizard guiado para crear portafolio |
| `/mis_portafolios` | Ver portafolios activos con capital (USD + ARS) |
| `/activos` | Elegir qué activos RV monitorear (toggles ✅/⬜ por portafolio) |
| `/inversiones` | Señales RV pendientes + carry trade + opciones RF |
| `/inversiones reset` | Cancelar wizard de portafolio en progreso |
| `/portafolio` | Distribución de activos RV y P&L del portafolio |
| `/precios` | Cotizaciones en tiempo real (crypto + dólar + activos) |
| `/como_funciona` | Explicación de señales RSI/EMA |
| `sumé 500 USD al conservador` | Aporte de capital USD a portafolio |
| `agregué 200000 pesos` | Aporte de capital ARS a portafolio |
| `deposité 1000 USD` | Aporte (heurística: >50k sin moneda → ARS) |

### Renta fija
| Comando / Texto | Acción |
|---|---|
| `/opciones_rf` | Instrumentos disponibles con botones para registrar posición |
| `/liquidez` | Carry trade + posiciones abiertas + P&L en USD |
| `puse 500000 en caución 7 días` | Registrar posición RF directamente |
| `AL30 200000` | Registrar bono soberano |
| `lecap 300000 S28F6` | Registrar letra |

### Utilidades
| Comando | Acción |
|---|---|
| `/ayuda` / `/start` | Guía rápida |
| `/id` | Telegram ID para vincular con el dashboard |
| `/iol_debug TICKER` | Debug de datos de mercado IOL |

## Flujos críticos
1. **Registro de gasto/ingreso**: usuario envía texto → parser detecta monto+descripción → categorización automática → inserta movimiento
2. **Categorización automática**: keyword matching (hardcoded + aprendidas por usuario) → sugiere categoría → usuario confirma con botón
3. **Dashboard mensual**: suma ingresos/gastos por categoría con filtro de mes
4. **Conversión USD**: gastos en USD se convierten a ARS (tipo de cambio oficial); descripción queda con `(USD X @ $Y oficial)`
5. **Wizard de portafolio**: `/portafolio_nuevo` → tipo → objetivo → plazo/renta → capital → % RF (0-100% libre, ✨ = recomendado) → nombre → activo. Al activar: si RF% > 0 sugiere instrumentos RF; si RV% > 0 sugiere activos RV con toggles (Claude elige 2-4 según perfil, pre-seleccionados en `portafolio_activos`).
6. **Aporte de capital**: `sumé X USD/ARS` → detecta portafolio destino (por hint o botones si múltiple) → confirma → actualiza `capital_usd` o `capital_ars` → guarda en `aportes_portafolio` → sugiere instrumentos RF para la parte RF del aporte
9a. **Selección de activos RV** (`/activos`): muestra todos los activos disponibles con toggles; cada tap inserta/elimina directo en `portafolio_activos`; el cron empieza a monitorear inmediatamente.
7. **Registro RF con botones**: `/opciones_rf` o sugerencia post-wizard/post-aporte → botón instrumento → opciones de monto (25/50/75/100% del capital RF) → confirmar → inserta en `posiciones_rf`
8. **Cron RV (cada ~30 min)**: actualiza precios + RSI/EMA → genera recomendaciones si hay señal → envía por Telegram con botones [Aceptar][Rechazar]
9. **Cron RF (L-V 15:00 UTC)**: actualiza TNA/precios RF → evalúa carry trade → alerta vencimientos → sugiere rotación RF↔RV

## Reglas de negocio invariantes
- Cada movimiento / posición / portafolio pertenece a un único usuario (filtro manual por `usuario_id`)
- Bot debe responder en menos de 3 segundos (Telegram timeout)
- Nunca eliminar movimientos: marcar como `estado='anulado'`
- El balance siempre se calcula con filtro de fecha y usuario
- Capital en `portafolios`: `capital_usd` (USD) y `capital_ars` (ARS) separados; para allocation se suman convertidos al MEP
- Posiciones RF: `monto_usd_entrada` es NOT NULL — requiere dólar MEP disponible al registrar
- `posiciones_rf.estado`: solo `abierta | cerrada | vencida` (no `activa` ni `rescatada`)
- `portafolios.tipo`: solo `conservador | pasivo | crecimiento | oportunista` (CHECK constraint)
- Aportes registran tipo de cambio MEP del momento para trazabilidad
- Carry trade: TNA/12 > devaluación MEP mensual → conviene ARS; caso contrario → USD
- El cron RV solo genera señales para activos en `portafolio_activos`; sin filas → 0 señales RV
- Activos disponibles para monitoreo: BTC, ETH, AAPL, GOOGL, MSFT, GGAL, YPFD (excluye tipo `dolar`)

## Consideraciones de seguridad específicas
- Webhook de Telegram valida que el request viene de Telegram (token en URL)
- `user_id` de Telegram mapeado al `user_id` de Supabase de forma segura
- No exponer datos financieros del usuario en logs
- API Routes del dashboard verifican sesión antes de devolver datos
- `CRON_SECRET` requerido en cron RF (siempre); cron RV también lo verifica

## Variables de entorno críticas (nunca en cliente)
- `SUPABASE_SERVICE_ROLE_KEY`
- `TELEGRAM_BOT_TOKEN`
- `ANTHROPIC_API_KEY`
- `IOL_USER` / `IOL_PASSWORD`
- `CRON_SECRET`

## Reportes de revisión
`.claude/reports/review-[YYYY-MM-DD]-[HH-MM].md`
