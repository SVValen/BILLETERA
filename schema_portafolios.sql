-- ============================================================
-- BILLETERA — Fase 1: Refactor a Portafolios Múltiples
-- ============================================================
-- Entorno de desarrollo: las tablas viejas se dropean sin
-- migración de datos.
--
-- NO TOCA: movimientos, categorias, recurrentes, cuotas,
-- presupuestos, objetivos_ahorro (módulo de gastos intacto).
-- ============================================================

-- ------------------------------------------------------------
-- 0. DROP de tablas viejas del módulo de inversiones
-- ------------------------------------------------------------

DROP TABLE IF EXISTS decisiones_inversion CASCADE;
DROP TABLE IF EXISTS recomendaciones CASCADE;
DROP TABLE IF EXISTS posiciones_rf CASCADE;
DROP TABLE IF EXISTS usuario_activos CASCADE;
DROP TABLE IF EXISTS perfiles_inversion CASCADE;

-- activos e instrumentos_rf se conservan intactas (catálogo global).

-- ------------------------------------------------------------
-- 1. TABLA: portafolios
-- ------------------------------------------------------------

CREATE TABLE portafolios (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,

  tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('conservador', 'pasivo', 'crecimiento', 'oportunista')),

  nombre_sugerido VARCHAR(100),
  nombre_personalizado VARCHAR(100),

  objetivo VARCHAR(50),
  plazo VARCHAR(20),
  moneda_preferida VARCHAR(10) DEFAULT 'USD',
  capital_usd DECIMAL(14,2) DEFAULT 0,
  asignacion_rf_pct DECIMAL(5,2) DEFAULT 0,

  estado_wizard VARCHAR(40) NOT NULL DEFAULT 'configurando_objetivos',

  activo BOOLEAN NOT NULL DEFAULT TRUE,

  creado_at TIMESTAMP NOT NULL DEFAULT NOW(),
  actualizado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_portafolios_usuario_tipo_activo
  ON portafolios (usuario_id, tipo)
  WHERE activo = TRUE;

CREATE INDEX idx_portafolios_usuario ON portafolios (usuario_id);

-- ------------------------------------------------------------
-- 2. TABLA: portafolio_activos (ex usuario_activos)
-- ------------------------------------------------------------

CREATE TABLE portafolio_activos (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  portafolio_id INT NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  activo_id INT NOT NULL REFERENCES activos(id) ON DELETE CASCADE,

  porcentaje_objetivo DECIMAL(5,2),
  monto_usd DECIMAL(14,2) DEFAULT 0,

  creado_at TIMESTAMP NOT NULL DEFAULT NOW(),

  UNIQUE (portafolio_id, activo_id)
);

CREATE INDEX idx_portafolio_activos_usuario ON portafolio_activos (usuario_id, portafolio_id);

-- ------------------------------------------------------------
-- 3. TABLA: posiciones_rf
-- ------------------------------------------------------------

CREATE TABLE posiciones_rf (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  portafolio_id INT NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  instrumento_id INT NOT NULL REFERENCES instrumentos_rf(id) ON DELETE CASCADE,

  monto_ars DECIMAL(14,2) NOT NULL,
  monto_usd_entrada DECIMAL(14,2) NOT NULL,
  tna_contratada DECIMAL(6,2),

  fecha_entrada DATE NOT NULL DEFAULT CURRENT_DATE,
  fecha_vencimiento DATE,

  estado VARCHAR(20) NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'cerrada', 'vencida')),
  fecha_cierre DATE,
  monto_ars_final DECIMAL(14,2),

  creado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_posiciones_rf_usuario ON posiciones_rf (usuario_id, portafolio_id);
CREATE INDEX idx_posiciones_rf_vencimiento ON posiciones_rf (fecha_vencimiento) WHERE estado = 'abierta';

-- ------------------------------------------------------------
-- 4. TABLA: recomendaciones
-- ------------------------------------------------------------

CREATE TABLE recomendaciones (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  portafolio_id INT NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  activo_id INT NOT NULL REFERENCES activos(id) ON DELETE CASCADE,

  accion VARCHAR(10) NOT NULL CHECK (accion IN ('comprar', 'vender')),
  razon TEXT,
  confianza INT CHECK (confianza BETWEEN 1 AND 10),

  rsi_en_momento DECIMAL(5,2),
  tendencia_en_momento VARCHAR(20),

  estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aceptada', 'rechazada', 'expirada')),

  generado_at TIMESTAMP NOT NULL DEFAULT NOW(),
  decidido_at TIMESTAMP
);

CREATE INDEX idx_recomendaciones_usuario ON recomendaciones (usuario_id, portafolio_id);
CREATE INDEX idx_recomendaciones_pendientes ON recomendaciones (portafolio_id, activo_id) WHERE estado = 'pendiente';

-- ------------------------------------------------------------
-- 5. TABLA: decisiones_inversion
-- ------------------------------------------------------------

CREATE TABLE decisiones_inversion (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  portafolio_id INT NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  recomendacion_id INT NOT NULL REFERENCES recomendaciones(id) ON DELETE CASCADE,

  accion VARCHAR(20) NOT NULL CHECK (accion IN ('aceptada', 'rechazada')),

  precio_en_decision DECIMAL(20,8),
  precio_7_dias DECIMAL(20,8),
  precio_30_dias DECIMAL(20,8),

  resultado VARCHAR(20) CHECK (resultado IN ('exitoso', 'fallido', 'neutral', 'pendiente')),

  creado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_decisiones_usuario ON decisiones_inversion (usuario_id, portafolio_id);

-- ------------------------------------------------------------
-- 6. RLS — mismo patrón permisivo que el resto del proyecto
--    (deuda técnica conocida, no se corrige en este plan)
-- ------------------------------------------------------------

ALTER TABLE portafolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE portafolio_activos ENABLE ROW LEVEL SECURITY;
ALTER TABLE posiciones_rf ENABLE ROW LEVEL SECURITY;
ALTER TABLE recomendaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisiones_inversion ENABLE ROW LEVEL SECURITY;

CREATE POLICY allow_all_portafolios ON portafolios FOR ALL USING (true);
CREATE POLICY allow_all_portafolio_activos ON portafolio_activos FOR ALL USING (true);
CREATE POLICY allow_all_posiciones_rf ON posiciones_rf FOR ALL USING (true);
CREATE POLICY allow_all_recomendaciones ON recomendaciones FOR ALL USING (true);
CREATE POLICY allow_all_decisiones ON decisiones_inversion FOR ALL USING (true);
