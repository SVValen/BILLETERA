'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

function fmtUSD(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}
function fmtPrecio(precio: number, moneda: string) {
  return moneda === 'ARS'
    ? new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(precio)
    : fmtUSD(precio)
}

interface Portafolio {
  id: number
  tipo: 'conservador' | 'pasivo' | 'crecimiento' | 'oportunista'
  nombre_personalizado: string | null
  nombre_sugerido: string | null
  capital_usd: number | null
  asignacion_rf_pct: number | null
  objetivo: string | null
}

interface Activo {
  id: number
  codigo: string
  nombre: string
  tipo: string
  moneda: string
  precio_actual: number | null
  precio_ars: number | null
  rsi: number | null
  tendencia: string | null
  ultimo_update: string | null
}

interface Recomendacion {
  id: number
  accion: 'comprar' | 'vender'
  razon: string
  rsi_en_momento: number | null
  confianza: number
  estado: string
  generado_at: string
  portafolio_id: number
  activos: { codigo: string; nombre: string; tipo: string; moneda: string } | null
  portafolios: { nombre_personalizado: string | null; nombre_sugerido: string | null; tipo: string } | null
}

interface Decision {
  id: number
  accion: string
  resultado: string
  creado_at: string
  recomendaciones: {
    accion: string
    activos: { codigo: string; nombre: string } | null
  } | null
}

interface Stats {
  total: number
  aceptadas: number
  exitosas: number
  winrate: number | null
}

const TIPO_EMOJI: Record<string, string> = {
  conservador: '🛡️',
  pasivo: '💰',
  crecimiento: '📈',
  oportunista: '🎯',
}

const TIPO_LABEL: Record<string, string> = {
  conservador: 'Conservador',
  pasivo: 'Pasivo',
  crecimiento: 'Crecimiento',
  oportunista: 'Oportunista',
}

const RSI_COLOR = (rsi: number | null) => {
  if (rsi === null) return 'var(--fg3)'
  if (rsi < 35) return '#22c55e'
  if (rsi > 65) return '#ef4444'
  return 'var(--fg2)'
}

const TENDENCIA_EMOJI: Record<string, string> = {
  alcista: '↗️',
  bajista: '↘️',
  lateral: '→',
}

