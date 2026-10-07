-- ============================================================
-- BILLETERA v2 — Cuotas familia (2026-10-07)
-- Compras hechas con tarjeta para familiares: quién debe qué cada mes.
-- Pegar en Supabase → SQL Editor.
-- ============================================================
CREATE TABLE IF NOT EXISTS familiares (
  id          SERIAL PRIMARY KEY,
  usuario_id  TEXT        NOT NULL,
  nombre      VARCHAR(60) NOT NULL,
  telefono    VARCHAR(30),           -- con código de país, ej. 5493624123456 (para el link de WhatsApp)
  activo      BOOLEAN     NOT NULL DEFAULT TRUE,
  creado_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (usuario_id, nombre)
);

-- Qué compra (plan de cuotas o gasto en 1 pago) le corresponde a cada familiar.
-- monto_mensual NULL = le corresponde la cuota entera; si no, la parte que le toca por mes.
CREATE TABLE IF NOT EXISTS familia_asignaciones (
  id             SERIAL PRIMARY KEY,
  familiar_id    INT           NOT NULL REFERENCES familiares(id) ON DELETE CASCADE,
  cuota_plan_id  INT           REFERENCES cuotas_plan(id) ON DELETE CASCADE,
  movimiento_id  INT           REFERENCES movimientos(id) ON DELETE CASCADE,
  monto_mensual  NUMERIC(14,2),
  nota           TEXT,
  creado_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  CHECK (cuota_plan_id IS NOT NULL OR movimiento_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_familia_asig_plan ON familia_asignaciones (cuota_plan_id);
CREATE INDEX IF NOT EXISTS idx_familia_asig_mov  ON familia_asignaciones (movimiento_id);

ALTER TABLE familiares           ENABLE ROW LEVEL SECURITY;
ALTER TABLE familia_asignaciones ENABLE ROW LEVEL SECURITY;

-- Familiares que ya aparecen en la planilla
INSERT INTO familiares (usuario_id, nombre) VALUES
  ('6917831447', 'Papá'), ('6917831447', 'Mamá'), ('6917831447', 'Pauli'), ('6917831447', 'Marian')
ON CONFLICT DO NOTHING;
