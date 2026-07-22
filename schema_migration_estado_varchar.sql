-- ============================================================
-- BILLETERA — Ampliar movimientos.estado (VARCHAR(30) se quedaba corto)
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- 'pendiente_descripcion_transferencia' tiene 35 caracteres — no entraba en
-- VARCHAR(30), así que todo insert de una transferencia detectada por mail
-- fallaba con 400 Bad Request (Postgrest) y la transferencia nunca se
-- registraba. VARCHAR(50) deja margen para futuros estados largos.
ALTER TABLE movimientos ALTER COLUMN estado TYPE VARCHAR(50);
