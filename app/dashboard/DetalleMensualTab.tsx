'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert, BilleteraBadge } from '@/app/components/design'

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

interface Cuota {
  id: number
  descripcion: string
  emoji: string
  monto_cuota: number
  num_cuotas: number
  pagadas: number
  restantes: number
  porcentaje: number
  proxima_cuota: string
}

interface Recurrente {
  id: number
  descripcion: string
  emoji: string
  monto: number
  dia_del_mes: number
  proxima_fecha: string
  dias_faltan: number
}

interface TarjetaResumen {
  tarjeta_id: number
  nombre: string
  cuotas: number
  un_pago: number
  total: number
  pagado: boolean
  monto_pagado: number | null
  fecha_pago: string | null
}

interface MovDetalle {
  id: number
  fecha: string
  descripcion: string
  monto: number
  forma_pago: string
}

interface IngresoMes {
  id: number
  descripcion: string
  monto_esperado: number
  monto_registrado: number | null
  registrado: boolean
}

interface PrestamoMes {
  prestamo_id: number
  nombre: string
  monto: number
  pagado: boolean
}

export default function DetalleMensualTab({ mes }: { mes: string }) {
  const [cuotas, setCuotas] = useState<Cuota[]>([])
  const [recurrentes, setRecurrentes] = useState<Recurrente[]>([])
  const [tarjetas, setTarjetas] = useState<TarjetaResumen[]>([])
  const [ingresosMes, setIngresosMes] = useState<IngresoMes[]>([])
  const [prestamosMes, setPrestamosMes] = useState<PrestamoMes[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [detalle, setDetalle] = useState<Record<number, MovDetalle[]>>({})
  const [loadingDetalle, setLoadingDetalle] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [cRes, rRes, tRes, iRes, pRes] = await Promise.all([
          fetchWithAuth(`/api/cuotas?mes=${mes}`),
          fetchWithAuth(`/api/recurrentes?dias=35`),
          fetchWithAuth(`/api/stats?mes=${mes}&resource=tarjetas`),
          fetchWithAuth(`/api/recurrentes?resource=ingresos_mes&mes=${mes}`),
          fetchWithAuth(`/api/inversiones?resource=prestamos_mes&mes=${mes}`),
        ])
        if (cancelled) return
        const [cData, rData, tData, iData, pData] = await Promise.all([cRes.json(), rRes.json(), tRes.json(), iRes.json(), pRes.json()])
        if (cancelled) return
        setCuotas(Array.isArray(cData) ? cData : [])
        setRecurrentes(Array.isArray(rData) ? rData : [])
        setTarjetas(Array.isArray(tData?.tarjetas) ? tData.tarjetas : [])
        setIngresosMes(Array.isArray(iData) ? iData : [])
        setPrestamosMes(Array.isArray(pData) ? pData : [])
        setExpanded(null)
        setDetalle({})
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Error desconocido')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [mes])

  const toggleDetalle = useCallback(async (tarjetaId: number) => {
    if (expanded === tarjetaId) {
      setExpanded(null)
      return
    }
    setExpanded(tarjetaId)
    if (detalle[tarjetaId]) return
    setLoadingDetalle(tarjetaId)
    try {
      const r = await fetchWithAuth(`/api/movements?mes_resumen=${mes}&tarjeta_id=${tarjetaId}&todos=1`)
      const data = await r.json()
      setDetalle(prev => ({ ...prev, [tarjetaId]: data.data || [] }))
    } finally {
      setLoadingDetalle(null)
    }
  }, [expanded, detalle, mes])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <BilleteraAlert variant="danger" title="Error">{error}</BilleteraAlert>

  const totalPendiente = tarjetas.filter(t => !t.pagado).reduce((s, t) => s + t.total, 0)
  const totalPagado = tarjetas.filter(t => t.pagado).reduce((s, t) => s + (t.monto_pagado ?? t.total), 0)
  const totalCuotasMensual = cuotas.reduce((s, c) => s + c.monto_cuota, 0)

  const totalTarjetaMes = totalPendiente + totalPagado
  const totalIngresosMes = ingresosMes.reduce((s, i) => s + (i.monto_registrado ?? i.monto_esperado), 0)
  const totalPrestamoMes = prestamosMes.reduce((s, p) => s + p.monto, 0)
  const montoLibre = totalIngresosMes - totalTarjetaMes - totalPrestamoMes

  return (
    <>
      {/* Ingresos esperados del mes */}
      {ingresosMes.length > 0 && (
        <div className="widget-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, flexWrap: 'wrap', gap: 8 }}>
            <h3 className="widget-title" style={{ margin: 0 }}>💰 Ingresos — {mes}</h3>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: 'var(--fg3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.5px' }}>Total</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--b-green)', letterSpacing: '-0.3px' }}>{fmt(totalIngresosMes)}</div>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {ingresosMes.map(i => (
              <div key={i.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 14 }}>
                <span>{i.descripcion}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {i.registrado
                    ? <BilleteraBadge variant="green">✅ Registrado</BilleteraBadge>
                    : <BilleteraBadge variant="gold">⏳ Esperado</BilleteraBadge>}
                  <span style={{ fontWeight: 700 }}>{fmt(i.monto_registrado ?? i.monto_esperado)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Resumen por tarjeta del mes */}
      {tarjetas.length > 0 && (
        <div className="widget-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, flexWrap: 'wrap', gap: 10 }}>
            <h3 className="widget-title" style={{ margin: 0 }}>💳 Resumen de tarjetas — {mes}</h3>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {totalPendiente > 0 && (
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--fg3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.5px' }}>⏳ Por pagar</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--b-gold-dk)', letterSpacing: '-0.3px' }}>{fmt(totalPendiente)}</div>
                </div>
              )}
              {totalPagado > 0 && (
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--fg3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.5px' }}>✅ Pagado</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--b-green)', letterSpacing: '-0.3px' }}>{fmt(totalPagado)}</div>
                </div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {tarjetas.map(t => (
              <div key={t.tarjeta_id} style={{
                border: `1.5px solid ${t.pagado ? 'rgba(34,197,94,.3)' : 'var(--border)'}`,
                borderRadius: 12,
                overflow: 'hidden',
                background: t.pagado ? 'rgba(34,197,94,.03)' : 'var(--bg3)',
              }}>
                {/* Header clickeable */}
                <button
                  onClick={() => toggleDetalle(t.tarjeta_id)}
                  style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: '12px 16px', textAlign: 'left', color: 'inherit' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 6 }}>
                      {expanded === t.tarjeta_id ? '▾' : '▸'} 💳 {t.nombre}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {t.pagado ? (
                        <>
                          <BilleteraBadge variant="green">✅ Pagado</BilleteraBadge>
                          <span style={{ fontWeight: 800, fontSize: 15, color: 'var(--b-green)' }}>{fmt(t.monto_pagado ?? 0)}</span>
                          {t.fecha_pago && <span style={{ fontSize: 12, color: 'var(--fg3)' }}>{t.fecha_pago}</span>}
                        </>
                      ) : (
                        <>
                          <BilleteraBadge variant="gold">⏳ Pendiente</BilleteraBadge>
                          <span style={{ fontWeight: 800, fontSize: 15 }}>{fmt(t.total)}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--fg3)', textAlign: 'left', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {t.cuotas > 0 && <span>📅 Cuotas fijas: <b>{fmt(t.cuotas)}</b></span>}
                    {t.un_pago > 0 && <span>🛒 En 1 pago: <b>{fmt(t.un_pago)}</b></span>}
                  </div>
                </button>

                {/* Panel de detalle */}
                {expanded === t.tarjeta_id && (
                  <div style={{ borderTop: '1px solid var(--border)', padding: '10px 16px 14px' }}>
                    {loadingDetalle === t.tarjeta_id ? (
                      <p className="muted" style={{ fontSize: 13, margin: 0 }}>Cargando...</p>
                    ) : (detalle[t.tarjeta_id] ?? []).length === 0 ? (
                      <p className="muted" style={{ fontSize: 13, margin: 0 }}>Sin movimientos.</p>
                    ) : (
                      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ color: 'var(--fg3)' }}>
                            <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.4px' }}>Fecha</th>
                            <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.4px' }}>Descripción</th>
                            <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.4px' }}>Forma</th>
                            <th style={{ textAlign: 'right', paddingBottom: 6, fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.4px' }}>Monto</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(detalle[t.tarjeta_id] ?? []).map(m => (
                            <tr key={m.id} style={{ borderTop: '1px solid var(--border)' }}>
                              <td style={{ padding: '5px 0', color: 'var(--fg3)', whiteSpace: 'nowrap', paddingRight: 12 }}>{m.fecha}</td>
                              <td style={{ padding: '5px 0', paddingRight: 12 }}>{m.descripcion}</td>
                              <td style={{ padding: '5px 0', color: 'var(--fg3)', paddingRight: 12, whiteSpace: 'nowrap' }}>{m.forma_pago}</td>
                              <td style={{ padding: '5px 0', textAlign: 'right', fontWeight: 700 }}>{fmt(m.monto)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            Usá <code>/pagar_tarjeta</code> en el bot para registrar el pago del resumen.
          </p>
        </div>
      )}

      {/* Cuota de préstamos del mes */}
      {prestamosMes.length > 0 && (
        <div className="widget-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
            <h3 className="widget-title" style={{ margin: 0 }}>🚗 Préstamo — {mes}</h3>
            <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.3px' }}>{fmt(totalPrestamoMes)}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {prestamosMes.map(p => (
              <div key={p.prestamo_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 14 }}>
                <span>{p.nombre}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {p.pagado
                    ? <BilleteraBadge variant="green">✅ Pagada</BilleteraBadge>
                    : <BilleteraBadge variant="gold">⏳ Pendiente</BilleteraBadge>}
                  <span style={{ fontWeight: 700 }}>{fmt(p.monto)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Monto libre: ingresos - tarjeta - préstamo */}
      {(ingresosMes.length > 0 || tarjetas.length > 0 || prestamosMes.length > 0) && (
        <div className="widget-box">
          <h3 className="widget-title">🧮 Te queda libre</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13, color: 'var(--fg3)', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Ingresos</span><span>{fmt(totalIngresosMes)}</span></div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>- Tarjeta</span><span>{fmt(totalTarjetaMes)}</span></div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>- Cuota préstamo</span><span>{fmt(totalPrestamoMes)}</span></div>
          </div>
          <p className={`card-value ${montoLibre >= 0 ? 'ingreso' : 'gasto'}`} style={{ margin: 0 }}>{fmt(montoLibre)}</p>
        </div>
      )}

      {/* Cuotas en proceso */}
      {cuotas.length > 0 && (
        <div className="widget-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, flexWrap: 'wrap', gap: 8 }}>
            <h3 className="widget-title" style={{ margin: 0 }}>📅 Cuotas en proceso</h3>
            {totalCuotasMensual > 0 && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: 'var(--fg3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.5px' }}>Comprometido/mes</div>
                <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.3px' }}>{fmt(totalCuotasMensual)}</div>
              </div>
            )}
          </div>
          <div className="cuotas-list">
            {cuotas.map(c => {
              const esUltima = c.restantes === 1
              return (
                <div key={c.id} className="cuota-item" style={esUltima ? { borderColor: 'rgba(124,58,237,.4)', background: 'rgba(124,58,237,.04)' } : {}}>
                  <div className="cuota-header">
                    <span className="cuota-desc">{c.emoji} {c.descripcion}</span>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {esUltima && <BilleteraBadge variant="gold">🏁 Última</BilleteraBadge>}
                      <span className="cuota-monto">{fmt(c.monto_cuota)}/mes</span>
                    </div>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${c.porcentaje}%` }} />
                  </div>
                  <div className="cuota-meta">
                    <span>Cuota {c.pagadas}/{c.num_cuotas}</span>
                    {c.proxima_cuota && (
                      <span>Próxima: {new Date(c.proxima_cuota + 'T12:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })}</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Próximos recurrentes */}
      {recurrentes.length > 0 && (
        <div className="widget-box">
          <h3 className="widget-title">🔁 Próximos recordatorios</h3>
          <div className="recurrentes-list">
            {recurrentes.slice(0, 6).map(r => (
              <div key={r.id} className="recurrente-item">
                <span className="recurrente-desc">{r.emoji} {r.descripcion}</span>
                <span className="recurrente-fecha">
                  {r.dias_faltan === 0
                    ? <BilleteraBadge variant="red">Hoy</BilleteraBadge>
                    : r.dias_faltan === 1
                    ? <BilleteraBadge variant="gold">Mañana</BilleteraBadge>
                    : `en ${r.dias_faltan}d`}
                </span>
                <span className="recurrente-monto">{fmt(r.monto)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tarjetas.length === 0 && cuotas.length === 0 && recurrentes.length === 0 && ingresosMes.length === 0 && prestamosMes.length === 0 && (
        <p className="empty">Sin cuotas, recordatorios ni tarjetas este mes. 🎉</p>
      )}
    </>
  )
}
