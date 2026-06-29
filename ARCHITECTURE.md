# ARCHITECTURE.md — Billetera
> Snapshot técnico. Actualizar con /snapshot --update tras cambios significativos.
> Última actualización: 2026-06-29 (Fase 6b — préstamos, pago de resumen de tarjeta)

## Archivos clave

### Autenticación (Next.js)
- `app/login/page.tsx` — login via magic link (OTP de Supabase); Client Component
- `app/auth/callback/route.ts` — intercambia `code` de OAuth por sesión y redirige a `/dashboard`
- `app/configurar/page.tsx` — paso obligatorio post-login: vincula `user.id` con `telegram_id`
- `lib/supabase-server.ts` — `createSupabaseServer()`: cliente para Server Components / Route Handlers
- `lib/supabase-browser.ts` — `createSupabaseBrowser()`: cliente para Client Components

### Dashboard (Next.js)
- `app/dashboard/page.tsx` — shell: auth check, selector de mes, dark mode, delega a tabs
- `app/dashboard/ResumenTab.tsx` — tarjetas gasto/ingreso/saldo, PieChart donut + BarChart, cuotas (con `?mes=`), recurrentes
- `app/dashboard/PresupuestosTab.tsx` — presupuestos por categoría vs. gasto real del mes
- `app/dashboard/MovimientosTab.tsx` — tabla de movimientos con filtros; editar/borrar
- `app/dashboard/ObjetivosTab.tsx` — objetivos de ahorro
- `app/dashboard/InversionesTab.tsx` — portafolios, activos RV monitoreados, recomendaciones pendientes, historial decisiones

### Bot Telegram (Python / FastAPI) — módulo `api/bot/`
- `api/telegram.py` — webhook principal: delega a `dispatcher.py`
- `api/bot/dispatcher.py` — enruta mensajes y callbacks; detecta texto libre (aportes, RF, movimientos)
- `api/bot/constants.py` — `AYUDA`, `CAT_BUTTONS`, keywords de categorías
- `api/bot/tg.py` — helpers `_send`, `_edit_message`, `_answer_callback`, `_transcribe_voice`, `_get_dolar_oficial`
- `api/bot/handlers/movimientos.py` — `_process_text`: parser principal de gastos/ingresos
- `api/bot/handlers/wizard_inversion.py` — wizard de creación de portafolio + `_sugerir_instrumentos_rf()`
- `api/bot/handlers/aportes.py` — detección y confirmación de aportes de capital (USD/ARS); sugiere RF post-aporte
- `api/bot/handlers/posiciones_rf.py` — parser de texto RF + callbacks `rf_elegir` / `rf_monto` / `rf_confirmar` / `rf_rescatar`
- `api/bot/handlers/activos_rv.py` — `sugerir_activos_rv()`, `handle_activos_cmd()`, `handle_rv_callback()`: selección de activos RV con toggles ✅/⬜; callbacks `rv_toggle`, `rv_confirmar`, `rv_sel_port`
- `api/bot/handlers/tarjetas.py` — `/tarjeta_nueva` (wizard botones nombre→día_cierre), `/tarjetas`, `pago_keyboard()`, `cuota_tarjeta_keyboard()`, `get_tarjetas_activas()`; callbacks `tnueva_nom`, `tnueva_cie`. También `/pagar_tarjeta`: `handle_pagar_tarjeta_cmd()`, `handle_pagar_tarjeta_callback()` (`pagtar_confirmar`, `pagtar_editar`), `handle_pagar_tarjeta_text()`, `_calcular_total_tarjeta()`, `_registrar_pago_tarjeta()`
- `api/bot/handlers/colchon.py` — `/colchon_nuevo`, `/colchon` (status + sugerencia Claude), `handle_colchon_text()` (captura monto de tope), `handle_colchon_callback()`; callbacks `colchon_aceptar`, `colchon_set`, `colchon_ajustar`, `colchon_dejar`, `colchon_invest`
- `api/bot/handlers/comandos_inversion.py` — `/inversiones`, `/portafolio`, `/liquidez`, `/precios`, `/opciones_rf`
- `api/bot/handlers/plan_renta.py` — wizard legado `/plan_renta` (simplificado; usa `tipo='conservador'` con estados propios)
- `api/bot/handlers/cuotas.py` — cuotas con progreso (`cuota X/N`), `cuota_inicio`
- `api/bot/handlers/presupuestos.py` — CRUD de presupuestos via bot
- `api/bot/callbacks/movimiento_callbacks.py` — callbacks editar/borrar/categorizar/recurrentes/cuotas
- `api/bot/callbacks/recomendacion_callbacks.py` — callbacks `inv_ok` / `inv_no` para señales RV
- `api/bot/middleware_portafolio.py` — `resolver_portafolio()`: si hay 1 portafolio activo lo retorna; si hay varios, muestra selector con botones

