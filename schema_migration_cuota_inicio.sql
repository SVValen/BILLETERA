-- Migración: soporte de cuotas en progreso
-- Aplica sobre DB existente (no rompe planes actuales: DEFAULT 1)
ALTER TABLE cuotas_plan
  ADD COLUMN IF NOT EXISTS cuota_inicio INT NOT NULL DEFAULT 1;
