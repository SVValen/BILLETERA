-- ============================================================
-- MIGRACIÓN: RLS policies por usuario (reemplaza las permisivas)
-- Ejecutar DESPUÉS de todos los schemas anteriores
-- ============================================================

-- Función helper: retorna el telegram_id del usuario autenticado
-- Permite que las policies usen el mismo identificador que el backend
CREATE OR REPLACE FUNCTION auth_telegram_id()
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT telegram_id FROM perfiles WHERE id = auth.uid()
$$;

-- ── perfiles ──────────────────────────────────────────────────────────────────
-- Cada usuario solo accede a su propio perfil
ALTER TABLE perfiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_all_perfiles" ON perfiles;
CREATE POLICY "own_perfil" ON perfiles
  FOR ALL
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- ── movimientos ───────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS "service_role_all_movimientos" ON movimientos;
CREATE POLICY "own_movimientos" ON movimientos
  FOR ALL
  USING (usuario_id = auth_telegram_id())
  WITH CHECK (usuario_id = auth_telegram_id());

-- ── presupuestos ──────────────────────────────────────────────────────────────
ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_all_presupuestos" ON presupuestos;
CREATE POLICY "own_presupuestos" ON presupuestos
  FOR ALL
  USING (usuario_id = auth_telegram_id())
  WITH CHECK (usuario_id = auth_telegram_id());

-- ── recurrentes ───────────────────────────────────────────────────────────────
ALTER TABLE recurrentes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_all_recurrentes" ON recurrentes;
CREATE POLICY "own_recurrentes" ON recurrentes
  FOR ALL
  USING (usuario_id = auth_telegram_id())
  WITH CHECK (usuario_id = auth_telegram_id());

-- ── cuotas_plan ───────────────────────────────────────────────────────────────
ALTER TABLE cuotas_plan ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_all_cuotas_plan" ON cuotas_plan;
CREATE POLICY "own_cuotas_plan" ON cuotas_plan
  FOR ALL
  USING (usuario_id = auth_telegram_id())
  WITH CHECK (usuario_id = auth_telegram_id());

-- ── keywords_aprendidas ───────────────────────────────────────────────────────
ALTER TABLE keywords_aprendidas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_all_keywords" ON keywords_aprendidas;
CREATE POLICY "own_keywords" ON keywords_aprendidas
  FOR ALL
  USING (usuario_id = auth_telegram_id())
  WITH CHECK (usuario_id = auth_telegram_id());

-- ── objetivos_ahorro ──────────────────────────────────────────────────────────
ALTER TABLE objetivos_ahorro ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_all_objetivos" ON objetivos_ahorro;
CREATE POLICY "own_objetivos" ON objetivos_ahorro
  FOR ALL
  USING (usuario_id = auth_telegram_id())
  WITH CHECK (usuario_id = auth_telegram_id());

-- ── categorias ────────────────────────────────────────────────────────────────
-- Datos de referencia compartidos: solo lectura para todos los autenticados
DROP POLICY IF EXISTS "service_role_all_categorias" ON categorias;
CREATE POLICY "read_categorias" ON categorias
  FOR SELECT
  USING (true);
