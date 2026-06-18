-- ============================================================
-- BILLETERA — Reset completo de base de datos
-- Estado: post-Fase 1 (portafolios múltiples)
-- Ejecutar en Supabase → SQL Editor
-- ⚠️  BORRA TODOS LOS DATOS — solo para desarrollo
-- ============================================================

-- ------------------------------------------------------------
-- 0. DROP de todas las tablas (CASCADE maneja FK)
-- ------------------------------------------------------------

DROP TABLE IF EXISTS decisiones_inversion    CASCADE;
DROP TABLE IF EXISTS recomendaciones         CASCADE;
DROP TABLE IF EXISTS portafolio_activos      CASCADE;
DROP TABLE IF EXISTS posiciones_rf           CASCADE;
DROP TABLE IF EXISTS portafolios             CASCADE;
DROP TABLE IF EXISTS precios_historicos      CASCADE;
DROP TABLE IF EXISTS instrumentos_rf         CASCADE;
DROP TABLE IF EXISTS keywords_aprendidas     CASCADE;
DROP TABLE IF EXISTS cuotas_plan             CASCADE;
DROP TABLE IF EXISTS recurrentes             CASCADE;
DROP TABLE IF EXISTS presupuestos            CASCADE;
DROP TABLE IF EXISTS objetivos_ahorro        CASCADE;
DROP TABLE IF EXISTS movimientos             CASCADE;
DROP TABLE IF EXISTS perfiles                CASCADE;
DROP TABLE IF EXISTS categorias              CASCADE;
-- tablas viejas por si quedaron restos
DROP TABLE IF EXISTS activos                 CASCADE;
DROP TABLE IF EXISTS usuario_activos         CASCADE;
DROP TABLE IF EXISTS perfiles_inversion      CASCADE;

DROP FUNCTION IF EXISTS set_updated_at() CASCADE;

-- ------------------------------------------------------------
-- 1. categorias
-- ------------------------------------------------------------

CREATE TABLE categorias (
  id                  SERIAL PRIMARY KEY,
  nombre              VARCHAR(50) UNIQUE NOT NULL,
  emoji               VARCHAR(10),
  presupuesto_mensual DECIMAL(10,2)
);

ALTER TABLE categorias ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all_categorias" ON categorias FOR ALL USING (true) WITH CHECK (true);

INSERT INTO categorias (id, nombre, emoji) VALUES
  (1,  'Supermercado',       '🛒'),
  (2,  'Transporte',         '🚗'),
  (3,  'Comida',             '🍽️'),
  (4,  'Servicios',          '💡'),
  (5,  'Entretenimiento',    '🎬'),
  (6,  'Salud',              '🏥'),
  (7,  'Otros',              '📌'),
  (8,  'Ropa',               '👕'),
  (9,  'Educación',          '📚'),
  (10, 'Vivienda',           '🏠'),
  (11, 'Mascotas',           '🐾'),
  (12, 'Viajes',             '✈️'),
  (13, 'Seguros',            '🛡️'),
  (14, 'Inversiones',        '💰'),
  (15, 'Compras Online',     '💳'),
  (16, 'Belleza & Bienestar','✨'),
  (17, 'Ingresos',           '💵'),
  (18, 'Suscripciones',      '📱')
ON CONFLICT DO NOTHING;

-- Resetear la secuencia para que el próximo auto-id sea mayor a 18
SELECT setval('categorias_id_seq', 18);

-- ------------------------------------------------------------
-- 2. perfiles (auth.users → telegram_id)
-- ------------------------------------------------------------

