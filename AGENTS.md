# Contexto de Proyecto — BILLETERA
> Leer al inicio de cada sesión de trabajo y antes de ejecutar /review.

## Descripción
Aplicación de finanzas personales con interfaz principal via Telegram bot.
El usuario registra ingresos, gastos e inversiones mediante comandos de chat.
El dashboard web muestra reportes, categorías, presupuestos, suscripciones e inversiones.

## Stack
- Next.js (App Router, TypeScript)
- Supabase (PostgreSQL + Auth)
- Vercel (hosting)
- Telegram Bot API (interfaz principal de carga)
- Python / FastAPI (API del bot — `api/telegram.py` y endpoints)
- Anthropic Claude API (análisis de inversiones — Haiku)
- GitHub Actions (crons de inversiones — Vercel Free solo permite 1 cron/día)

## Modelo de datos
- Usuarios individuales (no multi-tenant de empresas)
- Movimientos: ingreso o gasto, categoría, monto, fecha, descripción
- Categorías: con aprendizaje automático de keywords por usuario
- Recurrentes: gastos/ingresos que se repiten mensualmente
- Suscripciones: servicios con fecha de vencimiento y monto en USD
- Presupuestos: límites por categoría con alertas
- Perfiles de inversión: perfil de riesgo, capital en USD, objetivos, moneda preferida, % asignación RF
- Activos (renta variable): crypto via CoinGecko, CEDEARs/acciones via IOL; con RSI, EMA, tendencia
- Usuario_activos: qué activos monitorea cada usuario, con porcentaje y monto
- Recomendaciones: señales RV generadas por el cron con acción/confianza/razón
- Instrumentos RF: cauciones, letras, bonos soberanos, ONs con TNA y precios IOL
- Posiciones RF: posiciones abiertas del usuario con monto ARS, equivalente USD, TNA contratada

## Flujos críticos
1. **Registro via Telegram**: usuario envía mensaje → bot parsea → inserta movimiento
2. **Categorización automática**: keyword matching → sugiere categoría → usuario confirma
3. **Dashboard mensual**: suma ingresos/gastos por categoría → calcula balance
4. **Conversión USD**: gastos en USD se convierten a ARS (tipo de cambio oficial)
5. **Wizard de inversiones**: onboarding guiado → objetivos → plazo → moneda → capital (USD) → % RF → descripción → activos → portafolio
6. **Cron RV (cada ~30 min)**: actualiza precios + RSI/EMA → genera recomendaciones si hay señal
7. **Cron RF (L-V 12:00 AR)**: actualiza TNA/precios RF → evalúa carry trade → alerta vencimientos → sugiere rotación RF↔RV

## Reglas de negocio invariantes
- Cada movimiento pertenece a un único usuario (aislamiento por `user_id`)
- Suscripciones con monto en USD, mostrar en ARS según cotización
- Bot debe responder en menos de 3 segundos (Telegram timeout)
- Nunca eliminar movimientos: soft delete o marcar como anulado
- El balance siempre se calcula con filtro de fecha y usuario
- Capital de inversión se maneja en USD; conversión a ARS al tipo MEP para instrumentos ARS
- Carry trade: TNA/12 > devaluación MEP mensual → conviene estar en ARS; caso contrario → USD

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
