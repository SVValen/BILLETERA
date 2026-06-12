-- ============================================================
-- MIGRACIÓN: tabla perfiles + nuevas categorías
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Tabla perfiles: vincula email/auth.uid() con telegram_id
CREATE TABLE IF NOT EXISTS perfiles (
  id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  telegram_id TEXT UNIQUE,
  nombre TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE perfiles ENABLE ROW LEVEL SECURITY;

-- Cada usuario solo ve y edita su propio perfil
CREATE POLICY "own_perfil_select" ON perfiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "own_perfil_insert" ON perfiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "own_perfil_update" ON perfiles FOR UPDATE USING (auth.uid() = id);

-- ── Nuevas categorías (Ropa y Educación) ──
INSERT INTO categorias (id, nombre, emoji, presupuesto_mensual) VALUES
  (8, 'Ropa',      '👕', NULL),
  (9, 'Educación', '📚', NULL)
ON CONFLICT (id) DO NOTHING;

-- También por nombre por si los ids ya existen con otro valor
INSERT INTO categorias (nombre, emoji, presupuesto_mensual) VALUES
  ('Ropa',      '👕', NULL),
  ('Educación', '📚', NULL)
ON CONFLICT (nombre) DO NOTHING;
