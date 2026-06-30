-- ============================================================
-- BILLETERA — Editar monto de un recurrente antes de confirmar
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Marcador transitorio: true mientras el bot espera que el usuario
-- responda con el nuevo monto por texto (mismo patrón que
-- colchon_mensual.tope_variable IS NULL / tarjeta_pagos.monto_pagado IS NULL)
ALTER TABLE recurrentes ADD COLUMN IF NOT EXISTS esperando_edicion_monto BOOLEAN NOT NULL DEFAULT FALSE;
