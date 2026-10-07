-- ============================================================
-- BILLETERA v2 — Cierres variables de tarjeta (2026-10-07)
-- Santander y BBVA cierran entre el 29 y el 2 según el mes: el bot pregunta la fecha
-- y el mes de resumen de cada compra sale de la fecha real de cierre.
-- Pegar en Supabase → SQL Editor.
-- ============================================================
ALTER TABLE tarjetas ADD COLUMN IF NOT EXISTS cierre_variable BOOLEAN NOT NULL DEFAULT FALSE;

-- Un cierre por tarjeta y por resumen. mes_resumen = mes en que se paga ese resumen.
-- fecha_cierre NULL = el bot ya preguntó y está esperando la respuesta.
CREATE TABLE IF NOT EXISTS tarjeta_cierres (
  id            SERIAL PRIMARY KEY,
  tarjeta_id    INT         NOT NULL REFERENCES tarjetas(id) ON DELETE CASCADE,
  mes_resumen   VARCHAR(7)  NOT NULL,
  fecha_cierre  DATE,
  preguntado_at TIMESTAMPTZ,
  creado_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tarjeta_id, mes_resumen)
);
ALTER TABLE tarjeta_cierres ENABLE ROW LEVEL SECURITY;

UPDATE tarjetas SET cierre_variable = TRUE WHERE nombre IN ('Santander', 'BBVA');
