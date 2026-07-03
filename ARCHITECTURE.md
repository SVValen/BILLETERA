# ARCHITECTURE.md — Billetera
> Snapshot técnico. Actualizar con /snapshot --update tras cambios significativos.
> Última actualización: 2026-06-30 (modernización UI + Consumo vs Pagado + badges tarjetas + totales filtrados + gestión de categorías + edición de recurrentes)

## Archivos clave

### Autenticación (Next.js)
- `middleware.ts` — protege `/dashboard/:path*` y `/configurar/:path*`; redirige a `/login` si no hay sesión Supabase; sin verificación de `telegram_id` (eso lo hace cada Client Component)
- `app/login/page.tsx` — magic link (OTP Supabase); Client Component
- `app/auth/callback/route.ts` — intercambia `code` de OAuth por sesión, redirige a `/dashboard`
- `app/configurar/page.tsx` — paso obligatorio post-login: vincula `user.id` con `telegram_id` en `perfiles`
- `lib/supabase-server.ts` — `createSupabaseServer()` para Server Components / Route Handlers
- `lib/supabase-browser.ts` — `createSupabaseBrowser()` para Client Components
- `lib/auth.py` — `get_telegram_id_from_request()`: valida Bearer JWT Supabase → `supabase.auth.get_user(token)` → lookup `perfiles.telegram_id`; retorna `(telegram_id, None)` o `(None, JSONResponse 401/403)`; usado por todos los endpoints Python del dashboard
- `lib/fetch-with-auth.ts` — helper fetch con Bearer JWT de sesión Supabase; todos los Client Components lo usan para llamar a los endpoints Python

### Dashboard (Next.js) — app/dashboard/
- `page.tsx` — shell: auth check via `getUser()` + lookup `perfiles.telegram_id`, dark mode, selector de mes (compartido por inicio/detalle/presupuestos/movimientos), renderiza las 9 tabs. Tabs: `inicio|detalle|presupuestos|objetivos|movimientos|categorias|inversiones|liquidez|prestamos`
- `InicioTab.tsx` — 4 cards (Consumo/Pagado/Ingresos/Saldo), donut por categoría, bar chart con 3 barras (Consumo+Pagado+Ingresos), widget comparativa mes anterior (tasa ahorro, split efectivo/tarjeta, variación por categoría)
- `DetalleMensualTab.tsx` — resumen tarjetas con badge ✅/⏳ y grand total por pagar / ya pagado; detalle expandible por tarjeta; cuotas con badge 🏁 cuando `restantes === 1`; recurrentes con badge hoy/mañana
- `MovimientosTab.tsx` — tabla paginada + filtros (búsqueda/tipo/categoría/fecha); banner `.total-filtrado` con gastos+ingresos+neto del conjunto completo (no solo la página) cuando hay filtros activos; recategorización inline por fila con aprendizaje de keywords (PATCH)
- `PresupuestosTab.tsx` — presupuestos vs. gasto real; categorías desde `/api/presupuestos?resource=categorias` (no hardcodeadas)
- `CategoriasTab.tsx` — CRUD de categorías: crear (POST) y editar nombre/emoji (PUT); sin delete (FK sin CASCADE desde `movimientos.categoria_id` y `recurrentes.categoria_id`)
- `ObjetivosTab.tsx` — objetivos de ahorro con progress bar y aportes
- `InversionesTab.tsx` — portafolios, activos RV, recomendaciones pendientes, historial decisiones
- `LiquidezTab.tsx` — carry trade, posiciones RF abiertas, P&L
- `PrestamosTab.tsx` — préstamos activos con cuotas adelantadas