### Crons
- `api/cron.py` — diario (12:00 UTC via Vercel Cron): recurrentes del día + resumen semanal
- `api/cron_inversiones.py` — cada ~30 min (GitHub Actions): precios + RSI/EMA + recomendaciones RV
- `api/cron_rf.py` — L-V 15:00 UTC (GitHub Actions): TNA/precios RF + carry trade + alertas vencimientos

### Endpoints del dashboard
- `api/stats.py` — `GET /api/stats?mes=YYYY-MM`: gastos/ingresos por categoría. `GET ?resource=tarjetas`: total a pagar por tarjeta del mes (cuotas + 1 pago) y estado de pago
- `api/cuotas.py` — `GET /api/cuotas?mes=YYYY-MM`: cuotas activas con progreso (respeta `cuota_inicio`)
- `api/recurrentes.py` — `GET /api/recurrentes?dias=N`: próximos recurrentes
- `api/presupuestos.py` — CRUD de presupuestos
- `api/objetivos.py` — CRUD de objetivos de ahorro
- `api/movements.py` — lectura/edición de movimientos; incluye `tarjeta_id`/`tarjetas(nombre)`/`forma_pago` (derivado: "Pago resumen" / "Cuota X/N" / "1 pago" / "—")
- `api/inversiones.py` — `GET ?resource=portafolios|perfil|activos|recomendaciones|decisiones|liquidez|allocation|instrumentos_rf`

### Librerías Python
- `lib/parser.py` — `parse_movement()`, `categorize_from_keywords()`, `parse_recurrente()`, `parse_cuotas()`, `parse_cuota_progreso()`, `parse_aporte()`
- `lib/supabase_client.py` — singleton `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY`
- `lib/market_data.py` — fetchers: CoinGecko (crypto), IOL (CEDEARs/bonos/letras), dolarapi (oficial/MEP/blue), `fetch_caucion_tna()`, `fetch_iol_rf()`, `fetch_precio_activo()`
- `lib/indicators.py` — `calcular_rsi()`, `calcular_ema()`, `detectar_tendencia()`, `tiene_senal()`, `interpretar_rsi()`
- `lib/claude_invest.py` — `generar_recomendacion()`, `sugerir_activos_para_perfil()`, `sugerir_portafolio()`, `responder_pregunta_activos()`, `analizar_oportunidad_rf()`, `formatear_mensaje_telegram()`
- `lib/rf_analysis.py` — `analizar_carry_trade()`, `evaluar_vencimientos()`, `calcular_rendimiento_usd()`, `calcular_allocation()`
- `lib/tarjetas.py` — `calcular_mes_resumen(fecha_compra, dia_cierre)`, `mes_siguiente()`, `mes_label()`
- `lib/auth.py` — `get_telegram_id_from_request()`: extrae telegram_id desde sesión Supabase

### GitHub Actions
- `.github/workflows/cron-inversiones.yml` — cada 30 min: llama `/api/cron_inversiones`
- `.github/workflows/cron-outcomes.yml` — diario 03:00 UTC: llama `/api/cron_inversiones/outcomes`
- `.github/workflows/cron-rf.yml` — L-V 15:00 UTC: llama `/api/cron_rf`

