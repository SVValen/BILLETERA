-- Marca de la última lectura completa de mails: la próxima corrida busca desde ahí
-- (antes la ventana era fija de 5 días y si el cron se caía se perdían mails).
alter table usuario_gmail_config add column if not exists ultimo_sync_at timestamptz;
-- Arranca en la última corrida conocida para no reprocesar el pasado.
update usuario_gmail_config set ultimo_sync_at = coalesce(ultimo_sync_at, now()) where activo;