### Endpoints del dashboard (Python FastAPI)
- `api/stats.py` — GET `?mes=`: `total_gastos` (consumo, excluye `es_pago_tarjeta`), `total_pagado` (flujo caja real: efectivo + pagos resumen), `saldo = ingresos - total_pagado`, `por_categoria`. GET `?resource=tarjetas`: total a pagar por tarjeta del mes (`mes_resumen`) + estado de pago desde `tarjeta_pagos`. GET `?resource=metricas`: comparativa vs mes anterior (siempre excluye `es_pago_tarjeta`)
- `api/movements.py` — GET: lista paginada + `total_monto_gasto`/`total_monto_ingreso` del conjunto completo filtrado (doble query: paginada con `count="exact"` + lightweight `SELECT monto,tipo` con mismos filtros; cuando `todos=1` los totales se computan del mismo response). PATCH `?id=X {categoria_id}`: recategoriza + llama `_save_learned_keywords`
- `api/presupuestos.py` — CRUD presupuestos (`categoria_id`+`monto`+`mes`). Discrimina `?resource=categorias` / `{resource:"categorias"}` para GET (lista) / POST (crear) / PUT (editar nombre/emoji) sobre tabla `categorias` global. Sin DELETE
- `api/cuotas.py` — GET `?mes=`: cuotas activas con progreso (respeta `cuota_inicio`)
- `api/recurrentes.py` — GET `?dias=N`: próximos recurrentes en los próximos N días
- `api/objetivos.py` — CRUD objetivos de ahorro
- `api/inversiones.py` — GET `?resource=portafolios|perfil|activos|recomendaciones|decisiones|liquidez|allocation|instrumentos_rf`

### Bot Telegram (Python FastAPI) — api/bot/
- `api/telegram.py` — webhook principal; delega a `dispatcher.py`
- `api/bot/dispatcher.py` — cadena de routing (orden crítico): `handle_wizard_text` → `handle_plan_renta_text` → `handle_colchon_text` → `handle_pagar_tarjeta_text` → **`handle_recurrente_text`** → `parse_aporte`/`handle_aporte` → comandos `/...` → `_parse_posicion_rf` → `_process_text` (fallback). Aplicada en ambas ramas (texto plano y transcripción de voz)
- `api/bot/handlers/recurrentes.py` — `_registrar_recurrente()` para nuevo recurrente vía texto libre; `handle_recurrente_text()` captura monto editado cuando `esperando_edicion_monto=TRUE`, actualiza `recurrentes.monto` base y registra movimiento del día
- `api/bot/handlers/transferencias.py` — `handle_transferencia_text()`: captura la descripción libre de una transferencia detectada por mail (`estado='pendiente_descripcion_transferencia'`), categoriza y confirma o pide categoría con botones
- `api/bot/helpers.py` — `_save_learned_keywords(descripcion, categoria_id, usuario_id)`: extrae palabras ≥4 chars, filtra stop words, upsert en `keywords_aprendidas`; `_categorize()`: hardcoded + keywords aprendidas; importado también desde `api/movements.py`
- `api/bot/handlers/movimientos.py` — `_process_text`: parser principal de gastos/ingresos; `_save_and_confirm()` y `finalizar_pago_tarjeta_unico()` (compartido con sync IMAP)
- `api/bot/handlers/wizard_inversion.py` — wizard de portafolio + `_sugerir_instrumentos_rf()`
- `api/bot/handlers/aportes.py` — detección y confirmación de aportes de capital; sugiere RF post-aporte
- `api/bot/handlers/posiciones_rf.py` — parser RF + callbacks `rf_elegir`/`rf_monto`/`rf_confirmar`/`rf_rescatar`
- `api/bot/handlers/activos_rv.py` — selección de activos RV con toggles; callbacks `rv_toggle`/`rv_confirmar`
- `api/bot/handlers/tarjetas.py` — wizard tarjeta nueva, `/tarjetas`, `/pagar_tarjeta`, callback `last4_tar` para resolución IMAP
- `api/bot/handlers/colchon.py` — `/colchon_nuevo`, `/colchon` (status + sugerencia Claude), captura de tope variable
- `api/bot/handlers/prestamos.py` — préstamos con adelanto de cuotas; detección por keywords
- `api/bot/handlers/objetivos.py` — objetivos de ahorro con conexión a portafolio
- `api/bot/callbacks/movimiento_callbacks.py` — callbacks editar/borrar/categorizar/recurrentes/cuotas; `_save_learned_keywords` tras confirmación de categoría; `recurrente_editar:{id}` setea `esperando_edicion_monto=TRUE`
- `api/bot/callbacks/recomendacion_callbacks.py` — callbacks `inv_ok`/`inv_no` para señales RV

