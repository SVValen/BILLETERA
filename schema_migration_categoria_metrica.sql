-- ============================================================
-- BILLETERA — Preferencia de categorías en la métrica Efectivo vs Tarjeta
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Por categoría, si el usuario la excluyó de la métrica "efectivo vs tarjeta"
-- (InicioTab). Ausencia de fila = incluida (default). Solo se guardan las
-- exclusiones explícitas para no tener que poblar todas las categorías.
CREATE TABLE IF NOT EXISTS usuario_categoria_metrica (
  id SERIAL PRIMARY KEY,
  usuario_id TEXT NOT NULL,
  categoria_id INT NOT NULL REFERENCES categorias(id),
  incluir BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (usuario_id, categoria_id)
);

ALTER TABLE usuario_categoria_metrica ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS usuario_categoria_metrica_all ON usuario_categoria_metrica;
CREATE POLICY usuario_categoria_metrica_all ON usuario_categoria_metrica FOR ALL USING (true);

CREATE INDEX IF NOT EXISTS idx_usuario_categoria_metrica_usuario ON usuario_categoria_metrica(usuario_id);
