# Contexto de Proyecto — BILLETERA
> Leer al inicio de cada sesión de trabajo y antes de ejecutar /review.

## Descripción
Aplicación de finanzas personales con interfaz principal via Telegram bot.
El usuario registra ingresos y gastos mediante comandos de chat. El dashboard
web muestra reportes, categorías, presupuestos y suscripciones.

## Stack
- Next.js (App Router, TypeScript)
- Supabase (PostgreSQL + Auth)
- Vercel (hosting)
- Telegram Bot API (interfaz principal de carga)
- Python (API del bot — `api/telegram.py`)

## Modelo de datos
- Usuarios individuales (no multi-tenant de empresas)
- Movimientos: ingreso o gasto, categoría, monto, fecha, descripción
- Categorías: con aprendizaje automático de keywords por usuario
- Recurrentes: gastos/ingresos que se repiten mensualmente
- Suscripciones: servicios con fecha de vencimiento y monto en USD
- Presupuestos: límites por categoría con alertas

## Flujos críticos
1. **Registro via Telegram**: usuario envía mensaje → bot parsea → inserta movimiento
2. **Categorización automática**: keyword matching → sugiere categoría → usuario confirma
3. **Dashboard mensual**: suma ingresos/gastos por categoría → calcula balance
4. **Conversión USD**: gastos en USD se convierten a ARS (tipo de cambio)

## Reglas de negocio invariantes
- Cada movimiento pertenece a un único usuario (aislamiento por `user_id`)
- Suscripciones con monto en USD, mostrar en ARS según cotización
- Bot debe responder en menos de 3 segundos (Telegram timeout)
- Nunca eliminar movimientos: soft delete o marcar como anulado
- El balance siempre se calcula con filtro de fecha y usuario

## Consideraciones de seguridad específicas
- Webhook de Telegram valida que el request viene de Telegram (token en URL)
- `user_id` de Telegram mapeado al `user_id` de Supabase de forma segura
- No exponer datos financieros del usuario en logs
- API Routes del dashboard verifican sesión antes de devolver datos

## Variables de entorno críticas (nunca en cliente)
- `SUPABASE_SERVICE_ROLE_KEY`
- `TELEGRAM_BOT_TOKEN`

## Reportes de revisión
`.claude/reports/review-[YYYY-MM-DD]-[HH-MM].md`
