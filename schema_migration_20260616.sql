-- ============================================================
-- Migración 2026-06-16: moneda_preferida + fix YPF symbol
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- 1. Agregar columna moneda_preferida al perfil de inversión
ALTER TABLE perfiles_inversion
  ADD COLUMN IF NOT EXISTS moneda_preferida VARCHAR(10) DEFAULT 'ARS';

-- 2. Corregir símbolo de YPF en IOL (ticker BYMA es YPFD)
UPDATE activos SET simbolo_fuente = 'YPFD', nombre = 'YPF (YPFD)'
  WHERE codigo = 'YPF';
