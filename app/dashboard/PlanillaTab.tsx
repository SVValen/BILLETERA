'use client'

import { useEffect, useMemo, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert } from '@/app/components/design'

interface Fila {
  id: number
  descripcion: string
  monto: number
  tipo: 'gasto' | 'ingreso'
  grupo: string
  concepto: string | null
  moneda: 'ARS' | 'USD'
  monto_original: number | null
  tipo_cambio: number | null
  cuota_nro: number | null
  cuota_total: number | null
  debito_automatico: boolean
  pagado: boolean
  estimado: boolean
  rubro: string | null
  emoji: string | null
}

interface Planilla {
  mes: string
  filas: Fila[]
  total_ingresos: number
  total_gastos: number
  neto: number
  pagos_tarjeta: Record<string, number>
}

// Orden de los grupos, igual que en la planilla de Excel
const ORDEN_INGRESOS = ['Sueldo', 'Cuotas familia']
const ORDEN_GASTOS = ['Préstamo', 'Tarjeta Naranja', 'Tarjeta Santander', 'Tarjeta BBVA', 'Tarjeta MP', 'Alquiler', 'Efectivo']

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

function nombreMes(mes: string) {
  const [y, m] = mes.split('-')
  const n = MESES[Number(m) - 1] ?? mes
  return `${n.charAt(0).toUpperCase()}${n.slice(1)} ${y}`
}

function agrupar(filas: Fila[], orden: string[]) {
  const map = new Map<string, Fila[]>()
  for (const f of filas) {
    const g = f.grupo || 'Efectivo'
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(f)
  }
  const pos = (g: string) => {
    const i = orden.indexOf(g)
    return i === -1 ? orden.length : i
  }
  return [...map.entries()]
    .sort(([a], [b]) => pos(a) - pos(b) || a.localeCompare(b))
    .map(([grupo, items]) => ({ grupo, items, total: items.reduce((s, f) => s + f.monto, 0) }))
}

function Detalle({ f }: { f: Fila }) {
  const partes: string[] = []
  if (f.rubro && f.tipo === 'gasto') partes.push(f.rubro)
  if (f.moneda === 'USD' && f.monto_original != null) partes.push(`USD ${f.monto_original.toLocaleString('es-AR')}`)
  if (f.debito_automatico) partes.push('débito automático')
  if (f.estimado) partes.push('estimado')
  return partes.length ? <span className="planilla-meta">{partes.join(', ')}</span> : null
}

function Grupo({ grupo, items, total, pagado }: { grupo: string; items: Fila[]; total: number; pagado?: number }) {
  const pendientes = items.filter(f => !f.pagado && f.concepto !== 'descuento')
  return (
    <section className="planilla-grupo" aria-label={grupo}>
      <header className="planilla-grupo-head">
        <h4>{grupo}</h4>
        <span className="planilla-num planilla-subtotal">{fmt(total)}</span>
      </header>
      <table className="planilla-tabla">
        <tbody>
          {items.map(f => (
            <tr key={f.id} className={f.monto < 0 ? 'es-descuento' : undefined}>
              <td className="planilla-concepto">
                {!f.pagado && f.concepto !== 'descuento' && <span title="Pendiente de pago" aria-label="Pendiente de pago">⏳ </span>}
                {f.descripcion.replace(/\s*\(cuota \d+\/\d+\)$/, '')}
                <Detalle f={f} />
              </td>
              <td className="planilla-cuota">
                {f.cuota_nro != null && f.cuota_total != null && f.cuota_total > 1 ? `${f.cuota_nro}/${f.cuota_total}` : ''}
              </td>
              <td className="planilla-num">{fmt(f.monto)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(pagado != null || pendientes.length > 0) && (
        <p className="planilla-pie">
          {pagado != null
            ? Math.abs(pagado - total) <= 1
              ? `Pagado ${fmt(pagado)}`
              : `Pagaste ${fmt(pagado)} de ${fmt(total)}`
            : `${pendientes.length === items.length ? 'Pendiente' : `${pendientes.length} pendiente${pendientes.length > 1 ? 's' : ''}`}: ${fmt(pendientes.reduce((s, f) => s + f.monto, 0))}`}
        </p>
      )}
    </section>
  )
}

export default function PlanillaTab({ mes }: { mes: string }) {
  const [data, setData] = useState<Planilla | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchWithAuth(`/api/stats?mes=${mes}&resource=planilla`)
      .then(r => r.json())
      .then(d => {
        if (cancelled) return
        if (d?.error) setError(d.error)
        else setData(d)
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'No se pudo cargar la planilla') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [mes])

  const ingresos = useMemo(() => agrupar((data?.filas ?? []).filter(f => f.tipo === 'ingreso'), ORDEN_INGRESOS), [data])
  const gastos = useMemo(() => agrupar((data?.filas ?? []).filter(f => f.tipo === 'gasto'), ORDEN_GASTOS), [data])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <BilleteraAlert variant="danger" title="No se pudo cargar la planilla">{error}</BilleteraAlert>
  if (!data || data.filas.length === 0) {
    return <p className="empty">No hay movimientos para {nombreMes(mes)}. Cargá un gasto desde Telegram o elegí otro mes.</p>
  }

  return (
    <div className="planilla">
      <div className="planilla-neto">
        <h3>{nombreMes(mes)}</h3>
        <div className="planilla-neto-cuenta">
          <span>Ingresos <strong className="planilla-num">{fmt(data.total_ingresos)}</strong></span>
          <span>Gastos <strong className="planilla-num">{fmt(data.total_gastos)}</strong></span>
        </div>
        <p className={`planilla-neto-valor planilla-num ${data.neto >= 0 ? 'ingreso' : 'gasto'}`}>
          {fmt(data.neto)}
        </p>
        <p className="planilla-neto-label">Neto del mes</p>
      </div>

      <div className="planilla-columnas">
        <div className="widget-box planilla-lado">
          <h3 className="widget-title">Ingresos</h3>
          {ingresos.length === 0
            ? <p className="muted">Sin ingresos cargados.</p>
            : ingresos.map(g => <Grupo key={g.grupo} {...g} />)}
        </div>
        <div className="widget-box planilla-lado">
          <h3 className="widget-title">Gastos</h3>
          {gastos.map(g => <Grupo key={g.grupo} {...g} pagado={data.pagos_tarjeta[g.grupo]} />)}
        </div>
      </div>
    </div>
  )
}
