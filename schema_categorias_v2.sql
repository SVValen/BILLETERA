-- ============================================================
-- MIGRACIÓN: categorías v2 (sin presupuestos)
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Actualizar emojis y nombres de las existentes (IDs 1-9)
UPDATE categorias SET nombre = 'Supermercado',    emoji = '🛒' WHERE id = 1;
UPDATE categorias SET nombre = 'Transporte',       emoji = '🚗' WHERE id = 2;
UPDATE categorias SET nombre = 'Comida',           emoji = '🍽️' WHERE id = 3;
UPDATE categorias SET nombre = 'Servicios',        emoji = '💡' WHERE id = 4;
UPDATE categorias SET nombre = 'Entretenimiento',  emoji = '🎬' WHERE id = 5;
UPDATE categorias SET nombre = 'Salud',            emoji = '🏥' WHERE id = 6;
UPDATE categorias SET nombre = 'Otros',            emoji = '📌' WHERE id = 7;
UPDATE categorias SET nombre = 'Ropa',             emoji = '👕' WHERE id = 8;
UPDATE categorias SET nombre = 'Educación',        emoji = '📚' WHERE id = 9;

-- Agregar nuevas categorías (10-16)
INSERT INTO categorias (id, nombre, emoji, presupuesto_mensual) VALUES
  (10, 'Vivienda',           '🏠', NULL),
  (11, 'Mascotas',           '🐾', NULL),
  (12, 'Viajes',             '✈️', NULL),
  (13, 'Seguros',            '🛡️', NULL),
  (14, 'Inversiones',        '💰', NULL),
  (15, 'Compras Online',     '💳', NULL),
  (16, 'Belleza & Bienestar','✨', NULL)
ON CONFLICT (id) DO UPDATE
  SET nombre = EXCLUDED.nombre,
      emoji  = EXCLUDED.emoji;
