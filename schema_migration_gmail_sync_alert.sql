-- ============================================================
-- BILLETERA — Aviso de fallo de login IMAP (Gmail sync)
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Antes, un fallo de login IMAP (ej. app password de Gmail vencida/revocada)
-- quedaba silencioso: solo un log que nadie ve. Esta columna trackea el último
-- aviso enviado al usuario por Telegram para poder debounced (máx. 1 aviso/12h)
-- sin spamear en cada corrida del cron (cada 20 min).
ALTER TABLE usuario_gmail_config
  ADD COLUMN IF NOT EXISTS ultimo_aviso_error_at TIMESTAMP;
