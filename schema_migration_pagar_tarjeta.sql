-- ============================================================
-- BILLETERA — /pagar_tarjeta: resumen mensual por tarjeta
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Marca los movimientos que son el pago del resumen (no una compra)
ALTER TABLE movimientos ADD COLUMN IF NOT EXISTS es_pago_tarjeta BOOLEAN NOT NULL DEFAULT FALSE;

-- Categoría dedicada para el pago de resúmenes
INSERT INTO categorias (nombre, emoji) VALUES ('Pago Tarjeta', '🧾') ON CONFLICT (nombre) DO NOTHING;

-- Registro de pagos de resumen por tarjeta y mes
CREATE TABLE IF NOT EXISTS tarjeta_pagos (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  tarjeta_id INT NOT NULL REFERENCES tarjetas(id) ON DELETE CASCADE,
  mes_resumen VARCHAR(7) NOT NULL,
  monto_calculado DECIMAL(14,2) NOT NULL,
  monto_pagado DECIMAL(14,2),
  fecha_pago DATE,
  movimiento_id INT REFERENCES movimientos(id) ON DELETE SET NULL,
  creado_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (usuario_id, tarjeta_id, mes_resumen)
);

ALTER TABLE tarjeta_pagos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tarjeta_pagos_all ON tarjeta_pagos;
CREATE POLICY tarjeta_pagos_all ON tarjeta_pagos FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_tarjeta_pagos_usuario ON tarjeta_pagos(usuario_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_mes_resumen_tarjeta ON movimientos(usuario_id, mes_resumen, tarjeta_id);
