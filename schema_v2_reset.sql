-- ============================================================
-- BILLETERA v2 — Reset a lo simple (2026-10-06)
-- Antes de correr esto se copió todo a backup_v1.* (create table as table).
-- Mantiene: perfiles, usuario_gmail_config, tarjetas, tarjeta_last4_map,
--           prestamos + prestamo_cuotas (cronograma de amortización).
-- ============================================================

-- 1) Fuera inversiones, objetivos y colchón ------------------------------------
DROP TABLE IF EXISTS
  decisiones_inversion, recomendaciones, precios_historicos, portafolio_activos,
  posiciones_rf, instrumentos_rf, aportes_portafolio, colchon_mensual,
  objetivos_ahorro, portafolios, activos
CASCADE;

-- 2) Vaciar datos de uso --------------------------------------------------------
UPDATE prestamo_cuotas SET movimiento_id = NULL;
DELETE FROM email_procesados;
DELETE FROM tarjeta_pagos;
DELETE FROM movimientos;
DELETE FROM cuotas_plan;
DELETE FROM recurrentes;
DELETE FROM presupuestos;
DELETE FROM keywords_aprendidas;
DELETE FROM usuario_categoria_metrica;

-- 3) Rubros (categorías) alineados con el Excel ---------------------------------
-- IDs fijos: el código referencia 7 (Otros), 17 (Ingresos) y 20 (Pago Tarjeta).
DELETE FROM categorias;
INSERT INTO categorias (id, nombre, emoji) VALUES
  (1,  'Supermercado',             '🛒'),
  (2,  'Transporte',               '🚌'),
  (3,  'Comida',                   '🍽️'),
  (4,  'Servicios',                '💡'),
  (5,  'Salidas',                  '🎉'),
  (6,  'Salud y cuidado personal', '💅'),
  (7,  'Otros',                    '📌'),
  (8,  'Ropa',                     '👕'),
  (9,  'Educación',                '📚'),
  (10, 'Departamento',             '🏠'),
  (11, 'Mascotas',                 '🐾'),
  (12, 'Viajes',                   '✈️'),
  (13, 'Seguros e impuestos',      '🛡️'),
  (14, 'Tecnología',               '💻'),
  (15, 'Compras familia',          '👨‍👩‍👧'),
  (16, 'Regalos',                  '🎁'),
  (17, 'Ingresos',                 '💰'),
  (18, 'Suscripciones',            '🔁'),
  (19, 'Auto',                     '🚗'),
  (20, 'Pago Tarjeta',             '💳'),
  (21, 'Farmacia',                 '💊'),
  (22, 'Mudanza',                  '📦');
SELECT setval(pg_get_serial_sequence('categorias', 'id'), 22);

-- 4) Movimientos: columnas del Excel -------------------------------------------
-- grupo  = "Sub Categoria" del Excel: Sueldo, Cuotas familia, Préstamo,
--          Tarjeta Naranja/Santander/BBVA/MP, Alquiler, Efectivo
-- categoria_id = rubro ("Sub-sub categoria")
-- mes_resumen  = mes en que impacta/se paga (la hoja del Excel); obligatorio en v2
ALTER TABLE movimientos
  ALTER COLUMN monto TYPE NUMERIC(14,2),
  ADD COLUMN IF NOT EXISTS grupo             VARCHAR(40) NOT NULL DEFAULT 'Efectivo',
  ADD COLUMN IF NOT EXISTS moneda            VARCHAR(3)  NOT NULL DEFAULT 'ARS' CHECK (moneda IN ('ARS','USD')),
  ADD COLUMN IF NOT EXISTS monto_original    NUMERIC(14,2),   -- en la moneda original (USD)
  ADD COLUMN IF NOT EXISTS tipo_cambio       NUMERIC(12,4),   -- ARS por USD usado para convertir
  ADD COLUMN IF NOT EXISTS cuota_nro         INT,
  ADD COLUMN IF NOT EXISTS cuota_total       INT,
  ADD COLUMN IF NOT EXISTS cuota_plan_id     INT REFERENCES cuotas_plan(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS prestamo_id       INT REFERENCES prestamos(id)   ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS debito_automatico BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_movimientos_usuario_mes ON movimientos (usuario_id, mes_resumen, grupo);

ALTER TABLE cuotas_plan
  ALTER COLUMN monto_total TYPE NUMERIC(14,2),
  ALTER COLUMN monto_cuota TYPE NUMERIC(14,2),
  ADD COLUMN IF NOT EXISTS moneda VARCHAR(3) NOT NULL DEFAULT 'ARS';

ALTER TABLE recurrentes
  ALTER COLUMN monto TYPE NUMERIC(14,2),
  ADD COLUMN IF NOT EXISTS moneda            VARCHAR(3) NOT NULL DEFAULT 'ARS',
  ADD COLUMN IF NOT EXISTS grupo             VARCHAR(40),
  ADD COLUMN IF NOT EXISTS debito_automatico BOOLEAN NOT NULL DEFAULT FALSE;

-- 5) Cotizaciones del dólar (BCRA) ---------------------------------------------
CREATE TABLE IF NOT EXISTS cotizaciones (
  fecha  DATE         NOT NULL,
  fuente VARCHAR(30)  NOT NULL,   -- 'bcra_a3500' | 'manual'
  valor  NUMERIC(12,4) NOT NULL,
  creado_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (fecha, fuente)
);
ALTER TABLE cotizaciones ENABLE ROW LEVEL SECURITY;
