# ARCHITECTURE.md — Billetera
> Snapshot técnico. Actualizar con /snapshot --update tras cambios significativos.
> Última actualización: 2026-06-17

## Archivos clave

### Autenticación (Next.js)
- `app/login/page.tsx` — login via magic link (OTP de Supabase); Client Component
- `app/auth/callback/route.ts` — intercambia `code` de OAuth por sesión y redirige a `/dashboard`
- `app/configurar/page.tsx` — paso obligatorio post-login: vincula `user.id` con `telegram_id`
- `lib/supabase-server.ts` — `createSupabaseServer()`: cliente para Server Components / Route Handlers
- `lib/supabase-browser.ts` — `createSupabaseBrowser()`: cliente para Client Components

### Dashboard (Next.js)
- `app/dashboard/page.tsx` — shell: auth check, selector de mes, dark mode, delega a tabs
- `app/dashboard/ResumenTab.tsx` — tarjetas gasto/ingreso/saldo, PieChart + BarChart, cuotas, recurrentes
- `app/dashboard/PresupuestosTab.tsx` — presupuestos por categoría vs. gasto real del mes
- `app/dashboard/MovimientosTab.tsx` — tabla de movimientos con filtros; editar/borrar
- `app/dashboard/ObjetivosTab.tsx` — objetivos de ahorro
- `app/dashboard/InversionesTab.tsx` — perfil RV, activos monitoreados, recomendaciones pendientes, historial decisiones

### Bot Telegram (Python / FastAPI)
- `api/telegram.py` — webhook principal (~2200 líneas): parsea mensajes, callbacks inline, wizard de inversiones, parser de posiciones RF, todos los comandos
- `api/cron.py` — cron diario (12:00 UTC via Vercel Cron): recurrentes del día + resumen semanal los lunes
- `api/cron_inversiones.py` — cron RV cada ~30 min (GitHub Actions): actualiza precios, RSI/EMA, genera recomendaciones
- `api/cron_rf.py` — cron RF diario L-V 15:00 UTC (GitHub Actions): actualiza TNA/precios RF, evalúa carry trade, alerta vencimientos, sugiere rotación RF↔RV
- `api/stats.py` — `/api/stats?mes=YYYY-MM&usuario=TID`: agrega gastos/ingresos por categoría
- `api/cuotas.py` — `/api/cuotas?usuario=TID`: cuotas activas con progreso
- `api/recurrentes.py` — `/api/recurrentes?usuario=TID&dias=N`: recurrentes próximos
- `api/presupuestos.py` — CRUD de presupuestos
- `api/objetivos.py` — CRUD de objetivos de ahorro
- `api/movements.py` — lectura/edición de movimientos para el dashboard
- `api/inversiones.py` — endpoints RV+RF para dashboard: `?resource=perfil|activos|recomendaciones|decisiones|liquidez|allocation|instrumentos_rf`

### Librerías Python
- `lib/parser.py` — `parse_movement()`, `categorize_from_keywords()`, `parse_recurrente()`, `parse_cuotas()`
- `lib/supabase_client.py` — singleton `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY`
- `lib/market_data.py` — fetchers de precio: CoinGecko (crypto), IOL (CEDEARs/acciones/bonos/letras), dolarapi (dólar), `fetch_caucion_tna()`, `fetch_iol_rf()`
- `lib/indicators.py` — `calcular_rsi()`, `calcular_ema()`, `detectar_tendencia()`, `tiene_senal()`, `interpretar_rsi()`
- `lib/claude_invest.py` — `generar_recomendacion()`, `sugerir_activos_para_perfil()`, `sugerir_portafolio()`, `responder_pregunta_activos()`, `analizar_oportunidad_rf()`, `formatear_mensaje_telegram()`
- `lib/rf_analysis.py` — `analizar_carry_trade()`, `evaluar_vencimientos()`, `calcular_rendimiento_usd()`, `calcular_allocation()`
- `lib/auth.py` — `get_telegram_id_from_request()`: extrae telegram_id desde sesión Supabase en endpoints del dashboard

### GitHub Actions (crons)
- `.github/workflows/cron-inversiones.yml` — cada 30 min: llama `/api/cron_inversiones`
- `.github/workflows/cron-outcomes.yml` — diario 03:00 UTC: llama `/api/cron_inversiones/outcomes`
- `.github/workflows/cron-rf.yml` — L-V 15:00 UTC: llama `/api/cron_rf`

### Schema SQL (orden de aplicación)
1. `schema.sql` — base: `movimientos`, `categorias`
2. `schema_phase2.sql` / `schema_*.sql` — perfiles, ingresos, recurrentes, suscripciones, cuotas, presupuestos
3. `schema_rls_policies.sql` — políticas RLS por usuario
4. `schema_inversiones.sql` — módulo RV: `perfiles_inversion`, `activos`, `usuario_activos`, `recomendaciones`, `decisiones_inversion`, `precios_historicos`
5. `schema_migration_20260616.sql` — `moneda_preferida`, fix YPF→YPFD
6. `schema_rf.sql` — módulo RF: `instrumentos_rf`, `posiciones_rf`
7. `schema_migration_rf.sql` — `capital_usd`, `asignacion_rf_pct` + seed instrumentos RF

