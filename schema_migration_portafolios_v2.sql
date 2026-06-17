-- Migración v2: agrega columna renta_mensual_obj para el wizard tipo Pasivo
ALTER TABLE portafolios ADD COLUMN IF NOT EXISTS renta_mensual_obj VARCHAR(50);
