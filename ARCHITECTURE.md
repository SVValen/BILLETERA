# ARCHITECTURE.md — Billetera
> Snapshot técnico generado por /snapshot. Actualizar con /snapshot --update tras cambios significativos.

## Archivos clave

### Autenticación (Next.js)
- `app/login/page.tsx` — login via magic link (OTP de Supabase); Client Component
- `app/auth/callback/route.ts` — Route Handler que intercambia el `code` de OAuth por sesión y redirige a `/dashboard`
- `app/configurar/page.tsx` — paso obligatorio post-login: vincula `user.id` (Supabase) con `telegram_id`; bloquea acceso al dashboard si no está configurado
- `lib/supabase-server.ts` — `createSupabaseServer()`: cliente Supabase para Server Components / Route Handlers usando cookies Next.js
- `lib/supabase-browser.ts` — `createSupabaseBrowser()`: cliente Supabase para Client Components

### Dashboard (Next.js)
- `app/dashboard/page.tsx` — shell del dashboard: maneja auth check, vinculación de telegram_id, selector de mes y dark mode; delega a 4 tabs
- `app/dashboard/ResumenTab.tsx` — estadísticas del mes: tarjetas de gasto/ingreso/saldo, gráficos Recharts (PieChart + BarChart), cuotas en curso, próximos recurrentes
- `app/dashboard/PresupuestosTab.tsx` — muestra presupuestos por categoría vs. gasto real del mes; permite crear/editar presupuestos desde el frontend
- `app/dashboard/MovimientosTab.tsx` — tabla de movimientos del mes con filtros; permite editar/borrar
- `app/dashboard/ObjetivosTab.tsx` — gestión de objetivos de ahorro

### Bot Telegram (Python / FastAPI)
- `api/telegram.py` — webhook principal: parsea mensajes, maneja callbacks de botones inline, registra movimientos; contiene toda la lógica de negocio del bot
- `api/cron.py` — tarea diaria (12:00 UTC via Vercel Cron): procesa recurrentes del día y los lunes envía resumen semanal a todos los usuarios
- `api/stats.py` — endpoint `/api/stats?mes=YYYY-MM&usuario=TID`: agrega gastos/ingresos por categoría para el dashboard
- `api/cuotas.py` — endpoint `/api/cuotas?usuario=TID`: lista planes de cuotas activos con progreso
- `api/recurrentes.py` — endpoint `/api/recurrentes?usuario=TID&dias=N`: lista recurrentes próximos
- `api/presupuestos.py` — endpoints CRUD de presupuestos para el dashboard
- `api/objetivos.py` — endpoints CRUD de objetivos de ahorro
- `api/movements.py` — endpoint de lectura/edición de movimientos para el dashboard

### Parser y helpers Python
- `lib/parser.py` — `parse_movement()`: regex para extraer monto/descripción/tipo de texto libre; `categorize_from_keywords()`: matching de keywords hardcodeadas; `parse_recurrente()` / `parse_cuotas()`: detecta patrones especiales
- `lib/supabase_client.py` — singleton `get_supabase()` con `SUPABASE_SERVICE_ROLE_KEY` (acceso privilegiado sin RLS)

### Configuración y schema
- `vercel.json` — declara el cron (`/api/cron` a las 12:00 UTC diario)
- `schema.sql` — schema base: tablas `movimientos`, `categorias`
- `schema_phase2.sql` / `schema_*.sql` — migraciones incrementales: perfiles, ingresos, recurrentes, suscripciones, cuotas, presupuestos

---

## Patrones

### Acceso a datos — Python (Bot/API)
Todas las API Routes Python usan `get_supabase()` que devuelve un cliente con `SUPABASE_SERVICE_ROLE_KEY` — bypasea RLS completamente. El aislamiento por usuario se hace **manualmente** filtrando por `usuario_id` (= Telegram ID como string) en cada query.

### Acceso a datos — Next.js (Dashboard)
Las tabs del dashboard son Client Components que llaman a los endpoints Python via `fetch('/api/...')`. No usan Supabase JS directamente para leer datos del negocio. El cliente Supabase JS solo se usa para auth (sesión de usuario).

### Auth check en el Dashboard
No hay middleware. La autenticación se verifica dentro de cada Client Component en un `useEffect` al montar. Flujo: `getUser()` → si no hay sesión, push `/login`; si hay sesión pero no `telegram_id`, push `/configurar`.

### Categorización automática
Doble capa: (1) keywords hardcodeadas en `lib/parser.py` por categoría; (2) keywords aprendidas per-usuario en tabla `keywords_aprendidas` — se guardan cuando el usuario elige manualmente una categoría. Fallback: categoría "Otros" (id=7) → muestra botones inline para selección manual.

### USD → ARS
Conversión al tipo oficial via `dolarapi.com/v1/dolares/oficial` en el momento del registro. La descripción queda con la anotación `(USD X @ $Y oficial)` para trazabilidad.

### Movimientos: estados
`estado` en tabla `movimientos`: `confirmado` (normal) | `pendiente_confirmacion` (monto bajo < $1000, esperando confirmación) | `pendiente_edicion_monto` (usuario pidió editar el monto, próximo mensaje de texto lo actualiza) | `pendiente_categoria` (necesita categorización manual).

---

## Decisiones de arquitectura

- **Python + FastAPI para el bot, Next.js solo para el dashboard**: el bot necesita correr como funciones serverless de Vercel con FastAPI (ASGI). Se separó el código TS del Python desde el inicio para evitar mezclarlo.
- **Telegram ID como `usuario_id`**: el bot usa el `from.id` de Telegram directamente como clave de usuario en todas las tablas. El dashboard lo obtiene de la tabla `perfiles` donde se vincula con el UUID de Supabase Auth. Esto simplifica el bot (sin lookup extra) a costa de que el aislamiento dependa de nunca olvidar el filtro.
- **Sin middleware de auth Next.js**: el proyecto no usa `middleware.ts`. La verificación de sesión está en cada Client Component. Funciona porque no hay rutas API Next.js que expongan datos financieros — todas las queries van por los endpoints Python que usan service_role.
- **`supabase_client.py` usa service_role** (no anon key): los endpoints Python no pasan por RLS. Toda la seguridad es aislamiento por `usuario_id` en cada query. Las políticas RLS en el schema original son permisivas (legacy del MVP).
- **Recharts para gráficos**: elegido sobre Chart.js por integración más natural con React/TypeScript.
- **Soft delete no implementado para movimientos vía bot**: el callback `del_ok` hace un `delete()` real. El AGENTS.md dice "nunca eliminar", pero el bot sí borra. Inconsistencia conocida.

---

## Trabajo en curso

### Deuda técnica conocida
- **RLS no configurada por usuario**: las políticas actuales son permisivas (service_role todo). Si el anon key llegara a usarse en Python, cualquier usuario vería datos de otros.
- **Autenticación en endpoints Python sin validación**: `/api/stats`, `/api/cuotas`, etc. aceptan cualquier `usuario=TID` sin verificar que el cliente autenticado corresponda a ese telegram_id. Confían en que el dashboard pasa el ID correcto.
- **Borrado real de movimientos en el bot**: contradice la regla de negocio de soft delete definida en AGENTS.md.
- **`schema_*.sql` múltiples archivos**: no hay tooling de migraciones (sin Flyway, Prisma migrate, etc.). El estado real del schema en producción requiere aplicar todos los archivos en orden.
- **Cron con `CRON_SECRET` opcional**: si la variable no está seteada, el endpoint es público.

### TODOs críticos
- Sin TODOs/FIXMEs explícitos en el código al momento del snapshot (2026-06-14).
