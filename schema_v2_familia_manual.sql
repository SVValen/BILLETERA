-- ============================================================
-- BILLETERA v2 — Cuotas familia: entradas manuales (2026-10-07)
-- Cosas que se le cobran a un familiar y que no salen de una compra con tarjeta cargada
-- (o que van agrupadas distinto). Solo se ven en el panel Cuotas familia: no tocan la
-- planilla ni los totales del mes. Pegar en Supabase → SQL Editor.
-- ============================================================
CREATE TABLE IF NOT EXISTS familia_manual (
  id           SERIAL PRIMARY KEY,
  familiar_id  INT           NOT NULL REFERENCES familiares(id) ON DELETE CASCADE,
  descripcion  TEXT          NOT NULL,
  monto        NUMERIC(14,2) NOT NULL CHECK (monto > 0),   -- lo que te pasa por mes
  mes_primera  VARCHAR(7)    NOT NULL,                     -- 'YYYY-MM' de la cuota 1
  num_cuotas   INT           NOT NULL DEFAULT 1 CHECK (num_cuotas >= 1),
  creado_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_familia_manual_familiar ON familia_manual (familiar_id);
ALTER TABLE familia_manual ENABLE ROW LEVEL SECURITY;
