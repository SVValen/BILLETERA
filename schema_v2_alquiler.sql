-- ============================================================
-- BILLETERA v2 — Módulo de alquiler (2026-10-07)
-- Pegar completo en Supabase → SQL Editor. Incluye el trigger de grupo
-- (schema_v2_grupo_trigger.sql), así que alcanza con correr este archivo.
-- ============================================================

-- 1) Descuentos de alquiler (arreglos, luz, etc.) van como líneas negativas
--    dentro del grupo Alquiler: el CHECK pasa de monto > 0 a monto <> 0.
ALTER TABLE movimientos DROP CONSTRAINT IF EXISTS movimientos_monto_check;
ALTER TABLE movimientos ADD CONSTRAINT movimientos_monto_check
  CHECK (monto <> 0 AND (monto > 0 OR grupo = 'Alquiler'));

-- 2) Estado de pago: para gastos que se generan como pendientes (alquiler,
--    expensas, agua, gas) y se marcan pagados desde el bot o el dashboard.
ALTER TABLE movimientos
  ADD COLUMN IF NOT EXISTS pagado    BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS estimado  BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS concepto  VARCHAR(30);   -- alquiler | expensas | agua | gas | luz | descuento

-- 3) Contrato de alquiler
CREATE TABLE IF NOT EXISTS alquiler_contrato (
  id                 SERIAL PRIMARY KEY,
  usuario_id         TEXT          NOT NULL,
  direccion          TEXT,
  inicio             DATE          NOT NULL,          -- inicio de la locación
  primer_mes_ajuste  VARCHAR(7)    NOT NULL,          -- 'YYYY-MM' del primer mes con canon ajustado
  meses_ajuste       INT           NOT NULL DEFAULT 4,
  indice             VARCHAR(10)   NOT NULL DEFAULT 'IPC',
  canon_inicial      NUMERIC(14,2) NOT NULL,
  dia_vencimiento    INT           NOT NULL DEFAULT 10,
  unidad_expensas    TEXT,                            -- cómo aparece en la liquidación (p. ej. 'SOSA VALENTINA')
  activo             BOOLEAN       NOT NULL DEFAULT TRUE,
  creado_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Historial del canon: un registro por período de ajuste
CREATE TABLE IF NOT EXISTS alquiler_canon (
  id           SERIAL PRIMARY KEY,
  contrato_id  INT           NOT NULL REFERENCES alquiler_contrato(id) ON DELETE CASCADE,
  desde_mes    VARCHAR(7)    NOT NULL,   -- 'YYYY-MM'
  monto        NUMERIC(14,2) NOT NULL,
  estimado     BOOLEAN       NOT NULL DEFAULT FALSE,
  detalle      TEXT,                     -- p. ej. 'IPC jul-oct 2026: +7,41%'
  creado_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  UNIQUE (contrato_id, desde_mes)
);

ALTER TABLE alquiler_contrato ENABLE ROW LEVEL SECURITY;
ALTER TABLE alquiler_canon    ENABLE ROW LEVEL SECURITY;

INSERT INTO alquiler_contrato (usuario_id, direccion, inicio, primer_mes_ajuste, canon_inicial, unidad_expensas)
SELECT '6917831447', 'Av. Wilde 445, 5° D + cochera 8', DATE '2026-08-13', '2026-12', 650000, 'SOSA VALENTINA'
WHERE NOT EXISTS (SELECT 1 FROM alquiler_contrato WHERE usuario_id = '6917831447');

INSERT INTO alquiler_canon (contrato_id, desde_mes, monto, estimado, detalle)
SELECT id, '2026-08', 650000, FALSE, 'Canon inicial (contrato)' FROM alquiler_contrato WHERE usuario_id = '6917831447'
ON CONFLICT DO NOTHING;
INSERT INTO alquiler_canon (contrato_id, desde_mes, monto, estimado, detalle)
SELECT id, '2026-12', 700000, TRUE, 'Estimado hasta tener el IPC de octubre' FROM alquiler_contrato WHERE usuario_id = '6917831447'
ON CONFLICT DO NOTHING;

-- 4) Marcar conceptos de alquiler ya cargados
UPDATE movimientos SET concepto = lower(descripcion)
WHERE grupo = 'Alquiler' AND lower(descripcion) IN ('alquiler','expensas','agua','gas','luz');

-- 5) Grupo automático según tarjeta / préstamo (ver schema_v2_grupo_trigger.sql)
CREATE OR REPLACE FUNCTION movimientos_set_grupo()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.tarjeta_id IS NOT NULL THEN
    SELECT 'Tarjeta ' || nombre INTO NEW.grupo FROM tarjetas WHERE id = NEW.tarjeta_id;
  ELSIF NEW.prestamo_id IS NOT NULL THEN
    NEW.grupo := 'Préstamo';
  ELSIF NEW.grupo LIKE 'Tarjeta %' THEN
    NEW.grupo := 'Efectivo';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

DROP TRIGGER IF EXISTS trigger_movimientos_grupo ON movimientos;
CREATE TRIGGER trigger_movimientos_grupo
BEFORE INSERT OR UPDATE OF tarjeta_id, prestamo_id ON movimientos
FOR EACH ROW EXECUTE FUNCTION movimientos_set_grupo();