CREATE TABLE perfiles (
  id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  telegram_id TEXT UNIQUE,
  nombre      TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE perfiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_perfil_select" ON perfiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "own_perfil_insert" ON perfiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "own_perfil_update" ON perfiles FOR UPDATE USING (auth.uid() = id);

-- ------------------------------------------------------------
-- 3. movimientos
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE movimientos (
  id          SERIAL PRIMARY KEY,
  usuario_id  TEXT,
  fecha       DATE          NOT NULL,
  descripcion TEXT,
  monto       DECIMAL(10,2) NOT NULL CHECK (monto > 0),
  categoria_id INT          REFERENCES categorias(id),
  tipo        VARCHAR(20)   NOT NULL CHECK (tipo IN ('gasto', 'ingreso')),
  origen      VARCHAR(50)   DEFAULT 'manual',
  estado      VARCHAR(30)   DEFAULT 'confirmado',
  created_at  TIMESTAMPTZ   DEFAULT NOW(),
  updated_at  TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX idx_movimientos_fecha      ON movimientos (fecha);
CREATE INDEX idx_movimientos_usuario    ON movimientos (usuario_id);
CREATE INDEX idx_movimientos_categoria  ON movimientos (categoria_id);

CREATE TRIGGER trigger_movimientos_updated_at
BEFORE UPDATE ON movimientos
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE movimientos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_all_movimientos" ON movimientos FOR ALL USING (true) WITH CHECK (true);

-- ------------------------------------------------------------
-- 4. presupuestos
-- ------------------------------------------------------------

CREATE TABLE presupuestos (
  id           SERIAL PRIMARY KEY,
  usuario_id   TEXT          NOT NULL,
  categoria_id INT           NOT NULL REFERENCES categorias(id),
  monto        DECIMAL(10,2) NOT NULL,
  mes          VARCHAR(7)    NOT NULL,
  created_at   TIMESTAMPTZ   DEFAULT NOW(),
  UNIQUE (usuario_id, categoria_id, mes)
);

CREATE INDEX idx_presupuestos_usuario_mes ON presupuestos(usuario_id, mes);

ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_presupuestos" ON presupuestos FOR ALL USING (true) WITH CHECK (true);

-- ------------------------------------------------------------
-- 5. objetivos_ahorro
-- ------------------------------------------------------------

CREATE TABLE objetivos_ahorro (
  id             SERIAL PRIMARY KEY,
  usuario_id     TEXT          NOT NULL,
  nombre         VARCHAR(255)  NOT NULL,
  monto_objetivo DECIMAL(10,2) NOT NULL,
  monto_actual   DECIMAL(10,2) DEFAULT 0,
  fecha_objetivo DATE          NOT NULL,
  activo         BOOLEAN       DEFAULT TRUE,
  created_at     TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX idx_objetivos_usuario ON objetivos_ahorro(usuario_id);

ALTER TABLE objetivos_ahorro ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_objetivos" ON objetivos_ahorro FOR ALL USING (true) WITH CHECK (true);

-- ------------------------------------------------------------
-- 6. recurrentes + cuotas_plan
-- ------------------------------------------------------------

CREATE TABLE recurrentes (
  id                  SERIAL PRIMARY KEY,
  usuario_id          TEXT          NOT NULL,
  descripcion         TEXT          NOT NULL,
  monto               DECIMAL(10,2) NOT NULL,
  categoria_id        INT           REFERENCES categorias(id),
  tipo                VARCHAR(20)   DEFAULT 'gasto',
  dia_del_mes         INT           NOT NULL CHECK (dia_del_mes BETWEEN 1 AND 31),
  activo              BOOLEAN       DEFAULT TRUE,
  ultimo_recordatorio DATE,
  created_at          TIMESTAMPTZ   DEFAULT NOW()
);

ALTER TABLE recurrentes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_recurrentes" ON recurrentes FOR ALL USING (true) WITH CHECK (true);

CREATE TABLE cuotas_plan (
  id                  SERIAL PRIMARY KEY,
  usuario_id          TEXT          NOT NULL,
  descripcion         TEXT          NOT NULL,
  monto_total         DECIMAL(10,2) NOT NULL,
  monto_cuota         DECIMAL(10,2) NOT NULL,
  num_cuotas          INT           NOT NULL,
  cuota_inicio        INT           NOT NULL DEFAULT 1,
  categoria_id        INT           REFERENCES categorias(id),
  fecha_primera_cuota DATE,
  activo              BOOLEAN       DEFAULT TRUE,
  created_at          TIMESTAMPTZ   DEFAULT NOW()
);

ALTER TABLE cuotas_plan ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_cuotas_plan" ON cuotas_plan FOR ALL USING (true) WITH CHECK (true);

-- ------------------------------------------------------------
-- 7. keywords_aprendidas
-- ------------------------------------------------------------

CREATE TABLE keywords_aprendidas (
  id           SERIAL PRIMARY KEY,
  usuario_id   TEXT NOT NULL,
  keyword      TEXT NOT NULL,
  categoria_id INT  NOT NULL REFERENCES categorias(id),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (usuario_id, keyword)
);

CREATE INDEX idx_keywords_usuario ON keywords_aprendidas(usuario_id, keyword);

ALTER TABLE keywords_aprendidas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_keywords" ON keywords_aprendidas FOR ALL USING (true) WITH CHECK (true);

-- ------------------------------------------------------------
-- 8. activos + precios_historicos (catálogo global de RV)
-- ------------------------------------------------------------

CREATE TABLE activos (
  id              SERIAL PRIMARY KEY,
  codigo          VARCHAR(20)  UNIQUE NOT NULL,
  nombre          VARCHAR(100),
  tipo            VARCHAR(20)  NOT NULL,   -- crypto, cedear, accion_ar, dolar
  fuente          VARCHAR(20)  NOT NULL,   -- coingecko, iol, dolarapi
  simbolo_fuente  VARCHAR(30),
  moneda          VARCHAR(10)  DEFAULT 'USD',
  activo          BOOLEAN      DEFAULT TRUE,
  precio_actual   DECIMAL(20,8),
  precio_ars      DECIMAL(20,2),
  rsi             DECIMAL(5,2),
  ema_20          DECIMAL(20,8),
  ema_50          DECIMAL(20,8),
  tendencia       VARCHAR(20),
  ultimo_update   TIMESTAMPTZ
);

ALTER TABLE activos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_activos" ON activos FOR ALL USING (true) WITH CHECK (true);

INSERT INTO activos (codigo, nombre, tipo, fuente, simbolo_fuente, moneda) VALUES
  ('BTC',   'Bitcoin',             'crypto',     'coingecko', 'bitcoin',    'USD'),
  ('ETH',   'Ethereum',            'crypto',     'coingecko', 'ethereum',   'USD'),
  ('AAPL',  'Apple (CEDEAR)',      'cedear',     'iol',       'AAPL',       'ARS'),
  ('GOOGL', 'Google (CEDEAR)',     'cedear',     'iol',       'GOOGL',      'ARS'),
  ('MSFT',  'Microsoft (CEDEAR)',  'cedear',     'iol',       'MSFT',       'ARS'),
  ('GGAL',  'Grupo Galicia',       'accion_ar',  'iol',       'GGAL',       'ARS'),
  ('YPF',   'YPF (YPFD)',          'accion_ar',  'iol',       'YPFD',       'ARS')
ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE precios_historicos (
  id        SERIAL PRIMARY KEY,
  activo_id INT           NOT NULL REFERENCES activos(id),
  precio    DECIMAL(20,8) NOT NULL,
  timestamp TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX idx_precios_activo_ts ON precios_historicos (activo_id, timestamp DESC);

ALTER TABLE precios_historicos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_precios" ON precios_historicos FOR ALL USING (true) WITH CHECK (true);

-- ------------------------------------------------------------
-- 9. instrumentos_rf (catálogo global de RF)
-- ------------------------------------------------------------

CREATE TABLE instrumentos_rf (
  id            SERIAL PRIMARY KEY,
  codigo        VARCHAR(30)   UNIQUE NOT NULL,
  nombre        VARCHAR(100),
  tipo          VARCHAR(20)   NOT NULL,   -- caucion, letra, bono_soberano, on
  moneda        VARCHAR(10)   DEFAULT 'ARS',
  plazo_dias    INT,
  vencimiento   DATE,
  ticker_iol    VARCHAR(30),
  tna_actual    DECIMAL(8,4),
  precio_actual DECIMAL(15,4),
  tir           DECIMAL(8,4),
  paridad       DECIMAL(8,4),
  ultimo_update TIMESTAMPTZ,
  activo        BOOLEAN       DEFAULT TRUE
);

ALTER TABLE instrumentos_rf ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_instrumentos_rf" ON instrumentos_rf FOR ALL USING (true) WITH CHECK (true);

INSERT INTO instrumentos_rf (codigo, nombre, tipo, moneda, plazo_dias, ticker_iol) VALUES
  ('CAUCION_1D',  'Caución 1 día',          'caucion',       'ARS', 1,    NULL),
  ('CAUCION_7D',  'Caución 7 días',          'caucion',       'ARS', 7,    NULL),
  ('CAUCION_30D', 'Caución 30 días',         'caucion',       'ARS', 30,   NULL),
  ('AL30',        'Bono AL30 (Ley AR, USD)', 'bono_soberano', 'USD', NULL, 'AL30'),
  ('GD30',        'Bono GD30 (Ley NY, USD)', 'bono_soberano', 'USD', NULL, 'GD30'),
  ('AE38',        'Bono AE38 (Ley NY, USD)', 'bono_soberano', 'USD', NULL, 'AE38'),
  ('GD35',        'Bono GD35 (Ley NY, USD)', 'bono_soberano', 'USD', NULL, 'GD35')
ON CONFLICT (codigo) DO NOTHING;

-- ------------------------------------------------------------
-- 10. portafolios
-- ------------------------------------------------------------

CREATE TABLE portafolios (
  id                   SERIAL PRIMARY KEY,
  usuario_id           BIGINT        NOT NULL,
  tipo                 VARCHAR(20)   NOT NULL CHECK (tipo IN ('conservador', 'pasivo', 'crecimiento', 'oportunista')),
  nombre_sugerido      VARCHAR(100),
  nombre_personalizado VARCHAR(100),
  objetivo             VARCHAR(50),
  plazo                VARCHAR(20),
  moneda_preferida     VARCHAR(10)   DEFAULT 'USD',
  capital_usd          DECIMAL(14,2) DEFAULT 0,
  asignacion_rf_pct    DECIMAL(5,2)  DEFAULT 0,
  renta_mensual_obj    VARCHAR(50),
  estado_wizard        VARCHAR(40)   NOT NULL DEFAULT 'configurando_objetivo',
  activo               BOOLEAN       NOT NULL DEFAULT TRUE,
  creado_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
  actualizado_at       TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_portafolios_usuario_tipo_activo
  ON portafolios (usuario_id, tipo) WHERE activo = TRUE;

CREATE INDEX idx_portafolios_usuario ON portafolios (usuario_id);

ALTER TABLE portafolios ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_portafolios" ON portafolios FOR ALL USING (true);

-- ------------------------------------------------------------
-- 11. portafolio_activos
-- ------------------------------------------------------------

CREATE TABLE portafolio_activos (
  id                  SERIAL PRIMARY KEY,
  usuario_id          BIGINT        NOT NULL,
  portafolio_id       INT           NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  activo_id           INT           NOT NULL REFERENCES activos(id) ON DELETE CASCADE,
  porcentaje_objetivo DECIMAL(5,2),
  monto_usd           DECIMAL(14,2) DEFAULT 0,
  creado_at           TIMESTAMP     NOT NULL DEFAULT NOW(),
  UNIQUE (portafolio_id, activo_id)
);

CREATE INDEX idx_portafolio_activos_usuario ON portafolio_activos (usuario_id, portafolio_id);

ALTER TABLE portafolio_activos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_portafolio_activos" ON portafolio_activos FOR ALL USING (true);

-- ------------------------------------------------------------
-- 12. posiciones_rf
-- ------------------------------------------------------------

CREATE TABLE posiciones_rf (
  id                  SERIAL PRIMARY KEY,
  usuario_id          BIGINT        NOT NULL,
  portafolio_id       INT           NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  instrumento_id      INT           NOT NULL REFERENCES instrumentos_rf(id) ON DELETE CASCADE,
  monto_ars           DECIMAL(14,2) NOT NULL,
  monto_usd_entrada   DECIMAL(14,2) NOT NULL,
  tna_contratada      DECIMAL(6,2),
  fecha_entrada       DATE          NOT NULL DEFAULT CURRENT_DATE,
  fecha_vencimiento   DATE,
  estado              VARCHAR(20)   NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'cerrada', 'vencida')),
  fecha_cierre        DATE,
  monto_ars_final     DECIMAL(14,2),
  creado_at           TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_posiciones_rf_usuario    ON posiciones_rf (usuario_id, portafolio_id);
CREATE INDEX idx_posiciones_rf_vencimiento ON posiciones_rf (fecha_vencimiento) WHERE estado = 'abierta';

ALTER TABLE posiciones_rf ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_posiciones_rf" ON posiciones_rf FOR ALL USING (true);

-- ------------------------------------------------------------
-- 13. recomendaciones
-- ------------------------------------------------------------

CREATE TABLE recomendaciones (
  id                    SERIAL PRIMARY KEY,
  usuario_id            BIGINT      NOT NULL,
  portafolio_id         INT         NOT NULL REFERENCES portafolios(id) ON DELETE CASCADE,
  activo_id             INT         NOT NULL REFERENCES activos(id)     ON DELETE CASCADE,
  accion                VARCHAR(10) NOT NULL CHECK (accion IN ('comprar', 'vender')),
  razon                 TEXT,
  confianza             INT         CHECK (confianza BETWEEN 1 AND 10),
  rsi_en_momento        DECIMAL(5,2),
  tendencia_en_momento  VARCHAR(20),
  estado                VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aceptada', 'rechazada', 'expirada')),
  generado_at           TIMESTAMP   NOT NULL DEFAULT NOW(),
  decidido_at           TIMESTAMP
);

CREATE INDEX idx_recomendaciones_usuario    ON recomendaciones (usuario_id, portafolio_id);
CREATE INDEX idx_recomendaciones_pendientes ON recomendaciones (portafolio_id, activo_id) WHERE estado = 'pendiente';

ALTER TABLE recomendaciones ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_recomendaciones" ON recomendaciones FOR ALL USING (true);

-- ------------------------------------------------------------
-- 14. decisiones_inversion
-- ------------------------------------------------------------

CREATE TABLE decisiones_inversion (
  id               SERIAL PRIMARY KEY,
  usuario_id       BIGINT      NOT NULL,
  portafolio_id    INT         NOT NULL REFERENCES portafolios(id)     ON DELETE CASCADE,
  recomendacion_id INT         NOT NULL REFERENCES recomendaciones(id) ON DELETE CASCADE,
  accion           VARCHAR(20) NOT NULL CHECK (accion IN ('aceptada', 'rechazada')),
  precio_en_decision DECIMAL(20,8),
  precio_7_dias    DECIMAL(20,8),
  precio_30_dias   DECIMAL(20,8),
  resultado        VARCHAR(20) CHECK (resultado IN ('exitoso', 'fallido', 'neutral', 'pendiente')),
  creado_at        TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_decisiones_usuario ON decisiones_inversion (usuario_id, portafolio_id);

ALTER TABLE decisiones_inversion ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_all_decisiones" ON decisiones_inversion FOR ALL USING (true);