### Schema SQL (orden de aplicación)
1. `schema.sql` — base: `movimientos`, `categorias`
2. `schema_phase2.sql` / `schema_*.sql` — ingresos, recurrentes, suscripciones, cuotas, presupuestos
3. `schema_rls_policies.sql` — políticas RLS (permisivas en tablas de inversión — deuda técnica)
4. `schema_portafolios.sql` — módulo portafolios: `portafolios`, `portafolio_activos`, `posiciones_rf`, `recomendaciones`, `decisiones_inversion`
5. `schema_rf.sql` — `instrumentos_rf` (catálogo global)
6. `schema_migration_20260616.sql` — `moneda_preferida`, fix YPF→YPFD
7. `schema_migration_rf.sql` — `capital_usd`, `asignacion_rf_pct`, seed instrumentos RF
8. `schema_migration_rf_fix.sql` — fixes columnas RF
9. `schema_migration_portafolios_v2.sql` — ajustes columnas portafolios
10. `schema_migration_cuota_inicio.sql` — `cuota_inicio` en `cuotas_plan` (DEFAULT 1)
11. `schema_migration_aportes.sql` — `capital_ars` en `portafolios` + tabla `aportes_portafolio`
12. `schema_migration_tarjetas.sql` — tabla `tarjetas` + columnas `tarjeta_id/fecha_compra/mes_resumen` en `movimientos` + `tarjeta_id` en `cuotas_plan` + `proposito` en `portafolios` + tabla `colchon_mensual`
13. `schema_migration_prestamos.sql` — tablas `prestamos` y `prestamo_cuotas` (Fase 6 — préstamos con adelanto de cuotas)
14. `schema_migration_pagar_tarjeta.sql` — columna `movimientos.es_pago_tarjeta`, categoría "Pago Tarjeta", tabla `tarjeta_pagos`

---

## Patrones

### Acceso a datos — Python
Todas las APIs Python usan `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY` — bypasea RLS. El aislamiento por usuario se hace **manualmente** filtrando por `usuario_id` (= Telegram ID) en cada query.

### Acceso a datos — Next.js
Las tabs del dashboard son Client Components que llaman a los endpoints Python via `fetch('/api/...')`. El cliente Supabase JS solo se usa para auth. Data fetching usa `useEffect` con cancellation token para evitar race conditions al cambiar el mes.

### Auth check en el Dashboard
Sin middleware. Verificación en cada Client Component via `useEffect`: `getUser()` → sin sesión → push `/login`; con sesión pero sin `telegram_id` → push `/configurar`.

### Routing Vercel Python
Cada archivo `api/foo.py` maneja **solo** `/api/foo`. Sub-paths devuelven 404. Para múltiples operaciones: `GET ?resource=X` y `POST {resource: "X"}`.

### Dispatcher de texto (orden de prioridad)
1. Wizard en progreso (`handle_wizard_text`) — pasos de texto del setup de portafolio
2. Plan renta en progreso (`handle_plan_renta_text`) — wizard legado
3. Aporte de capital (`parse_aporte`) — "sumé 500 USD", "agregué 200000 pesos". Requiere moneda explícita **o** hint de destino; sin ninguno → `None` (evita falso-positivo "agregué 3000 nafta")
4. Comandos `/...`
5. Parser RF (`_parse_posicion_rf`) — "puse X en caución", "AL30 X", "lecap X"
6. Parser de movimiento (`_process_text`) — fallback general

### Categorización automática
Doble capa: (1) keywords hardcodeadas en `lib/parser.py`; (2) keywords aprendidas per-usuario en `keywords_aprendidas`. Fallback: categoría "Otros" → botones inline.

### USD → ARS (movimientos)
Conversión al tipo oficial via `dolarapi.com/v1/dolares/oficial`. La descripción queda con `(USD X @ $Y oficial)` para trazabilidad.

