-- ============================================================
-- Migración RF: capital_usd, asignacion_rf_pct + seed instrumentos
-- Ejecutar DESPUÉS de schema_rf.sql
-- ============================================================

-- 1. Columnas nuevas en perfiles de inversión
ALTER TABLE perfiles_inversion
  ADD COLUMN IF NOT EXISTS capital_usd DECIMAL(15,2),
  ADD COLUMN IF NOT EXISTS asignacion_rf_pct INT DEFAULT 30;

-- 2. Seed: instrumentos RF iniciales
INSERT INTO instrumentos_rf (codigo, nombre, tipo, moneda, plazo_dias, ticker_iol) VALUES
  ('CAUCION_1D',  'Caución 1 día',                 'caucion',       'ARS', 1,    NULL),
  ('CAUCION_7D',  'Caución 7 días',                 'caucion',       'ARS', 7,    NULL),
  ('CAUCION_30D', 'Caución 30 días',                'caucion',       'ARS', 30,   NULL),
  ('AL30',        'Bono AL30 (Ley AR, USD)',        'bono_soberano', 'USD', NULL, 'AL30'),
  ('GD30',        'Bono GD30 (Ley NY, USD)',        'bono_soberano', 'USD', NULL, 'GD30'),
  ('AE38',        'Bono AE38 (Ley NY, USD)',        'bono_soberano', 'USD', NULL, 'AE38'),
  ('GD35',        'Bono GD35 (Ley NY, USD)',        'bono_soberano', 'USD', NULL, 'GD35')
ON CONFLICT (codigo) DO NOTHING;

-- Nota: Letras (Lecaps) se insertan con su ticker específico cuando se conoce la licitación.
-- Ejemplo: INSERT INTO instrumentos_rf (codigo, nombre, tipo, moneda, plazo_dias, vencimiento, ticker_iol)
--          VALUES ('LECAP_S30J6', 'Lecap vto 30-Jun-2026', 'letra', 'ARS', 30, '2026-06-30', 'S30J6');
