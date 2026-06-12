-- Agregar categoría Ingresos (id=17)
INSERT INTO categorias (id, nombre, emoji, presupuesto_mensual)
VALUES (17, 'Ingresos', '💵', NULL)
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, emoji = EXCLUDED.emoji;

-- Reclasificar los movimientos de tipo ingreso que quedaron en Otros (id=7)
UPDATE movimientos SET categoria_id = 17 WHERE tipo = 'ingreso' AND categoria_id = 7;
