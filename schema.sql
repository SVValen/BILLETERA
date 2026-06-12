-- ============================================================
-- BILLETERA - Schema inicial (Fase 1 MVP)
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Categorías
CREATE TABLE IF NOT EXISTS categorias (
  id SERIAL PRIMARY KEY,
  nombre VARCHAR(50) UNIQUE NOT NULL,
  emoji VARCHAR(10),
  presupuesto_mensual DECIMAL(10, 2)
);

-- Movimientos (gastos e ingresos)
CREATE TABLE IF NOT EXISTS movimientos (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT,
  fecha DATE NOT NULL,
  descripcion TEXT,
  monto DECIMAL(10, 2) NOT NULL CHECK (monto > 0),
  categoria_id INT REFERENCES categorias (id),
  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('gasto', 'ingreso')),
  origen VARCHAR(50) DEFAULT 'manual',
  estado VARCHAR(30) DEFAULT 'confirmado',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos (fecha);
CREATE INDEX IF NOT EXISTS idx_movimientos_categoria ON movimientos (categoria_id);

-- Trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trigger_movimientos_updated_at
BEFORE UPDATE ON movimientos
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- Datos iniciales
-- ============================================================
INSERT INTO categorias (nombre, emoji, presupuesto_mensual) VALUES
  ('Supermercado',    '🛒', 15000),
  ('Transporte',      '🚗',  5000),
  ('Comida',          '🍽️', 10000),
  ('Servicios',       '💡',  8000),
  ('Entretenimiento', '🎬',  5000),
  ('Salud',           '🏥',  3000),
  ('Otros',           '📌',  NULL)
ON CONFLICT (nombre) DO NOTHING;

-- ============================================================
-- Row Level Security (básico - todos los rows visibles por ahora)
-- Activar después de agregar auth de Supabase en Fase 2
-- ============================================================
ALTER TABLE movimientos ENABLE ROW LEVEL SECURITY;
ALTER TABLE categorias ENABLE ROW LEVEL SECURITY;

-- Política temporal: service role puede leer/escribir todo
CREATE POLICY "service_role_all_movimientos"
  ON movimientos FOR ALL
  USING (true)
  WITH CHECK (true);

CREATE POLICY "service_role_all_categorias"
  ON categorias FOR ALL
  USING (true)
  WITH CHECK (true);