### Capital de portafolio (doble moneda)
`portafolios.capital_usd` (USD) y `portafolios.capital_ars` (ARS) se almacenan por separado. Para calcular allocation total se convierten al MEP del momento: `total_usd = capital_usd + capital_ars / mep`. Los aportes quedan en `aportes_portafolio` con `tipo_cambio_mep` para trazabilidad.

La actualización de capital usa **concurrencia optimista**: `UPDATE WHERE capital_usd = old_value` (o `capital_ars`). Si no se modifican filas → doble-tap o retry de Telegram detectado → responder silenciosamente sin re-registrar.

### Registro de posición RF con botones
Flujo: botón instrumento (`rf_elegir:{id}`) → calcula capital RF = `(capital_usd * dolar_mep + capital_ars) * rf_pct / 100` (doble moneda) → muestra opciones 25/50/75/100% → `rf_monto:{id}:{ars}` → confirmar (`rf_confirmar:{payload_enc}`) → inserta en `posiciones_rf`. `monto_usd_entrada` se calcula al MEP, es NOT NULL. Ambos callbacks (`rf_elegir` y `rf_monto`) hacen early-exit si no hay portafolio activo.

### Sugerencia de instrumentos RF
`_sugerir_instrumentos_rf()` en `wizard_inversion.py` se llama:
- Al activar un portafolio nuevo con RF% > 0
- Después de cada aporte confirmado (con `nuevo_capital_usd/ars` para contextualizar el monto)

Prioriza instrumentos por tipo según carry trade actual: carry positivo → cauciones + letras primero; carry negativo → bonos USD primero.

### Selección de activos RV (Fase 4)
`sugerir_activos_rv()` en `activos_rv.py` se llama al activar un portafolio nuevo con RV% > 0 (después de la sugerencia RF si aplica).

Flujo: Claude sugiere 2-4 activos basado en perfil (tipo/objetivo/plazo/moneda) → se pre-insertan en `portafolio_activos` → mensaje con toggles ✅/⬜ por activo (3 por fila). Cada tap persiste directo en DB (insert/delete); no hay estado pendiente. Botón "Listo — monitorear N activos" cierra el flujo. Fallback sin Claude: activos hardcodeados por tipo de portafolio.

Capital RV para el prompt de Claude: `capital_total_usd = capital_usd + capital_ars / dolar_mep` (doble moneda); luego `capital_rv_usd * dolar_mep` → ARS para el prompt. No se usa MEP hardcodeado.

`/activos` permite editar la selección de cualquier portafolio activo en cualquier momento.

Una vez que `portafolio_activos` tiene filas, el `cron_inversiones.py` comienza a generar señales RSI/EMA para esos activos.

### Renta Variable — señales
RSI (14 períodos) sobre histórico CoinGecko (crypto, hourly) / IOL (acciones, diario ajustado). Señal: RSI < 35 (sobreventa) o > 65 (sobrecompra). EMA 20/50 para tendencia. Claude Haiku genera recomendación con contexto de perfil + winrate histórico.

### Renta Fija — carry trade
`tna_mensual = tna_caucion / 12`. `devaluacion_mensual = Δ dólar_MEP 30d`. `carry = tna_mensual - devaluacion`. carry > 2% → ENTRAR; 0–2% → Claude evalúa; < 0% → SALIR a USD.

### Tarjetas y mes de resumen (Fase 5)
`calcular_mes_resumen(fecha_compra, dia_cierre)`: si `dia(fecha_compra) <= dia_cierre` → mismo mes; sino → mes siguiente.

Flujo de registro de gasto con tarjeta: `_process_text` → detecta tarjetas activas → guarda con `estado='pendiente_tarjeta'` → botones [Efectivo][Tarjeta…] → callback `pago_tar:{mov_id}:{tarjeta_id_o_0}` → aplica tarjeta + mes_resumen + finaliza (monto_bajo / categoria / confirmado).

