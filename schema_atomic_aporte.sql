-- ============================================================
-- MIGRACIÓN: función RPC para aporte atómico a objetivos
-- Elimina la race condition del read-modify-write en PUT /api/objetivos
-- ============================================================

CREATE OR REPLACE FUNCTION incrementar_objetivo(
  obj_id    INTEGER,
  p_usuario TEXT,
  incremento NUMERIC
)
RETURNS SETOF objetivos_ahorro
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  UPDATE objetivos_ahorro
  SET monto_actual = monto_actual + incremento
  WHERE id = obj_id
    AND usuario_id = p_usuario
    AND activo = TRUE
  RETURNING *;
END;
$$;