export default function InversionesTab() {
  const [portafolios, setPortafolios] = useState<Portafolio[]>([])
  const [activos, setActivos] = useState<Activo[]>([])
  const [recomendaciones, setRecomendaciones] = useState<Recomendacion[]>([])
  const [decisiones, setDecisiones] = useState<Decision[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [decidiendo, setDecidiendo] = useState<number | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [pRes, aRes, rRes, dRes] = await Promise.all([
        fetchWithAuth('/api/inversiones?resource=portafolios'),
        fetchWithAuth('/api/inversiones?resource=activos'),
        fetchWithAuth('/api/inversiones?resource=recomendaciones&estado=pendiente&limit=10'),
        fetchWithAuth('/api/inversiones?resource=decisiones'),
      ])

      if (!pRes.ok || !aRes.ok || !rRes.ok || !dRes.ok) {
        throw new Error(`API error: ${[pRes, aRes, rRes, dRes].map(r => r.status).join('/')}`)
      }

      const [pData, aData, rData, dData] = await Promise.all([
        pRes.json(), aRes.json(), rRes.json(), dRes.json(),
      ])

      setPortafolios(Array.isArray(pData) ? pData : [])
      setActivos(Array.isArray(aData) ? aData : [])
      setRecomendaciones(Array.isArray(rData) ? rData : [])
      setDecisiones(Array.isArray(dData?.decisiones) ? dData.decisiones : [])
      setStats(dData?.stats ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar datos de inversiones')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  async function decidir(recId: number, accion: 'aceptada' | 'rechazada') {
    setDecidiendo(recId)
    await fetchWithAuth('/api/inversiones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource: 'decidir', recomendacion_id: recId, accion }),
    })
    setDecidiendo(null)
    fetchData()
  }

  if (loading) return <div className="loading">Cargando inversiones...</div>
  if (error) return <div className="error-banner">{error} <button className="btn-ghost" onClick={fetchData}>Reintentar</button></div>

  if (portafolios.length === 0) {
    return (
      <div className="tab-content">
        <div className="section-header">
          <h2 className="section-title">📈 Inversiones</h2>
        </div>
        <div className="widget-box" style={{ textAlign: 'center', padding: '32px 24px' }}>
          <p style={{ fontSize: 16, marginBottom: 8 }}>No tenés portafolios configurados aún.</p>
          <p style={{ color: 'var(--fg3)', fontSize: 14 }}>
            Enviá <strong>/portafolio_nuevo</strong> por Telegram para crear tu primer portafolio de inversión.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="tab-content">
      <div className="section-header">
        <h2 className="section-title">📈 Inversiones</h2>
      </div>

      {/* Portafolios */}
      <div className="cards" style={{ gridTemplateColumns: `repeat(${Math.min(portafolios.length, 2)}, 1fr)` }}>
        {portafolios.map(p => {
          const nombre = p.nombre_personalizado || p.nombre_sugerido || TIPO_LABEL[p.tipo]
          return (
            <div key={p.id} className="card">
              <p className="card-label">{TIPO_EMOJI[p.tipo]} {TIPO_LABEL[p.tipo]}</p>
              <p className="card-value" style={{ fontSize: 18 }}>{nombre}</p>
              <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--fg3)' }}>
                {p.capital_usd ? fmtUSD(p.capital_usd) : '—'} · RF {p.asignacion_rf_pct ?? '—'}%
              </p>
              {p.objetivo && (
                <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--fg3)' }}>{p.objetivo}</p>
              )}
            </div>
          )
        })}
      </div>

      {/* Stats */}
      <div className="cards" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="card">
          <p className="card-label">Winrate</p>
          <p className="card-value" style={{ color: stats?.winrate != null && stats.winrate >= 50 ? '#22c55e' : '#ef4444' }}>
            {stats?.winrate != null ? `${stats.winrate}%` : '—'}
          </p>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--fg3)' }}>
            {stats?.exitosas ?? 0}/{stats?.aceptadas ?? 0} aceptadas
          </p>
        </div>
        <div className="card">
          <p className="card-label">Decisiones</p>
          <p className="card-value">{stats?.total ?? 0}</p>
        </div>
        <div className="card">
          <p className="card-label">Activos monitoreados</p>
          <p className="card-value">{activos.length}</p>
        </div>
      </div>

      {/* Recomendaciones pendientes */}
      {recomendaciones.length > 0 && (
        <div className="widget-box">
          <h3 className="widget-title">⏳ Recomendaciones pendientes</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {recomendaciones.map(rec => {
              const accionColor = rec.accion === 'comprar' ? '#22c55e' : '#ef4444'
              const accionEmoji = rec.accion === 'comprar' ? '🟢' : '🔴'
              const portNombre = rec.portafolios?.nombre_personalizado || rec.portafolios?.nombre_sugerido || TIPO_LABEL[rec.portafolios?.tipo ?? ''] || '—'
              return (
                <div key={rec.id} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <span style={{ fontWeight: 700, fontSize: 15, color: accionColor }}>
                          {accionEmoji} {rec.accion.toUpperCase()}
                        </span>
                        <span style={{ fontWeight: 600 }}>{rec.activos?.nombre ?? rec.activos?.codigo}</span>
                        <span style={{ fontSize: 12, color: 'var(--fg3)', marginLeft: 'auto' }}>
                          Confianza: {rec.confianza}/10
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: 13, color: 'var(--fg2)', lineHeight: 1.5 }}>{rec.razon}</p>
                      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--fg3)', display: 'flex', gap: 12 }}>
                        {rec.rsi_en_momento != null && <span>RSI: {rec.rsi_en_momento}</span>}
                        <span>{portNombre}</span>
                        <span>{new Date(rec.generado_at).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
                      <button
                        className="btn-primary"
                        style={{ padding: '6px 14px', fontSize: 13 }}
                        disabled={decidiendo === rec.id}
                        onClick={() => decidir(rec.id, 'aceptada')}
                      >
                        ✅ Aceptar
                      </button>
                      <button
                        className="btn-ghost"
                        style={{ padding: '6px 14px', fontSize: 13 }}
                        disabled={decidiendo === rec.id}
                        onClick={() => decidir(rec.id, 'rechazada')}
                      >
                        ❌ Rechazar
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Activos monitoreados */}
      <div className="widget-box">
        <h3 className="widget-title">📊 Activos monitoreados</h3>
        <div style={{ overflowX: 'auto' }}>
          <table className="mov-table">
            <thead>
              <tr>
                <th>Activo</th>
                <th>Tipo</th>
                <th style={{ textAlign: 'right' }}>Precio</th>
                <th style={{ textAlign: 'right' }}>RSI</th>
                <th style={{ textAlign: 'center' }}>Tendencia</th>
                <th style={{ textAlign: 'right' }}>Actualizado</th>
              </tr>
            </thead>
            <tbody>
              {activos.map(a => {
                const precio = a.moneda === 'ARS' ? a.precio_ars : a.precio_actual
                const updateTime = a.ultimo_update
                  ? new Date(a.ultimo_update).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
                  : '—'
                return (
                  <tr key={a.id}>
                    <td><strong>{a.codigo}</strong> <span style={{ color: 'var(--fg3)', fontSize: 12 }}>{a.nombre}</span></td>
                    <td style={{ fontSize: 12, color: 'var(--fg3)' }}>{a.tipo}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>
                      {precio ? fmtPrecio(precio, a.moneda) : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600, color: RSI_COLOR(a.rsi) }}>
                      {a.rsi ?? '—'}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {a.tendencia ? `${TENDENCIA_EMOJI[a.tendencia] ?? ''} ${a.tendencia}` : '—'}
                    </td>
                    <td style={{ textAlign: 'right', fontSize: 12, color: 'var(--fg3)' }}>{updateTime}</td>
                  </tr>
                )
              })}
              {activos.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--fg3)', padding: '24px 0' }}>
                  Sin datos todavía — el cron actualiza precios cada 30 minutos
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--fg3)' }}>
          🟢 RSI &lt; 35 sobreventa (señal de compra) · 🔴 RSI &gt; 65 sobrecompra (señal de venta)
        </p>
      </div>

      {/* Historial de decisiones */}
      <div className="widget-box">
        <h3 className="widget-title">🕐 Historial de decisiones</h3>
        {decisiones.length === 0 ? (
          <p style={{ color: 'var(--fg3)', fontSize: 14 }}>Sin decisiones todavía. Las recomendaciones aparecen aquí una vez que aceptés o rechacés.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {decisiones.slice(0, 20).map(d => {
              const nombre = d.recomendaciones?.activos?.nombre ?? d.recomendaciones?.activos?.codigo ?? '?'
              const accionRec = d.recomendaciones?.accion ?? '?'
              const resultadoColor = d.resultado === 'exitoso' ? '#22c55e' : d.resultado === 'fallido' ? '#ef4444' : 'var(--fg3)'
              const resultadoLabel: Record<string, string> = { exitoso: '✅ Exitoso', fallido: '❌ Fallido', neutral: '➖ Neutral', pendiente: '⏳ Pendiente' }
              return (
                <div key={d.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 14 }}>
                  <span style={{ width: 22, textAlign: 'center' }}>{d.accion === 'aceptada' ? '✅' : '❌'}</span>
                  <span style={{ flex: 1 }}>{nombre} — {accionRec}</span>
                  <span style={{ color: resultadoColor, fontSize: 12, whiteSpace: 'nowrap' }}>
                    {resultadoLabel[d.resultado] ?? d.resultado}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--fg3)', whiteSpace: 'nowrap' }}>
                    {new Date(d.creado_at).toLocaleDateString('es-AR')}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
