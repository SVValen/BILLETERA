-- ============================================================
-- BILLETERA: Módulo de Renta Fija
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Instrumentos de RF disponibles (referencia global, no por usuario)
CREATE TABLE IF NOT EXISTS instrumentos_rf (
  id SERIAL PRIMARY KEY,
  codigo VARCHAR(30) UNIQUE NOT NULL,   -- CAUCION_1D, LECAP_S28F6, AL30, etc.
  nombre VARCHAR(100),
  tipo VARCHAR(20) NOT NULL,            -- caucion | letra | bono_soberano | on
  moneda VARCHAR(10) DEFAULT 'ARS',     -- ARS | USD
  plazo_dias INT,                       -- 1, 7, 30 para cauciones; calculado para letras
  vencimiento DATE,                     -- NULL para cauciones renovables
  ticker_iol VARCHAR(30),               -- símbolo para IOL (S28F6, AL30, YPFD, etc.)
  tna_actual DECIMAL(8,4),              -- % TNA actual (actualizado por cron)
  precio_actual DECIMAL(15,4),          -- precio de mercado para bonos/letras
  tir DECIMAL(8,4),                     -- TIR (%) para bonos
  paridad DECIMAL(8,4),                 -- % del valor nominal para bonos
  ultimo_update TIMESTAMPTZ,
  activo BOOLEAN DEFAULT TRUE
);

-- Posiciones abiertas del usuario en RF
CREATE TABLE IF NOT EXISTS posiciones_rf (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT NOT NULL,             -- telegram_id
  instrumento_id INT REFERENCES instrumentos_rf(id) ON DELETE SET NULL,
  tipo VARCHAR(20),                     -- desnorm. para queries rápidas sin JOIN
  monto_ars DECIMAL(15,2) NOT NULL,
  monto_usd DECIMAL(15,2),              -- equivalente USD al entrar (al tipo MEP)
  tipo_cambio_entrada DECIMAL(10,2),    -- dólar MEP al momento de colocar
  tna_contratada DECIMAL(8,4),          -- TNA al momento de entrar
  fecha_entrada TIMESTAMPTZ DEFAULT NOW(),
  fecha_vencimiento DATE,               -- NULL para cauciones sin vencimiento fijo
  estado VARCHAR(20) DEFAULT 'activa',  -- activa | vencida | rescatada
  notas TEXT
);

CREATE INDEX IF NOT EXISTS idx_posrf_usuario ON posiciones_rf (usuario_id);
CREATE INDEX IF NOT EXISTS idx_posrf_estado ON posiciones_rf (estado);
CREATE INDEX IF NOT EXISTS idx_posrf_vencimiento ON posiciones_rf (fecha_vencimiento);

-- RLS permissive (mismo patrón que el resto del proyecto)
ALTER TABLE instrumentos_rf ENABLE ROW LEVEL SECURITY;
ALTER TABLE posiciones_rf ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_instrumentos_rf" ON instrumentos_rf;
CREATE POLICY "service_role_all_instrumentos_rf" ON instrumentos_rf FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_all_posiciones_rf" ON posiciones_rf;
CREATE POLICY "service_role_all_posiciones_rf" ON posiciones_rf FOR ALL USING (true) WITH CHECK (true);
