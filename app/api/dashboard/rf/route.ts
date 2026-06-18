import { createClient } from '@supabase/supabase-js'
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET(req: NextRequest) {
  try {
    const supabase = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL || '',
      process.env.SUPABASE_SERVICE_ROLE_KEY || ''
    )

    // Obtener usuario autenticado
    const authHeader = req.headers.get('Authorization') || ''
    const token = authHeader.replace('Bearer ', '')

    if (!token) {
      return NextResponse.json({ error: 'No autorizado' }, { status: 401 })
    }

    // Obtener user desde token
    const { data: { user } } = await supabase.auth.getUser(token)
    if (!user) {
      return NextResponse.json({ error: 'No autorizado' }, { status: 401 })
    }

    // Obtener perfil del usuario (para telegram_id si es necesario)
    const { data: perfil } = await supabase
      .from('perfiles')
      .select('telegram_id')
      .eq('id', user.id)
      .single()

    const user_id = perfil?.telegram_id || user.id

    // Obtener posiciones RF abiertas con datos de instrumentos
    const { data: posiciones, error: posError } = await supabase
      .from('posiciones_rf')
      .select('*, instrumentos_rf(nombre, tipo, tna_actual, precio_actual)')
      .eq('usuario_id', user_id)
      .eq('estado', 'abierta')

    if (posError) throw posError

    // Obtener dólar MEP (simplificado - en producción usar API)
    let dolar_mep = 1400 // Valor default

    // Obtener carry trade
    const { data: caucion } = await supabase
      .from('instrumentos_rf')
      .select('tna_actual')
      .eq('codigo', 'CAUCION_7D')
      .single()

    const tna_cauc = caucion?.tna_actual || 35
    const tna_mensual = tna_cauc / 12
    
    // Devaluación MEP estimada (~3% mensual en contexto inflacionario)
    const devaluacion_mep = 3.0
    const carry_mensual = tna_mensual - devaluacion_mep

    const carry_trade = {
      accion: carry_mensual > 2 ? 'entrar' : carry_mensual < 0 ? 'salir' : 'neutral',
      tna_mensual,
      carry_mensual,
    }

    // Calcular totales y rendimiento
    let total_ars = 0
    let total_usd = 0
    let rendimiento_total_usd = 0

    const posiciones_con_rendimiento = (posiciones || []).map((pos) => {
      total_ars += pos.monto_ars || 0
      const monto_usd = (pos.monto_ars || 0) / dolar_mep
      total_usd += monto_usd

      // Rendimiento acumulado (si existe) o estimado
      let rendimiento = pos.rendimiento_acumulado || 0

      // Si no hay rendimiento registrado, estimarlo basado en días y TNA
      if (!pos.rendimiento_acumulado && pos.tna_contratada) {
        const dias_desde_entrada = Math.floor(
          (new Date().getTime() - new Date(pos.fecha_entrada).getTime()) / (1000 * 60 * 60 * 24)
        )
        const rendimiento_ars = (pos.monto_ars * pos.tna_contratada / 100 / 365) * dias_desde_entrada
        rendimiento = rendimiento_ars / dolar_mep
      }

      rendimiento_total_usd += rendimiento

      return {
        ...pos,
        rendimiento_acumulado: rendimiento,
      }
    })

    return NextResponse.json({
      posiciones: posiciones_con_rendimiento,
      dolar_mep,
      carry_trade,
      total_usd,
      total_ars,
      rendimiento_total_usd,
    })
  } catch (error) {
    console.error('Error en /api/dashboard/rf:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Error desconocido' },
      { status: 500 }
    )
  }
}
