-- ── Presupuestos mensuales por categoría ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS presupuestos (
  id           SERIAL PRIMARY KEY,
  usuario_id   TEXT          NOT NULL,
  categoria_id INT           NOT NULL REFERENCES categorias(id),
  monto        DECIMAL(10,2) NOT NULL,
  mes          VARCHAR(7)    NOT NULL,  -- 'YYYY-MM'
  created_at   TIMESTAMPTZ   DEFAULT NOW(),
  UNIQUE (usuario_id, categoria_id, mes)
);

ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_presupuestos" ON presupuestos
  FOR ALL USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_presupuestos_usuario_mes ON presupuestos(usuario_id, mes);

-- ── Objetivos de ahorro ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS objetivos_ahorro (
  id              SERIAL PRIMARY KEY,
  usuario_id      TEXT          NOT NULL,
  nombre          VARCHAR(255)  NOT NULL,
  monto_objetivo  DECIMAL(10,2) NOT NULL,
  monto_actual    DECIMAL(10,2) DEFAULT 0,
  fecha_objetivo  DATE          NOT NULL,
  activo          BOOLEAN       DEFAULT TRUE,
  created_at      TIMESTAMPTZ   DEFAULT NOW()
);

ALTER TABLE objetivos_ahorro ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_objetivos" ON objetivos_ahorro
  FOR ALL USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_objetivos_usuario ON objetivos_ahorro(usuario_id);
