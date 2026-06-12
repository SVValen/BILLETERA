-- Categoría Suscripciones (id=18)
INSERT INTO categorias (id, nombre, emoji)
VALUES (18, 'Suscripciones', '📱')
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, emoji = EXCLUDED.emoji;

-- Tabla de keywords aprendidas por el usuario al categorizar manualmente
CREATE TABLE IF NOT EXISTS keywords_aprendidas (
  id           SERIAL PRIMARY KEY,
  usuario_id   TEXT NOT NULL,
  keyword      TEXT NOT NULL,
  categoria_id INT  NOT NULL REFERENCES categorias(id),
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (usuario_id, keyword)
);

ALTER TABLE keywords_aprendidas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_keywords" ON keywords_aprendidas
  FOR ALL USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_keywords_usuario ON keywords_aprendidas(usuario_id, keyword);