### Crons
- `api/cron.py` — Vercel Cron (12:00 UTC diario): `_procesar_recurrentes()` con atomic claim (`.or_("ultimo_recordatorio.is.null,..."`); keyboard 3 botones: Sí/No/**Editar monto**; resumen semanal los domingos
- `api/cron_inversiones.py` — GitHub Actions cada 30 min: precios + RSI/EMA + recomendaciones RV + `?job=gmail_sync` → `sync_gmail_all_users()`
- `api/cron_rf.py` — GitHub Actions L-V 15:00 UTC: TNA/precios RF + carry trade + alertas vencimientos
- `.github/workflows/cron-gmail-sync.yml` — cada 20 min: llama `/api/cron_inversiones?job=gmail_sync`

### Librerías Python — lib/
- `lib/parser.py` — `parse_movement()`, `categorize_from_keywords()`, `parse_recurrente()`, `parse_cuotas()`, `parse_aporte()`
- `lib/supabase_client.py` — singleton `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY`
- `lib/market_data.py` — fetchers: CoinGecko, IOL, dolarapi; `fetch_caucion_tna()`, `fetch_precio_activo()`
- `lib/indicators.py` — `calcular_rsi()`, `calcular_ema()`, `detectar_tendencia()`, `tiene_senal()`
- `lib/claude_invest.py` — `generar_recomendacion()`, `sugerir_activos_para_perfil()`, `sugerir_portafolio()`, `sugerir_tope_tarjetas()`, `analizar_oportunidad_rf()`
- `lib/rf_analysis.py` — `analizar_carry_trade()`, `calcular_rendimiento_usd()`, `calcular_allocation()`
- `lib/tarjetas.py` — `calcular_mes_resumen(fecha_compra, dia_cierre)`: mes en que el usuario paga, no el mes de cierre del ciclo (corrección 2026-06-30)
- `lib/auth.py` — `get_telegram_id_from_request()` para endpoints Python del dashboard
- `lib/email_parser_santander.py` — clasifica y parsea 5 tipos de mail Santander (débito automático, pago 1 pago, pago cuotas, débito, transferencia)
- `lib/gmail_sync.py` — `sync_gmail_all_users()`: polling IMAP, dedup por `Message-ID`, routing por tipo de mail

### CSS / Design system
- `app/globals.css` — design system completo: variables CSS light/dark, grid `auto-fit minmax(150px,1fr)` para cards (soporta 4 columnas), hover/transform en cards, badge system (`.badge-ok`/`.badge-pending`/`.badge-alert`/`.badge-info`/`.badge-last`), nav con gradiente en título, `.total-filtrado` para banners de totales filtrados, botones con box-shadow feedback

---

## Patrones

### Acceso a datos — Python
Todos los endpoints Python usan `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY` — bypasea RLS. Aislamiento por usuario **manual** filtrando por `usuario_id` (= Telegram ID) en cada query. Sin RLS activa en tablas de inversiones.

### Auth en endpoints Python del dashboard
`get_telegram_id_from_request(request)` extrae Bearer JWT del header Authorization → `supabase.auth.get_user(token)` → lookup `perfiles.telegram_id`. Retorna `(telegram_id, None)` si OK, o `(None, JSONResponse)` si falla. Todos los endpoints Python del dashboard llaman esto primero.

### Acceso a datos — Next.js
Client Components fetching via `fetchWithAuth` (inyecta Bearer token de sesión Supabase). Sin Server Components con data fetching — todo es client-side. `useEffect` + cancellation token para evitar race conditions al cambiar mes. Supabase JS se usa solo para auth.

### Separación Consumo vs Flujo de Caja (InicioTab)
`api/stats.py` GET principal distingue:
- `total_gastos` = consumo (tipo='gasto' AND NOT `es_pago_tarjeta`) — para breakdown por categoría
- `total_pagado` = flujo caja (efectivo + `es_pago_tarjeta=TRUE`, excluye TC sin pagar) — para el saldo real
- `saldo = total_ingresos - total_pagado` — dinero que realmente quedó en la cuenta

### Totales filtrados en movimientos
`GET /api/movements` siempre ejecuta dos queries: (1) paginada con `count="exact"` para los datos de la página, (2) lightweight `SELECT monto,tipo` con los mismos filtros para `total_monto_gasto`/`total_monto_ingreso` del conjunto completo. Cuando `todos=1`, los totales se computan del único response sin segunda query.

### Keyword learning — bidireccional
`_save_learned_keywords(descripcion, categoria_id, usuario_id)` en `api/bot/helpers.py` se llama desde: (1) bot tras confirmar categoría (`movimiento_callbacks.py`), (2) dashboard al recategorizar (`movements.py` PATCH). Extrae palabras ≥4 chars, filtra stop words de `constants.py`, upsert `keywords_aprendidas` con `on_conflict=usuario_id,keyword` → cada keyword mapea a exactamente una categoría por usuario.

### Recurrentes — edición de monto pre-confirmación
Marcador transitorio `recurrentes.esperando_edicion_monto BOOLEAN DEFAULT FALSE` — mismo patrón que `colchon_mensual.tope_variable IS NULL` / `tarjeta_pagos.monto_pagado IS NULL`. Callback `recurrente_editar:{rec_id}` setea el flag; `handle_recurrente_text()` en el dispatcher lo detecta primero (antes del parser de movimientos), parsea el monto del texto libre, actualiza `recurrentes.monto` (base hacia adelante) y registra el movimiento del día.

### Categorías — gestión desde dashboard
`api/presupuestos.py` discrimina `?resource=categorias` / `{resource:"categorias"}` para GET/POST/PUT sobre la tabla `categorias` (global, sin `usuario_id`). Sin DELETE porque la tabla no tiene soft-delete y `movimientos.categoria_id` + `recurrentes.categoria_id` son FK sin CASCADE — borrar rompería historial.

### Pending state via sentinel
Patrón recurrente para capturar texto libre después de un callback:
- `colchon_mensual.tope_variable IS NULL` → `handle_colchon_text`
- `tarjeta_pagos.monto_pagado IS NULL` → `handle_pagar_tarjeta_text`
- `recurrentes.esperando_edicion_monto = TRUE` → `handle_recurrente_text`
- `tarjeta_last4_map.tarjeta_id IS NULL` → resolución IMAP via `last4_tar` callback
- `movimientos.estado = 'pendiente_descripcion_transferencia'` → `handle_transferencia_text` (transferencias detectadas por mail, sin comercio)

Cada handler retorna `bool` y se llama en orden en `dispatch_message` antes del parser de movimientos.

### Cron de recurrentes — atomic claim
`_procesar_recurrentes()` actualiza `ultimo_recordatorio` con `.or_("ultimo_recordatorio.is.null,ultimo_recordatorio.lt.{hoy}")`. Si no devuelve filas, otro proceso ya lo procesó hoy — early exit sin duplicar el recordatorio.

### Multi-resource en un mismo archivo Python
Vercel Hobby: máximo 12 funciones serverless, límite alcanzado. Sub-operaciones se discriminan con `?resource=X` (GET) y `{resource:"X"}` en body (POST/PUT/PATCH) dentro del mismo `api/*.py`. No agregar `api/*.py` nuevos.

### Routing Vercel Python
Cada `api/foo.py` maneja exactamente `/api/foo`. Sub-paths devuelven 404. `sys.path.insert(0, ...)` al inicio de cada archivo permite imports desde `lib/` y `api/bot/`.

### Dashboard — auth check
Sin middleware Next.js para proteger datos. Verificación en cada Client Component: `getUser()` → sin sesión → `/login`; con sesión pero sin `telegram_id` en `perfiles` → `/configurar`. El `middleware.ts` solo redirige a `/login` si no hay sesión Supabase activa.

---

## Decisiones de arquitectura

- **Consumo ≠ Flujo de caja (decisión explícita del usuario)**: Las compras con TC se categorizan en el mes de compra. El pago del resumen es un movimiento separado en el mes de pago (`es_pago_tarjeta=TRUE`). El dashboard muestra ambas vistas (4 cards) para evitar confusión. El `saldo` usa el flujo de caja real, no el consumo.
- **Keywords aprendidas centralizadas en helpers.py**: `_save_learned_keywords` vive en `api/bot/helpers.py` e importado también desde `api/movements.py` (PATCH). Evita duplicar lógica de extracción/filtrado. El import funciona porque todos los `api/*.py` hacen `sys.path.insert(0, ...)`.
- **Categorías globales (sin `usuario_id`)**: Todas las categorías son compartidas entre usuarios. Simplifica el modelo y el CRUD. El aprendizaje de keywords sí es per-usuario (`keywords_aprendidas.usuario_id`).
- **Python + FastAPI para el bot, Next.js solo para el dashboard**: bot como funciones serverless Vercel con FastAPI (ASGI). No mezclar lógica de bot en Next.js API Routes.
- **Telegram ID como `usuario_id` en todas las tablas del bot**: simplifica el bot; el aislamiento depende de nunca olvidar el filtro manual en cada query.
- **GitHub Actions para crons de inversiones**: Vercel Free solo permite 1 cron/día. GitHub Actions permite `*/30 * * * *` y `0 15 * * 1-5`.
- **CoinGecko en lugar de Binance**: Binance bloquea IPs de Vercel US (HTTP 451).
- **Capital en dos monedas**: `capital_usd` + `capital_ars` separados — preserva la moneda original y permite recalcular al MEP corriente en cada consulta.
- **Sugerencia RF sin Claude**: prioridad determinística (carry trade + tipo de portafolio). Claude solo para señales RV y zona gris carry. Más rápido y sin riesgo de timeout en el flujo de aporte.
- **Recharts para gráficos**: sobre Chart.js por integración React/TypeScript.

---

## Trabajo en curso

### Funcionalidades recientes (activas y estables)
- **Auto-registro IMAP Santander** (`lib/gmail_sync.py` + `lib/email_parser_santander.py`): polling cada 20 min, 5 tipos de mail (incluye transferencias enviadas, registradas como efectivo con descripción pendiente), resolución de last4 via `tarjeta_last4_map`
- **Gestión de categorías desde el dashboard** (`CategoriasTab.tsx` + `api/presupuestos.py?resource=categorias`)
- **Recategorización con aprendizaje** (`MovimientosTab.tsx` + `movements.py` PATCH): corregir categorías desde la tabla y propagar keywords
- **Edición de monto de recurrentes** (`handlers/recurrentes.py` + `cron.py`): 3er botón "Editar monto"; actualiza monto base hacia adelante
- **Separación Consumo vs Pagado** (`InicioTab.tsx` + `stats.py`): 4 cards, bar chart con 3 series
- **Totales filtrados en movimientos** (`MovimientosTab.tsx` + `movements.py`): banner con suma del conjunto completo filtrado
- **Badges DetalleMensualTab**: ✅/⏳ por tarjeta, grand total pendiente/pagado, 🏁 última cuota
- **Objetivos de ahorro con portafolio conectado** (`ObjetivosTab.tsx`, `handlers/objetivos.py`)
- **Préstamos con adelanto de cuotas** (`PrestamosTab.tsx`, `handlers/prestamos.py`)

### Deuda técnica conocida
- **RLS no configurada en tablas de inversiones**: políticas permisivas `USING (true)`. Si el anon key se usara en Python, cualquier usuario vería datos de otros.
- **`plan_renta.py` legado**: wizard paralelo con estados propios; no crea posiciones reales ni usa `instrumentos_rf`. Candidato a deprecar.
- **`schema_*.sql` múltiples archivos sin tooling de migraciones**: orden de aplicación documentado en AGENTS.md; aplicar manualmente en Supabase SQL Editor.
- **`/mis_portafolios` no muestra historial de aportes**: muestra capital actual pero no `aportes_portafolio`.
- **TNA de cauciones IOL**: endpoint no documentado públicamente; puede devolver NULL hasta actualización manual.
- **Soft delete inconsistente**: `del_ok` hace `estado='anulado'` (correcto), verificar que no queden referencias al `delete()` directo del código antiguo.