Cuotas: `_registrar_cuota_plan` → si hay tarjetas → pregunta tarjeta → `cuota_tar:{plan_id}:{tarjeta_id}` → pregunta fecha → `_create_cuota_movimientos` propaga `tarjeta_id` y `mes_resumen` a cada movimiento generado.

Wizard tarjeta nueva: botones para nombre (`tnueva_nom:{nombre}`) → inserta `tarjetas` con `dia_cierre=NULL, activa=FALSE` → botones para día (`tnueva_cie:{id}:{dia}`) → activa.

### Colchón de tarjetas (Fase 5)
Portafolio `tipo='conservador', proposito='colchon_tarjetas'`. Creado con `/colchon_nuevo`.

`/colchon` calcula dinámicamente (sin cachear en BD):
- `comprometido` = `SUM(monto)` de movimientos con `tarjeta_id IS NOT NULL AND mes_resumen=mes AND descripcion LIKE '(cuota X/N)'`
- `gastado_variable` = mismo pero sin el patrón cuota
- `invertido` = `SUM(monto_ars)` de `posiciones_rf` abiertas del portafolio colchón
- `tope_variable` = guardado en `colchon_mensual` por el usuario (o sugerido por Claude)

Claude sugiere `tope_variable` on-demand solo si hay ≥2 meses de historial de gastos variables con tarjeta. Función `sugerir_tope_tarjetas(historial, presupuesto_total)` en `lib/claude_invest.py`.

Alerta de exceso: `_check_colchon_exceso()` en `movimiento_callbacks.py` se llama desde `pago_tar` (solo gastos variables, no cuotas) cuando `gastado_variable > tope_variable`.

### Pago de resumen de tarjeta (`/pagar_tarjeta`)
Resuelve un problema distinto al colchón: agrupa, por tarjeta, todo lo que corresponde pagar en el mes actual — cuotas fijas **y** compras en 1 pago — y permite registrar ese pago como un movimiento de caja real, separado de las compras originales.

Modelo de contabilidad (decisión explícita del usuario): una compra con tarjeta queda categorizada en el mes en que se hizo (`mes_resumen`), para poder comparar gasto por categoría mes a mes. El pago del resumen (`/pagar_tarjeta`) es un movimiento **independiente**, registrado en el mes en que efectivamente se paga, con categoría "Pago Tarjeta" y `es_pago_tarjeta=TRUE`. Esto "duplica" el monto en el total de gastos del mes de pago a propósito — es el costo de tener ambas vistas (gasto por categoría + flujo de caja real de tarjetas) sin tener que excluir compras con tarjeta del cálculo de balance existente.

Flujo: `handle_pagar_tarjeta_cmd()` → por cada tarjeta activa, `_calcular_total_tarjeta()` suma cuotas (patrón `(cuota X/N)`) + compras en 1 pago con `mes_resumen` = mes actual, excluyendo movimientos `es_pago_tarjeta=TRUE` y pagos ya registrados en `tarjeta_pagos` para ese mes → botones [Confirmar monto][Editar monto] → `pagtar_confirmar:{tarjeta_id}:{mes}:{monto}` o `pagtar_editar:{tarjeta_id}:{mes}:{monto_calculado}` (inserta fila `tarjeta_pagos` con `monto_pagado=NULL` como marcador y espera el monto por texto, mismo patrón que `colchon_mensual.tope_variable`) → `handle_pagar_tarjeta_text()` detecta la fila pendiente → `_registrar_pago_tarjeta()` inserta el movimiento gasto y hace upsert en `tarjeta_pagos` (`on_conflict` por `usuario_id, tarjeta_id, mes_resumen`).

`api/stats.py?resource=tarjetas` expone el mismo cálculo para el dashboard (widget en `ResumenTab.tsx`), excluyendo siempre `es_pago_tarjeta=TRUE` para no contar el pago contra sí mismo.

