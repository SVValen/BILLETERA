-- Fase 6: Préstamos con adelanto de cuotas + Objetivos conectados a portafolios

-- Categoría Auto (verificar y crear si no existe)
INSERT INTO categorias (nombre, emoji) VALUES ('Auto', '🚗') ON CONFLICT (nombre) DO NOTHING;

CREATE TABLE IF NOT EXISTS prestamos (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  total_cuotas INT NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  creado_at TIMESTAMP NOT NULL DEFAULT NOW()
);
ALTER TABLE prestamos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_prestamos" ON prestamos FOR ALL USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS prestamo_cuotas (
  id SERIAL PRIMARY KEY,
  prestamo_id INT NOT NULL REFERENCES prestamos(id) ON DELETE CASCADE,
  usuario_id BIGINT NOT NULL,
  numero_cuota INT NOT NULL,
  mes_previsto VARCHAR(7) NOT NULL,
  capital DECIMAL(14,2) NOT NULL,
  monto_ordinario DECIMAL(14,2),
  monto_adelanto DECIMAL(14,2),   -- calculado en Python: ROUND(capital * 1.25, 2)
  pagado BOOLEAN NOT NULL DEFAULT FALSE,
  tipo_pago VARCHAR(20) CHECK (tipo_pago IN ('ordinaria', 'adelanto')),
  monto_pagado DECIMAL(14,2),
  fecha_pago DATE,
  movimiento_id INT REFERENCES movimientos(id) ON DELETE SET NULL,
  UNIQUE (prestamo_id, numero_cuota)
);
ALTER TABLE prestamo_cuotas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_prestamo_cuotas" ON prestamo_cuotas FOR ALL USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS idx_prestamo_cuotas_usuario ON prestamo_cuotas (usuario_id, prestamo_id);
CREATE INDEX IF NOT EXISTS idx_prestamo_cuotas_pendientes ON prestamo_cuotas (prestamo_id, pagado) WHERE pagado = FALSE;

-- Parte B: Objetivos conectados a portafolios
ALTER TABLE objetivos_ahorro
  ADD COLUMN IF NOT EXISTS portafolio_id INT REFERENCES portafolios(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS esperando_portafolio BOOLEAN DEFAULT FALSE;
