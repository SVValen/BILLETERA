'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

function fmtARS(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}
function fmtUSD(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n)
}
function fmtPrecio(precio: number, moneda: string) {
  return moneda === 'ARS' ? fmtARS(precio) : fmtUSD(precio)
}

interface Perfil {
  perfil: 'conservador' | 'moderado' | 'arriesgado'
  objetivo: string
  capital_disponible: number | null
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
  accion: 'comprar' | 'vender' | 'mantener'
  razon: string
  precio_recomendacion: number
  rsi_momento: number | null
  confianza: number
  estado: string
  generado_at: string
  activos: { codigo: string; nombre: string; tipo: string; moneda: string }
}

interface Decision {
  id: number
  accion: string
  monto: number | null
  ganancia_pct: number | null
  resultado: string
  fecha_decision: string
  recomendaciones: {
    accion: string
    activos: { codigo: string; nombre: string }
  }
}

interface Stats {
  total: number
  aceptadas: number
  exitosas: number
  winrate: number | null
}

const PERFIL_LABELS: Record<string, string> = {
  conservador: '🛡️ Conservador',
  moderado: '⚖️ Moderado',
  arriesgado: '🚀 Arriesgado',
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
  const [perfil, setPerfil] = useState<Perfil | null | undefined>(undefined)
  const [activos, setActivos] = useState<Activo[]>([])
  const [recomendaciones, setRecomendaciones] = useState<Recomendacion[]>([])
  const [decisiones, setDecisiones] = useState<Decision[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Formulario de perfil
  const [editandoPerfil, setEditandoPerfil] = useState(false)
  const [formPerfil, setFormPerfil] = useState({ perfil: 'moderado', objetivo: '', capital: '' })
  const [savingPerfil, setSavingPerfil] = useState(false)

  // Decidir recomendación
  const [decidiendo, setDecidiendo] = useState<number | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [pRes, aRes, rRes, dRes] = await Promise.all([
        fetchWithAuth('/api/inversiones/perfil'),
        fetchWithAuth('/api/inversiones/activos'),
        fetchWithAuth('/api/inversiones/recomendaciones?estado=pendiente&limit=10'),
        fetchWithAuth('/api/inversiones/decisiones'),
      ])

      // Chequear errores HTTP antes de parsear JSON
      if (!pRes.ok) {
        const body = await pRes.text()
        let msg = `Perfil: ${pRes.status}`
        try { msg = JSON.parse(body).error || msg } catch { /* noop */ }
        throw new Error(msg)
      }
      if (!aRes.ok || !rRes.ok || !dRes.ok) {
        throw new Error(`API error: ${[aRes, rRes, dRes].map(r => r.status).join('/')}`)
      }

      const [pData, aData, rData, dData] = await Promise.all([
        pRes.json(), aRes.json(), rRes.json(), dRes.json(),
      ])

      // pData vacío ({}) = sin perfil configurado
      const hasProfile = pData && !pData.error && Object.keys(pData).length > 0 && pData.perfil
      setPerfil(hasProfile ? pData : null)
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

  async function guardarPerfil() {
    setSavingPerfil(true)
    await fetchWithAuth('/api/inversiones/perfil', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        perfil: formPerfil.perfil,
        objetivo: formPerfil.objetivo || null,
        capital_disponible: formPerfil.capital ? parseFloat(formPerfil.capital) : null,
      }),
    })
    setSavingPerfil(false)
    setEditandoPerfil(false)
    fetchData()
  }

  async function decidir(recId: number, accion: 'aceptada' | 'rechazada') {
    setDecidiendo(recId)
    await fetchWithAuth('/api/inversiones/decidir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recomendacion_id: recId, accion }),
    })
    setDecidiendo(null)
    fetchData()
  }

  if (loading) return <div className="loading">Cargando inversiones...</div>
  if (error) return <div className="error-banner">{error} <button className="btn-ghost" onClick={fetchData}>Reintentar</button></div>

  // Sin perfil → formulario de setup
  if (perfil === null || editandoPerfil) {
    return (
      <div className="tab-content">
        <div className="section-header">
          <h2 className="section-title">📈 Configurar perfil de inversión</h2>
          {editandoPerfil && (
            <button className="btn-ghost" onClick={() => setEditandoPerfil(false)}>Cancelar</button>
          )}
        </div>
        <div className="widget-box" style={{ maxWidth: 500 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label className="form-label">Perfil de riesgo</label>
              <select
                className="form-input"
                value={formPerfil.perfil}
                onChange={e => setFormPerfil(f => ({ ...f, perfil: e.target.value }))}
              >
                <option value="conservador">🛡️ Conservador — preservar capital</option>
                <option value="moderado">⚖️ Moderado — balance rendimiento/riesgo</option>
                <option value="arriesgado">🚀 Arriesgado — máximo rendimiento</option>
              </select>
            </div>
            <div>
              <label className="form-label">Objetivo (opcional)</label>
              <input
                className="form-input"
                placeholder="ej: ahorro largo plazo, generar pasivos..."
                value={formPerfil.objetivo}
                onChange={e => setFormPerfil(f => ({ ...f, objetivo: e.target.value }))}
              />
            </div>
            <div>
              <label className="form-label">Capital disponible en ARS (opcional)</label>
              <input
                className="form-input"
                type="number"
                placeholder="ej: 500000"
                value={formPerfil.capital}
                onChange={e => setFormPerfil(f => ({ ...f, capital: e.target.value }))}
              />
            </div>
            <button
              className="btn-primary"
              onClick={guardarPerfil}
              disabled={savingPerfil}
            >
              {savingPerfil ? 'Guardando...' : 'Guardar perfil'}
            </button>
          </div>
        </div>
        <p style={{ fontSize: 13, color: 'var(--fg3)', marginTop: 12 }}>
          Una vez configurado, el sistema comenzará a analizar activos y enviarte recomendaciones por Telegram cada 30 minutos cuando detecte señales.
        </p>
      </div>
    )
  }

  return (
    <div className="tab-content">
      {/* Stats + perfil */}
      <div className="section-header">
        <h2 className="section-title">📈 Inversiones</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--fg2)' }}>
            {perfil && PERFIL_LABELS[perfil.perfil]}
            {perfil?.capital_disponible ? ` · ${fmtARS(perfil.capital_disponible)}` : ''}
          </span>
          <button className="btn-ghost" onClick={() => {
            if (!perfil) return
            setFormPerfil({ perfil: perfil.perfil, objetivo: perfil.objetivo ?? '', capital: String(perfil.capital_disponible ?? '') })
            setEditandoPerfil(true)
          }}>Editar</button>
        </div>
      </div>

      {/* Cards de stats */}
      <div className="cards" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <div className="card">
          <p className="card-label">Winrate</p>
          <p className="card-value" style={{ color: stats?.winrate && stats.winrate >= 50 ? '#22c55e' : '#ef4444' }}>
            {stats?.winrate != null ? `${stats.winrate}%` : '—'}
          </p>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--fg3)' }}>
            {stats?.exitosas ?? 0}/{stats?.aceptadas ?? 0} aceptadas
          </p>
        </div>
        <div className="card">
          <p className="card-label">Decisiones totales</p>
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
              const accionColor = rec.accion === 'comprar' ? '#22c55e' : rec.accion === 'vender' ? '#ef4444' : '#f59e0b'
              const accionEmoji = rec.accion === 'comprar' ? '🟢' : rec.accion === 'vender' ? '🔴' : '🟡'
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
                        <span>Precio: {fmtPrecio(rec.precio_recomendacion, rec.activos?.moneda)}</span>
                        {rec.rsi_momento && <span>RSI: {rec.rsi_momento}</span>}
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
                  {d.ganancia_pct != null && (
                    <span style={{ color: d.ganancia_pct >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                      {d.ganancia_pct >= 0 ? '+' : ''}{d.ganancia_pct}%
                    </span>
                  )}
                  <span style={{ color: resultadoColor, fontSize: 12, whiteSpace: 'nowrap' }}>
                    {resultadoLabel[d.resultado] ?? d.resultado}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--fg3)', whiteSpace: 'nowrap' }}>
                    {new Date(d.fecha_decision).toLocaleDateString('es-AR')}
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