### Movimientos: estados
`estado` en `movimientos`: `confirmado` | `pendiente_confirmacion` (monto < $1000) | `pendiente_edicion_monto` | `pendiente_categoria` | `pendiente_tarjeta` (esperando elección de medio de pago).

### Wizard de portafolio: estados
`portafolios.estado_wizard`: `configurando_objetivo` → `configurando_renta` (pasivo) | `configurando_plazo` (cons/crec) | `configurando_capital` (oportunista) → `configurando_rf_pct` → `configurando_nombre` → `activo`.
RF%: opciones 0/25/50/75/100% para todos los tipos; ✨ marca el recomendado por tipo.
Estados de solo-botones protegidos por guard en dispatcher.

El cleanup al iniciar `/portafolio_nuevo` borra solo filas en `_WIZARD_ESTADOS` explícito (`configurando_*`), **no** rows de `plan_renta.py` que también usan `tipo='conservador'` — sus estados (`pidiendo_capital`, `eligiendo_plan`, etc.) son disjuntos.

---

## Decisiones de arquitectura

- **Python + FastAPI para el bot, Next.js solo para el dashboard**: bot como funciones serverless Vercel con FastAPI (ASGI).
- **Telegram ID como `usuario_id`**: el bot usa `from.id` directamente en todas las tablas. Simplifica el bot a costa de que el aislamiento dependa de nunca olvidar el filtro manual.
- **Sin middleware de auth Next.js**: verificación en cada Client Component. Funciona porque no hay rutas API Next.js que expongan datos financieros.
- **`supabase_client.py` usa service_role**: los endpoints Python no pasan por RLS. Seguridad = filtro por `usuario_id` en cada query.
- **GitHub Actions para crons de inversiones**: Vercel Free solo permite 1 cron/día. GitHub Actions permite `*/30 * * * *` y `0 15 * * 1-5`.
- **CoinGecko en lugar de Binance**: Binance bloquea IPs de Vercel US (HTTP 451). CoinGecko free tier sin restricciones geo.
- **IOL para RF y RV**: mismo endpoint `/api/v2/bCBA/Titulos/{simbolo}/Cotizacion` para CEDEARs, acciones, bonos y letras.
- **Capital en dos monedas**: `capital_usd` y `capital_ars` separados en lugar de convertir todo a USD al momento del aporte. Preserva la moneda original y permite recalcular al MEP corriente en cada consulta.
- **Sugerencia RF sin Claude**: la prioridad de instrumentos se calcula determinísticamente (carry trade + tipo de portafolio). Claude solo se usa para señales RV y zona gris carry. Más rápido y sin riesgo de timeout en el flujo de aporte.
- **Recharts para gráficos**: sobre Chart.js por integración React/TypeScript.

---

## Deuda técnica conocida

- **RLS no configurada por usuario en tablas de inversiones**: políticas permisivas (`USING (true)`). Si el anon key se usara en Python, cualquier usuario vería datos de otros.
- **Autenticación en endpoints Python sin validación cruzada**: `/api/stats`, `/api/cuotas`, etc. confían en que el dashboard pasa el `usuario_id` correcto.
- **TNA de cauciones IOL**: no hay endpoint documentado público. `fetch_caucion_tna()` intenta dos endpoints; si fallan, TNA queda NULL hasta actualización manual.
- **`schema_*.sql` múltiples archivos sin tooling de migraciones**: orden de aplicación documentado arriba; aplicar manualmente en Supabase SQL Editor.
- **`/mis_portafolios` no muestra aportes históricos**: muestra capital actual pero no el historial de `aportes_portafolio`.
- **`plan_renta.py` legado**: wizard paralelo con estados propios; no crea posiciones reales ni aprovecha `instrumentos_rf`. Candidato a deprecar.
- **Soft delete inconsistente**: `del_ok` hace `estado='anulado'` (correcto), pero el código antiguo hacía `delete()` real. Verificar que no queden referencias al delete directo.
