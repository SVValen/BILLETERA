-- ============================================================
-- BILLETERA v2 — Transferencias desde Santander (2026-10-07)
-- Cada transferencia que llega por mail queda acá, NO como gasto: el bot pregunta
-- qué se pagó con ella (resumen de tarjeta, cuota de préstamo, alquiler), si fue un
-- gasto real o un pase entre cuentas propias. Así no se carga dos veces lo que ya
-- se marcó pagado desde el dashboard. Pegar en Supabase → SQL Editor.
-- ============================================================
CREATE TABLE IF NOT EXISTS transferencias (
  id             SERIAL PRIMARY KEY,
  usuario_id     BIGINT        NOT NULL,
  fecha          DATE          NOT NULL,
  monto          NUMERIC(14,2) NOT NULL CHECK (monto > 0),
  destinatario   TEXT,
  cbu            TEXT,
  -- pendiente | pago | gasto | propia
  estado         TEXT          NOT NULL DEFAULT 'pendiente',
  -- a qué se aplicó: 'tarjeta:<id>:<YYYY-MM>' | 'prestamo:<cuota_id>' | 'alquiler:<YYYY-MM>'
  aplicada_a     TEXT,
  movimiento_id  INT,
  creado_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_transferencias_usuario ON transferencias (usuario_id, estado);
CREATE INDEX IF NOT EXISTS idx_transferencias_cbu ON transferencias (usuario_id, cbu);
ALTER TABLE transferencias ENABLE ROW LEVEL SECURITY;
