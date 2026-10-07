# ARCHITECTURE.md — Billetera v2
> Última actualización: 2026-10-07 (reset a lo simple: planilla del mes, alquiler, dólar BCRA, Naranja)

## Endpoints (Python, `api/*.py` — Vercel Hobby: máx. 12 funciones)
- `telegram.py` — webhook → `api/bot/dispatcher.py`
- `cron.py` — diario: dólar BCRA, recordatorios de recurrentes, conceptos pendientes del alquiler
  (mes en curso y próximo), ajuste IPC. `?job=gmail_sync` → lectura de mails
- `stats.py` — GET `?mes=` (inicio), `?resource=tarjetas|planilla|metricas|categoria_prefs`;
  PUT `{resource: categoria_prefs|pagar_tarjeta}`
- `movements.py` — lista/filtros/recategorización
- `alquiler.py` — GET `?mes=`; POST `{resource: pagar|pagar_mes|descuento}`
- `prestamos.py` — GET `?resource=prestamos|prestamos_mes|prestamo_cuotas`; POST `{resource: importar_prestamo|pagar_cuota}`
- `cuotas.py`, `recurrentes.py`, `presupuestos.py` (también categorías)

## Librerías (`lib/`)
- `alquiler.py` — contrato, canon por mes, `asegurar_mes`, pagos, descuentos, `aplicar_liquidacion`, `actualizar_ajuste_ipc`
- `expensas_pdf.py` — lectura de la liquidación (pdfplumber, columnas por posición)
- `cotizacion.py` — dólar BCRA (A 3500) con caché diaria en `cotizaciones`; fallback dolarapi
- `pagos.py` — pago de resumen de tarjeta y de cuota de préstamo (bot y dashboard)
- `gmail_sync.py` + `email_parser_santander.py` + `email_parser_naranja.py`
- `parser.py` — parseo de texto y `KEYWORDS` (orden = prioridad) por id de categoría
- `tarjetas.py` (`calcular_mes_resumen`), `auth.py`, `date_utils.py`, `supabase_client.py`

## Bot (`api/bot/`)
Dispatcher: PDF → audio → respuestas pendientes (pago tarjeta, recurrente, transferencia, descuento
de alquiler) → comandos → texto libre (`handlers/movimientos._process_text`).
Handlers: movimientos, cuotas, recurrentes, tarjetas, prestamos, presupuestos, transferencias,
alquiler, expensas. Callbacks: `callbacks/movimiento_callbacks.py` (incluye `mon:` para la moneda).

## Dashboard (`app/dashboard/`)
Tabs: Inicio, **Planilla del mes** (vista Excel), Detalle mensual (tarjetas, préstamo, alquiler con
botones de pago, cuotas, recurrentes), Presupuestos, Movimientos, Categorías, Préstamos.
Todo client-side con `fetchWithAuth` (JWT de Supabase → `lib/auth.py`).

## Decisiones
- **Mes de pago como eje** (`mes_resumen`): así se arma la planilla igual que el Excel
- **Consumo ≠ pago**: la compra con tarjeta y el pago del resumen son movimientos distintos;
  el pago (`es_pago_tarjeta`) no entra en la planilla ni en el consumo
- **Pendientes generados por adelantado**: cuotas, préstamos y alquiler existen antes de pagarse
  (`pagado=false`, `estimado` cuando el monto todavía no es real)
- **Grupo por trigger** en la base para que bot, mails y dashboard no tengan que acordarse
