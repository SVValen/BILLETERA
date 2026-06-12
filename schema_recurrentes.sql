-- Gastos recurrentes: recordatorios mensuales
CREATE TABLE IF NOT EXISTS recurrentes (
  id           SERIAL PRIMARY KEY,
  usuario_id   TEXT          NOT NULL,
  descripcion  TEXT          NOT NULL,
  monto        DECIMAL(10,2) NOT NULL,
  categoria_id INT           REFERENCES categorias(id),
  tipo         VARCHAR(20)   DEFAULT 'gasto',
  dia_del_mes  INT           NOT NULL CHECK (dia_del_mes BETWEEN 1 AND 31),
  activo       BOOLEAN       DEFAULT TRUE,
  ultimo_recordatorio DATE,
  created_at   TIMESTAMPTZ   DEFAULT NOW()
);

ALTER TABLE recurrentes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_recurrentes" ON recurrentes
  FOR ALL USING (true) WITH CHECK (true);

-- Plan de compras en cuotas
CREATE TABLE IF NOT EXISTS cuotas_plan (
  id                  SERIAL PRIMARY KEY,
  usuario_id          TEXT          NOT NULL,
  descripcion         TEXT          NOT NULL,
  monto_total         DECIMAL(10,2) NOT NULL,
  monto_cuota         DECIMAL(10,2) NOT NULL,
  num_cuotas          INT           NOT NULL,
  categoria_id        INT           REFERENCES categorias(id),
  fecha_primera_cuota DATE,         -- NULL mientras espera confirmación
  activo              BOOLEAN       DEFAULT TRUE,
  created_at          TIMESTAMPTZ   DEFAULT NOW()
);

ALTER TABLE cuotas_plan ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_cuotas_plan" ON cuotas_plan
  FOR ALL USING (true) WITH CHECK (true);
