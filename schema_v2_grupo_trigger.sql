-- ============================================================
-- BILLETERA v2 — grupo automático según tarjeta / préstamo
-- Cualquier camino que inserte o actualice un movimiento (bot, mails, dashboard)
-- queda con el grupo correcto sin tener que acordarse de setearlo.
-- ============================================================
CREATE OR REPLACE FUNCTION movimientos_set_grupo()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.tarjeta_id IS NOT NULL THEN
    SELECT 'Tarjeta ' || nombre INTO NEW.grupo FROM tarjetas WHERE id = NEW.tarjeta_id;
  ELSIF NEW.prestamo_id IS NOT NULL THEN
    NEW.grupo := 'Préstamo';
  ELSIF NEW.grupo LIKE 'Tarjeta %' THEN
    -- se le quitó la tarjeta (p. ej. corregido a efectivo)
    NEW.grupo := 'Efectivo';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

DROP TRIGGER IF EXISTS trigger_movimientos_grupo ON movimientos;
CREATE TRIGGER trigger_movimientos_grupo
BEFORE INSERT OR UPDATE OF tarjeta_id, prestamo_id ON movimientos
FOR EACH ROW EXECUTE FUNCTION movimientos_set_grupo();
