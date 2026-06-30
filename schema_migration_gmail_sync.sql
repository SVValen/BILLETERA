-- ============================================================
-- BILLETERA — Auto-registro de gastos vía email Santander (IMAP)
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Credenciales IMAP por usuario (Fase 1: carga manual, sin wizard de bot)
-- Nunca loguear gmail_app_password.
CREATE TABLE IF NOT EXISTS usuario_gmail_config (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL UNIQUE,
  gmail_email TEXT NOT NULL,
  gmail_app_password TEXT NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  creado_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE usuario_gmail_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS usuario_gmail_config_all ON usuario_gmail_config;
CREATE POLICY usuario_gmail_config_all ON usuario_gmail_config FOR ALL USING (true);

-- Dedup de mails ya procesados (por Message-ID)
CREATE TABLE IF NOT EXISTS email_procesados (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  message_id TEXT NOT NULL,
  tipo_detectado TEXT,
  movimiento_id INT REFERENCES movimientos(id) ON DELETE SET NULL,
  cuota_plan_id INT REFERENCES cuotas_plan(id) ON DELETE SET NULL,
  procesado_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (usuario_id, message_id)
);

ALTER TABLE email_procesados ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS email_procesados_all ON email_procesados;
CREATE POLICY email_procesados_all ON email_procesados FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_email_procesados_usuario ON email_procesados(usuario_id);

-- Mapeo aprendido de "terminada en NNNN" → tarjeta. tarjeta_id NULL = pregunta pendiente
-- (mismo patrón de marcador transitorio que colchon_mensual.tope_variable / tarjeta_pagos.monto_pagado)
CREATE TABLE IF NOT EXISTS tarjeta_last4_map (
  id SERIAL PRIMARY KEY,
  usuario_id BIGINT NOT NULL,
  last4 VARCHAR(4) NOT NULL,
  tarjeta_id INT REFERENCES tarjetas(id) ON DELETE CASCADE,
  creado_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (usuario_id, last4)
);

ALTER TABLE tarjeta_last4_map ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tarjeta_last4_map_all ON tarjeta_last4_map;
CREATE POLICY tarjeta_last4_map_all ON tarjeta_last4_map FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_tarjeta_last4_map_usuario ON tarjeta_last4_map(usuario_id);
