# Orden de migraciones — Billetera

Aplicar en Supabase → SQL Editor en este orden:

| # | Archivo | Qué crea / modifica |
|---|---------|---------------------|
| 1 | `schema.sql` | Tablas base: `movimientos`, `categorias` (categorías 1–7), RLS inicial |
| 2 | `schema_perfiles.sql` | Tabla `perfiles` (vincula Supabase user_id ↔ telegram_id) + categorías adicionales |
| 3 | `schema_categorias_v2.sql` | Recrea categorías sin columna `presupuesto_mensual` (limpieza del schema base) |
| 4 | `schema_ingresos.sql` | Agrega categoría Ingresos (id=17) |
| 5 | `schema_phase2.sql` | Tabla `presupuestos`, tabla `cuotas_plan`, tabla `keywords_aprendidas`, tabla `objetivos_ahorro` |
| 6 | `schema_recurrentes.sql` | Tabla `recurrentes` (gastos recurrentes mensuales) |
| 7 | `schema_suscripciones.sql` | Agrega categoría Suscripciones (id=18) |
| 8 | `schema_rls_policies.sql` | Reemplaza policies permisivas por policies que filtran por `auth_telegram_id()` |
| 9 | `schema_atomic_aporte.sql` | Función RPC `incrementar_objetivo` para aporte atómico sin race condition |

## Cómo aplicar en un ambiente nuevo

1. Abrir Supabase → SQL Editor
2. Pegar y ejecutar cada archivo en el orden de la tabla de arriba
3. Verificar que no hay errores antes de pasar al siguiente

## Estado del schema en producción

El schema está gestionado manualmente (sin herramienta de migraciones). Si se necesita saber
el estado actual de producción, comparar contra este orden aplicando cada archivo en un ambiente de staging.
