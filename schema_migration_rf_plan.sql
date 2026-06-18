-- ============================================================
-- Migración: Mejorar posiciones_rf para tracking detallado
-- ============================================================

-- Agregar columnas para tracking de plan_renta y detalles
ALTER TABLE posiciones_rf
  ADD COLUMN IF NOT EXISTS broker VARCHAR(50),        -- IOL, Balanz, Santander, otro
  ADD COLUMN IF NOT EXISTS precio_entrada DECIMAL(15,4),  -- precio de compra del instrumento
  ADD COLUMN IF NOT EXISTS cantidad DECIMAL(15,2),         -- cantidad de instrumentos (ej: 100 bonos)
  ADD COLUMN IF NOT EXISTS comisiones DECIMAL(15,2),       -- comisiones pagadas
  ADD COLUMN IF NOT EXISTS rendimiento_acumulado DECIMAL(15,2); -- rendimiento en USD acumulado

-- Índice para buscar posiciones por broker (para alertas)
CREATE INDEX IF NOT EXISTS idx_posrf_broker ON posiciones_rf (usuario_id, broker);

-- Agregar columna a portafolios para asociar plan_renta con portafolio final
ALTER TABLE portafolios
  ADD COLUMN IF NOT EXISTS plan_renta_id INT,
  ADD COLUMN IF NOT EXISTS broker_preferido VARCHAR(50),
  ADD COLUMN IF NOT EXISTS meta_renta_mensual_usd DECIMAL(15,2);

COMMENT ON COLUMN posiciones_rf.broker IS 'Broker donde se compró: IOL, Balanz, Santander, otro';
COMMENT ON COLUMN posiciones_rf.precio_entrada IS 'Precio a que se compró (en ARS o USD según instrumento)';
COMMENT ON COLUMN posiciones_rf.cantidad IS 'Cantidad de instrumentos comprados (para calcular rendimiento)';
COMMENT ON COLUMN posiciones_rf.rendimiento_acumulado IS 'Rendimiento en USD acumulado desde compra';
