-- ============================================================
-- Migración RF Fix: Corregir posiciones_rf para portafolios
-- Ejecutar en Supabase → SQL Editor ANTES que el código Python
-- ============================================================

-- 1. Agregar columnas faltantes a posiciones_rf
ALTER TABLE posiciones_rf
  ADD COLUMN IF NOT EXISTS portafolio_id INT REFERENCES portafolios(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS monto_usd_entrada DECIMAL(15,2),
  ADD COLUMN IF NOT EXISTS fecha_cierre TIMESTAMPTZ;

-- 2. Actualizar la columna estado para usar valores consistentes
-- Primero, actualizar valores existentes del schema antiguo
UPDATE posiciones_rf SET estado = 'abierta' WHERE estado = 'activa';
UPDATE posiciones_rf SET estado = 'cerrada' WHERE estado IN ('vencida', 'rescatada');

-- 3. Cambiar default para que los nuevos registros usen 'abierta'
ALTER TABLE posiciones_rf
  ALTER COLUMN estado SET DEFAULT 'abierta';

-- 4. Crear índice para portafolio_id (queries frecuentes)
CREATE INDEX IF NOT EXISTS idx_posrf_portafolio ON posiciones_rf (portafolio_id);

-- Comentario: Las posiciones_rf ahora soportan complemente el flujo de portafolios
