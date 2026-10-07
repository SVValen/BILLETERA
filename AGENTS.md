# Contexto de Proyecto — BILLETERA (v2, simple)
> Leer al inicio de cada sesión de trabajo. Trabajar directo en `main` (proyecto personal, sin ramas).

## Qué es
Finanzas personales con carga por Telegram y dashboard web. El objetivo de la v2 es ver en la app
**los mismos datos que la planilla de Excel "Balance Personal"**: una hoja por **mes de pago**, filas
agrupadas por *grupo* (Sueldo, Cuotas familia, Préstamo, Tarjeta Naranja/Santander/BBVA/MP,
Alquiler, Efectivo) con rubro, cuota X/N, moneda y débito automático, subtotales y **neto del mes**.

En octubre 2026 se borró todo lo de inversiones (portafolios, RV/RF, colchón, objetivos, resumen
semanal). La base anterior quedó copiada en el esquema `backup_v1` de Supabase.

## Stack
- Next.js (App Router, TypeScript) — dashboard
- Python / FastAPI en funciones de Vercel — bot y endpoints (`api/*.py`, un archivo = una ruta)
- Supabase (Postgres + Auth). Proyecto `BILLETERA` (ref `tuzrnadpcitcwalmtbnl`)
- Vercel (cuenta SSValen, Hobby; deploy automático al pushear a `main`) — https://billetera-gamma.vercel.app
- Telegram Bot API, Groq Whisper (audios)
- GitHub Actions: `cron-gmail-sync.yml` cada 20 min → `/api/cron?job=gmail_sync`
- Vercel Cron diario 12:00 UTC → `/api/cron`

## Modelo de datos (v2)
- `movimientos`: monto (ARS), tipo gasto|ingreso, **grupo**, categoria_id (= rubro), **mes_resumen**
  (= mes de pago, obligatorio), moneda, monto_original, tipo_cambio, cuota_nro/cuota_total/
  cuota_plan_id, prestamo_id, debito_automatico, **pagado**, **estimado**, concepto (alquiler),
  tarjeta_id, es_pago_tarjeta, estado
  - Trigger `movimientos_set_grupo`: con tarjeta → 'Tarjeta <nombre>'; con préstamo → 'Préstamo'
  - Montos negativos solo en grupo 'Alquiler' (descuentos por arreglos)
- `categorias`: rubros del Excel. IDs fijos que usa el código: 7 Otros, 17 Ingresos, 20 Pago Tarjeta, 10 Departamento
- `tarjetas` (dia_cierre: Naranja 27, MP 5; Santander/BBVA `cierre_variable`), `tarjeta_cierres` (fecha real de cierre por resumen; el cron pregunta desde el 25), `tarjeta_last4_map`, `tarjeta_pagos`
- `cuotas_plan`, `prestamos` + `prestamo_cuotas` (cronograma importado completo)
- `alquiler_contrato` + `alquiler_canon` (canon por período, estimado hasta tener IPC)
- `cotizaciones` (dólar mayorista BCRA A 3500 por día)
- `familiares` + `familia_asignaciones` (qué compra/plan le corresponde a cada familiar y cuánto por mes)
- `recurrentes`, `presupuestos`, `keywords_aprendidas`, `email_procesados`, `usuario_gmail_config`, `perfiles`

## Reglas de negocio
- `usuario_id` = Telegram ID; filtro manual en cada query (service role, sin RLS efectiva)
- Nunca borrar movimientos: `estado='anulado'`
- La planilla y los totales del mes se arman por `mes_resumen`, excluyendo `es_pago_tarjeta`
- Dólares: se guardan en pesos al **dólar BCRA** con `moneda='USD'`, `monto_original`, `tipo_cambio`
- Montos ≤ 100 sin moneda → el bot pregunta USD / pesos / miles
- Alquiler: se paga del 1 al 10, por adelantado; las expensas del mes son la **liquidación del mes
  anterior**. A cargo del inquilino: total de su fila − expensas extraordinarias. Agua y gas van aparte
- Ajuste del alquiler cada 4 meses por IPC (primer ajuste: diciembre 2026). Criterio: variación del
  IPC de los 4 meses anteriores ya publicados (dic → IPC oct / IPC jun)
- Sueldo UTN: lo calcula la tarea programada "Sueldo UTN desde planilla FAGDUT" (no es código del repo)

## Bot (Telegram)
| Texto / comando | Acción |
|---|---|
| `5000 comida`, `sueldo 80000` | Gasto / ingreso (pregunta medio de pago si hay tarjetas) |
| `20 claude`, `100 usd x` | ≤ 100 pregunta moneda; con "usd" convierte al dólar BCRA |
| `150000 tele 12 cuotas`, `cuota 2/3 …` | Compra en cuotas |
| `40000 internet todos los 1` | Recurrente |
| `/alquiler [YYYY-MM]` | Alquiler, expensas, agua, gas y descuentos del mes, con botones de pago |
| `descuento 28500 ducha` | Descuento del alquiler del mes |
| PDF de expensas | Lee la fila del inquilino y carga expensas/agua/gas |
| `/tarjetas`, `/tarjeta_nueva`, `/pagar_tarjeta` | Tarjetas y pago de resumen |
| `/cierre santander 30/10` | Fecha real de cierre (tarjetas de cierre variable) |
| `/prestamos` | Cuotas de préstamo |
| `/presupuesto`, `/recurrentes`, `/editar`, `/borrar`, `/id`, `/ayuda` | Utilidades |

## Mails (Gmail IMAP)
Santander (`lib/email_parser_santander.py`) y Naranja X (`lib/email_parser_naranja.py`).

## Variables de entorno (nunca en cliente)
`SUPABASE_SERVICE_ROLE_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `CRON_SECRET`, `GROQ_API_KEY`

## Migraciones
Archivos `schema_v2_*.sql`. Las migraciones desde el conector de Supabase se cancelan: correrlas en el
SQL Editor. Los `schema_*.sql` anteriores son históricos (v1).
