-- ============================================================
-- BILLETERA — Borrar todos los datos de usuario
-- ⚠️  SOLO DESARROLLO — borra todo menos tablas de catálogo
-- Ejecutar en Supabase → SQL Editor
-- ============================================================

-- Orden: hijos antes que padres (FK constraints)
DELETE FROM decisiones_inversion;
DELETE FROM recomendaciones;
DELETE FROM portafolio_activos;
DELETE FROM aportes_portafolio;
DELETE FROM posiciones_rf;
DELETE FROM colchon_mensual;
DELETE FROM portafolios;
DELETE FROM movimientos;
DELETE FROM cuotas_plan;
DELETE FROM tarjetas;
DELETE FROM recurrentes;
DELETE FROM presupuestos;
DELETE FROM objetivos_ahorro;
DELETE FROM keywords_aprendidas;
DELETE FROM precios_historicos;
DELETE FROM prestamo_cuotas;
DELETE FROM prestamos;

-- Resetear secuencias
ALTER SEQUENCE decisiones_inversion_id_seq  RESTART WITH 1;
ALTER SEQUENCE recomendaciones_id_seq       RESTART WITH 1;
ALTER SEQUENCE portafolio_activos_id_seq    RESTART WITH 1;
ALTER SEQUENCE aportes_portafolio_id_seq    RESTART WITH 1;
ALTER SEQUENCE posiciones_rf_id_seq         RESTART WITH 1;
ALTER SEQUENCE colchon_mensual_id_seq       RESTART WITH 1;
ALTER SEQUENCE portafolios_id_seq           RESTART WITH 1;
ALTER SEQUENCE movimientos_id_seq           RESTART WITH 1;
ALTER SEQUENCE cuotas_plan_id_seq           RESTART WITH 1;
ALTER SEQUENCE tarjetas_id_seq              RESTART WITH 1;
ALTER SEQUENCE recurrentes_id_seq           RESTART WITH 1;
ALTER SEQUENCE presupuestos_id_seq          RESTART WITH 1;
ALTER SEQUENCE objetivos_ahorro_id_seq      RESTART WITH 1;
ALTER SEQUENCE keywords_aprendidas_id_seq   RESTART WITH 1;
ALTER SEQUENCE precios_historicos_id_seq    RESTART WITH 1;
ALTER SEQUENCE prestamo_cuotas_id_seq       RESTART WITH 1;
ALTER SEQUENCE prestamos_id_seq             RESTART WITH 1;

-- Se preservan: categorias, activos, instrumentos_rf, perfiles
