-- ============================================================
-- MIGRACIÓN: capital_ars en portafolios + tabla aportes_portafolio
-- Aplicar en Supabase SQL Editor
-- ============================================================

-- capital en ARS (además del USD ya existente)
ALTER TABLE portafolios
  ADD COLUMN IF NOT EXISTS capital_ars DECIMAL(14,2) NOT NULL DEFAULT 0;

-- historial de aportes por portafolio
CREATE TABLE IF NOT EXISTS aportes_portafolio (
  id            SERIAL PRIMARY KEY,
  portafolio_id INT NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  usuario_id    BIGINT NOT NULL,
  monto_usd     DECIMAL(14,2),
  monto_ars     DECIMAL(14,2),
  tipo_cambio_mep DECIMAL(10,2),
  fecha         DATE NOT NULL DEFAULT CURRENT_DATE,
  creado_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aportes_portafolio
  ON aportes_portafolio (portafolio_id, usuario_id);

ALTER TABLE aportes_portafolio ENABLE ROW LEVEL SECURITY;
CREATE POLICY allow_all_aportes ON aportes_portafolio FOR ALL USING (true);
