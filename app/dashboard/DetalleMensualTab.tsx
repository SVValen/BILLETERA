'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

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

export default function DetalleMensualTab({ mes }: { mes: string }) {
  const [cuotas, setCuotas] = useState<Cuota[]>([])
  const [recurrentes, setRecurrentes] = useState<Recurrente[]>([])
  const [tarjetas, setTarjetas] = useState<TarjetaResumen[]>([])
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
        const [cRes, rRes, tRes] = await Promise.all([
          fetchWithAuth(`/api/cuotas?mes=${mes}`),
          fetchWithAuth(`/api/recurrentes?dias=35`),
          fetchWithAuth(`/api/stats?mes=${mes}&resource=tarjetas`),
        ])
        if (cancelled) return
        const [cData, rData, tData] = await Promise.all([cRes.json(), rRes.json(), tRes.json()])
        if (cancelled) return
        setCuotas(Array.isArray(cData) ? cData : [])
        setRecurrentes(Array.isArray(rData) ? rData : [])
        setTarjetas(Array.isArray(tData?.tarjetas) ? tData.tarjetas : [])
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
  if (error) return <div className="error-banner">{error}</div>

  const totalPendiente = tarjetas.filter(t => !t.pagado).reduce((s, t) => s + t.total, 0)
  const totalPagado = tarjetas.filter(t => t.pagado).reduce((s, t) => s + (t.monto_pagado ?? t.total), 0)
  const totalCuotasMensual = cuotas.reduce((s, c) => s + c.monto_cuota, 0)

  return (
    <>
      {/* Resumen por tarjeta del mes */}
      {tarjetas.length > 0 && (
        <div className="widget-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, flexWrap: 'wrap', gap: 10 }}>
            <h3 className="widget-title" style={{ margin: 0 }}>💳 Resumen de tarjetas — {mes}</h3>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {totalPendiente > 0 && (
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--fg3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.5px' }}>⏳ Por pagar</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#f59e0b', letterSpacing: '-0.3px' }}>{fmt(totalPendiente)}</div>
                </div>
              )}
              {totalPagado > 0 && (
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--fg3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.5px' }}>✅ Pagado</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: '#22c55e', letterSpacing: '-0.3px' }}>{fmt(totalPagado)}</div>
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
                          <span className="badge badge-ok">✅ Pagado</span>
                          <span style={{ fontWeight: 800, fontSize: 15, color: '#22c55e' }}>{fmt(t.monto_pagado ?? 0)}</span>
                          {t.fecha_pago && <span style={{ fontSize: 12, color: 'var(--fg3)' }}>{t.fecha_pago}</span>}
                        </>
                      ) : (
                        <>
                          <span className="badge badge-pending">⏳ Pendiente</span>
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
                      {esUltima && <span className="badge badge-last">🏁 Última</span>}
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
                    ? <span className="badge badge-alert">Hoy</span>
                    : r.dias_faltan === 1
                    ? <span className="badge badge-pending">Mañana</span>
                    : `en ${r.dias_faltan}d`}
                </span>
                <span className="recurrente-monto">{fmt(r.monto)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tarjetas.length === 0 && cuotas.length === 0 && recurrentes.length === 0 && (
        <p className="empty">Sin cuotas, recordatorios ni tarjetas este mes. 🎉</p>
      )}
    </>
  )
}
