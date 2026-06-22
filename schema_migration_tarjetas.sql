-- ============================================================
-- Fase 5 — Tarjetas, mes de resumen y colchón de tarjetas
-- Aplicar en Supabase SQL Editor (después de schema_migration_aportes.sql)
-- ============================================================

-- ── Tarjetas del usuario ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tarjetas (
  id          SERIAL PRIMARY KEY,
  usuario_id  BIGINT       NOT NULL,
  nombre      VARCHAR(50)  NOT NULL,
  dia_cierre  INT          CHECK (dia_cierre BETWEEN 1 AND 28),  -- NULL mientras wizard pendiente
  activa      BOOLEAN      NOT NULL DEFAULT TRUE,
  creado_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
  UNIQUE (usuario_id, nombre)
);

ALTER TABLE tarjetas ENABLE ROW LEVEL SECURITY;
CREATE POLICY allow_all_tarjetas ON tarjetas FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_tarjetas_usuario ON tarjetas (usuario_id, activa);

-- ── Movimientos: columnas para tarjeta y mes de resumen ──────────────────────
-- fecha_compra: cuándo se hizo la compra (= fecha existente para gastos normales)
-- mes_resumen:  mes en que se paga el resumen, calculado según dia_cierre
-- tarjeta_id:   NULL = efectivo

ALTER TABLE movimientos
  ADD COLUMN IF NOT EXISTS tarjeta_id   INT  REFERENCES tarjetas(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS fecha_compra DATE,
  ADD COLUMN IF NOT EXISTS mes_resumen  VARCHAR(7);  -- 'YYYY-MM'

CREATE INDEX IF NOT EXISTS idx_movimientos_mes_resumen ON movimientos (usuario_id, mes_resumen);
CREATE INDEX IF NOT EXISTS idx_movimientos_tarjeta ON movimientos (tarjeta_id);

-- ── Cuotas: agregar tarjeta ───────────────────────────────────────────────────
ALTER TABLE cuotas_plan
  ADD COLUMN IF NOT EXISTS tarjeta_id INT REFERENCES tarjetas(id) ON DELETE SET NULL;

-- ── Portafolios: propósito opcional ──────────────────────────────────────────
ALTER TABLE portafolios
  ADD COLUMN IF NOT EXISTS proposito VARCHAR(30);
-- NULL = portafolio general; 'colchon_tarjetas' = colchón de tarjetas

-- ── Colchón mensual ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS colchon_mensual (
  id                    SERIAL PRIMARY KEY,
  usuario_id            BIGINT          NOT NULL,
  portafolio_id         INT             NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  mes                   VARCHAR(7)      NOT NULL,   -- 'YYYY-MM'
  tope_variable         DECIMAL(14,2),              -- límite de gasto variable con TC fijado por usuario
  tope_sugerido_claude  DECIMAL(14,2),              -- sugerencia de Claude (si la hay)
  razon_sugerencia      TEXT,                       -- explicación de Claude
  creado_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
  UNIQUE (portafolio_id, mes)
);

ALTER TABLE colchon_mensual ENABLE ROW LEVEL SECURITY;
CREATE POLICY allow_all_colchon ON colchon_mensual FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_colchon_usuario_mes ON colchon_mensual (usuario_id, mes);