---

## Patrones

### Acceso a datos — Python
Todas las APIs Python usan `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY` — bypasea RLS. El aislamiento por usuario se hace **manualmente** filtrando por `usuario_id` (= Telegram ID) en cada query.

### Acceso a datos — Next.js
Las tabs del dashboard son Client Components que llaman a los endpoints Python via `fetch('/api/...')`. El cliente Supabase JS solo se usa para auth.

### Auth check en el Dashboard
No hay middleware. Verificación en cada Client Component via `useEffect`: `getUser()` → si no hay sesión push `/login`; si hay sesión pero no `telegram_id` push `/configurar`.

### Routing Vercel Python
Cada archivo `api/foo.py` maneja **solo** `/api/foo`. Sub-paths como `/api/foo/bar` devuelven 404. Para múltiples operaciones: `GET ?resource=X` y `POST {resource: "X"}`.

### Categorización automática
Doble capa: (1) keywords hardcodeadas en `lib/parser.py`; (2) keywords aprendidas per-usuario en `keywords_aprendidas`. Fallback: categoría "Otros" → botones inline.

### USD → ARS (movimientos)
Conversión al tipo oficial via `dolarapi.com/v1/dolares/oficial`. La descripción queda con `(USD X @ $Y oficial)` para trazabilidad.

### Renta Variable — señales
RSI (14 períodos) calculado sobre histórico de CoinGecko (crypto, hourly) / IOL (acciones, diario ajustado). Señal cuando RSI < 35 (sobreventa) o > 65 (sobrecompra). EMA 20/50 para tendencia. Claude Haiku genera la recomendación con contexto de perfil + winrate.

### Renta Fija — carry trade
`tna_mensual = tna_caucion / 12`. `devaluacion_mensual = Δ dólar_MEP últimos 30d`. `carry = tna_mensual - devaluacion`. carry > 2% → ENTRAR ARS; < 0% → SALIR a USD; 0-2% → Claude evalúa contexto.

### Capital en USD
`perfiles_inversion.capital_usd` almacena el capital total en USD. Para instrumentos ARS se convierte al MEP en el momento. El P&L de posiciones RF se calcula en USD: `(monto_ars_final / mep_actual) - monto_usd_entrada`.

### Movimientos: estados
`estado` en `movimientos`: `confirmado` | `pendiente_confirmacion` (monto < $1000) | `pendiente_edicion_monto` | `pendiente_categoria`.

### Wizard de inversiones: estados de perfil
`perfiles_inversion.estado`: `configurando_objetivos` → `configurando_plazo` → `configurando_moneda` → `configurando_capital` → `configurando_rf_pct` → `configurando_descripcion` → `configurando_activos` → `configurando_portafolio` → `activo`.
Los estados de solo-botones están protegidos por un catch-all guard en el dispatcher de texto (evita movimientos fantasma).

---

## Decisiones de arquitectura

- **Python + FastAPI para el bot, Next.js solo para el dashboard**: bot como funciones serverless Vercel con FastAPI (ASGI).
- **Telegram ID como `usuario_id`**: el bot usa `from.id` directamente en todas las tablas. Simplifica el bot a costa de que el aislamiento dependa de nunca olvidar el filtro.
- **Sin middleware de auth Next.js**: verificación en cada Client Component. Funciona porque no hay rutas API Next.js que expongan datos financieros.
- **`supabase_client.py` usa service_role**: los endpoints Python no pasan por RLS. Seguridad = filtro por `usuario_id` en cada query.
- **GitHub Actions para crons de inversiones**: Vercel Free solo permite 1 cron/día. GitHub Actions permite `*/30 * * * *` y `0 15 * * 1-5`.
- **CoinGecko en lugar de Binance**: Binance bloquea IPs de Vercel US (HTTP 451). CoinGecko no tiene restricciones geo en free tier.
- **IOL para RF y RV**: mismo endpoint `/api/v2/bCBA/Titulos/{simbolo}/Cotizacion` para CEDEARs, acciones, bonos y letras. TNA de cauciones via endpoints separados (con fallback graceful si no disponible).
- **Recharts para gráficos**: sobre Chart.js por integración React/TypeScript.
- **Soft delete no implementado para movimientos vía bot**: el callback `del_ok` hace un `delete()` real. Inconsistencia con la regla de AGENTS.md.

---

## Deuda técnica conocida

- **RLS no configurada por usuario en tablas de inversiones**: políticas permisivas (`USING (true)`). Si el anon key se usara en Python, cualquier usuario vería datos de otros.
- **Autenticación en endpoints Python sin validación cruzada**: `/api/stats`, `/api/cuotas`, etc. confían en que el dashboard pasa el `usuario_id` correcto.
- **TNA de cauciones IOL**: no hay endpoint documentado público para leer tasas sin ejecutar una operación. `fetch_caucion_tna()` intenta dos endpoints; si fallan, la TNA queda NULL hasta actualización manual.
- **`schema_*.sql` múltiples archivos**: sin tooling de migraciones. Orden de aplicación documentado arriba.
- **`telegram.py` monolítico**: ~2200 líneas con toda la lógica del bot inline.
