-- ============================================================
-- BILLETERA: Módulo de Inversiones
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Perfil de inversión del usuario
CREATE TABLE IF NOT EXISTS perfiles_inversion (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT NOT NULL UNIQUE,  -- telegram_id (mismo que en movimientos)
  perfil VARCHAR(20) NOT NULL DEFAULT 'moderado',  -- conservador, moderado, arriesgado (derivado por Claude)
  objetivo VARCHAR(50),                 -- ingresos_pasivos, crecimiento, cobertura, meta_especifica
  plazo VARCHAR(20),                    -- corto, mediano, largo
  capital_disponible DECIMAL(15,2),
  descripcion_libre TEXT,               -- texto libre del usuario (input para Claude)
  notas TEXT,
  estado VARCHAR(30) DEFAULT 'activo',  -- activo | configurando_plazo | configurando_capital | configurando_descripcion | configurando_activos
  creado_at TIMESTAMPTZ DEFAULT NOW(),
  actualizado_at TIMESTAMPTZ DEFAULT NOW()
);

-- Activos monitoreados
CREATE TABLE IF NOT EXISTS activos (
  id SERIAL PRIMARY KEY,
  codigo VARCHAR(20) UNIQUE NOT NULL,   -- BTC, ETH, AAPL (cedear), GGAL
  nombre VARCHAR(100),
  tipo VARCHAR(20) NOT NULL,            -- crypto, cedear, accion_ar, dolar
  fuente VARCHAR(20) NOT NULL,          -- binance, iol, dolarapi
  simbolo_fuente VARCHAR(30),           -- símbolo tal como lo usa la API origen
  moneda VARCHAR(10) DEFAULT 'USD',     -- USD o ARS
  activo BOOLEAN DEFAULT TRUE,
  -- Precio actual (actualizado por cron)
  precio_actual DECIMAL(20,8),
  precio_ars DECIMAL(20,2),
  rsi DECIMAL(5,2),
  ema_20 DECIMAL(20,8),
  ema_50 DECIMAL(20,8),
  tendencia VARCHAR(20),                -- alcista, bajista, lateral
  ultimo_update TIMESTAMPTZ
);

-- Recomendaciones generadas por Claude
CREATE TABLE IF NOT EXISTS recomendaciones (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT NOT NULL,
  activo_id INT NOT NULL REFERENCES activos(id),
  accion VARCHAR(20) NOT NULL,          -- comprar, vender, mantener
  razon TEXT,
  precio_recomendacion DECIMAL(20,8),
  rsi_momento DECIMAL(5,2),
  confianza INT CHECK (confianza BETWEEN 1 AND 10),
  estado VARCHAR(20) DEFAULT 'pendiente',  -- pendiente, aceptada, rechazada, expirada
  telegram_message_id INT,
  generado_at TIMESTAMPTZ DEFAULT NOW(),
  decidido_at TIMESTAMPTZ,
  expira_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '4 hours'
);

CREATE INDEX IF NOT EXISTS idx_rec_usuario ON recomendaciones (usuario_id);
CREATE INDEX IF NOT EXISTS idx_rec_estado ON recomendaciones (estado);

-- Decisiones del usuario (accept/reject tracking)
CREATE TABLE IF NOT EXISTS decisiones_inversion (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT NOT NULL,
  recomendacion_id INT NOT NULL REFERENCES recomendaciones(id),
  accion VARCHAR(20) NOT NULL,          -- aceptada, rechazada
  monto DECIMAL(15,2),                  -- cuánto invirtió (si aceptó)
  precio_entrada DECIMAL(20,8),
  -- Outcome tracking (actualizado por cron)
  precio_7d DECIMAL(20,8),
  precio_30d DECIMAL(20,8),
  ganancia_pct DECIMAL(8,2),
  resultado VARCHAR(20) DEFAULT 'pendiente',  -- exitoso, fallido, neutral, pendiente
  -- Vinculación con Billetera
  movimiento_id INT REFERENCES movimientos(id) ON DELETE SET NULL,
  fecha_decision TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dec_usuario ON decisiones_inversion (usuario_id);

-- Activos que cada usuario eligió monitorear
CREATE TABLE IF NOT EXISTS usuario_activos (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT NOT NULL,
  activo_id INT NOT NULL REFERENCES activos(id),
  UNIQUE(usuario_id, activo_id)
);

CREATE INDEX IF NOT EXISTS idx_ua_usuario ON usuario_activos (usuario_id);

ALTER TABLE usuario_activos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all" ON usuario_activos FOR ALL USING (true) WITH CHECK (true);

-- Historial de precios (para calcular RSI sin llamar la API N veces)
CREATE TABLE IF NOT EXISTS precios_historicos (
  id SERIAL PRIMARY KEY,
  activo_id INT NOT NULL REFERENCES activos(id),
  precio DECIMAL(20,8) NOT NULL,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_precios_activo_ts ON precios_historicos (activo_id, timestamp DESC);

-- ============================================================
-- Datos iniciales: activos a monitorear
-- ============================================================
INSERT INTO activos (codigo, nombre, tipo, fuente, simbolo_fuente, moneda) VALUES
  ('BTC',  'Bitcoin',   'crypto',    'binance', 'BTCUSDT', 'USD'),
  ('ETH',  'Ethereum',  'crypto',    'binance', 'ETHUSDT', 'USD'),
  ('USDT', 'Tether',    'dolar',     'dolarapi', 'usdt',   'USD'),
  ('AAPL', 'Apple (CEDEAR)',  'cedear', 'iol', 'AAPL',    'ARS'),
  ('GOOGL','Google (CEDEAR)', 'cedear', 'iol', 'GOOGL',   'ARS'),
  ('MSFT', 'Microsoft (CEDEAR)', 'cedear', 'iol', 'MSFT', 'ARS'),
  ('GGAL', 'Grupo Galicia', 'accion_ar', 'iol', 'GGAL',  'ARS'),
  ('YPF',  'YPF',       'accion_ar', 'iol', 'YPF',        'ARS')
ON CONFLICT (codigo) DO NOTHING;

-- RLS permissive (mismo patrón que el resto del proyecto)
ALTER TABLE perfiles_inversion ENABLE ROW LEVEL SECURITY;
ALTER TABLE activos ENABLE ROW LEVEL SECURITY;
ALTER TABLE recomendaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisiones_inversion ENABLE ROW LEVEL SECURITY;
ALTER TABLE precios_historicos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON perfiles_inversion FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON activos FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON recomendaciones FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON decisiones_inversion FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON precios_historicos FOR ALL USING (true) WITH CHECK (true);
