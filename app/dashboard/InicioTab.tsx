'use client'

import { useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import {
  PieChart, Pie, Cell, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
} from 'recharts'

const COLORS = [
  '#6366f1', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7',
  '#ec4899', '#84cc16', '#f97316', '#14b8a6', '#8b5cf6',
  '#0ea5e9', '#d946ef', '#10b981', '#fb923c',
]

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

function fmtK(v: number | string | undefined | null) {
  const n = typeof v === 'number' ? v : 0
  return n >= 1_000_000
    ? `$${(n / 1_000_000).toFixed(1)}M`
    : `$${(n / 1000).toFixed(0)}k`
}

interface Stats {
  mes: string
  total_gastos: number
  total_ingresos: number
  saldo: number
  por_categoria: Record<string, { monto: number; emoji: string }>
}

interface Metricas {
  mes: string
  mes_anterior: string
  tasa_ahorro: { actual: number | null; anterior: number | null }
  medio_pago: {
    actual: { efectivo_pct: number; tarjeta_pct: number } | null
    anterior: { efectivo_pct: number; tarjeta_pct: number } | null
  }
  categorias_cambio: { nombre: string; emoji: string; monto: number; monto_anterior: number; pct_cambio: number }[]
}

// Tooltip personalizado para el donut
function PieTooltip({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number; payload: { pct: number } }> }) {
  if (!active || !payload?.length) return null
  const { name, value, payload: p } = payload[0]
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 13 }}>
      <div style={{ fontWeight: 600 }}>{name}</div>
      <div>{fmt(value)} · {p.pct}%</div>
    </div>
  )
}

export default function InicioTab({ mes }: { mes: string }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [metricas, setMetricas] = useState<Metricas | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [sRes, mRes] = await Promise.all([
          fetchWithAuth(`/api/stats?mes=${mes}`),
          fetchWithAuth(`/api/stats?mes=${mes}&resource=metricas`),
        ])
        if (cancelled) return
        if (!sRes.ok) throw new Error('Error al cargar estadísticas')
        const [sData, mData] = await Promise.all([sRes.json(), mRes.json()])
        if (cancelled) return
        setStats(sData)
        setMetricas(mRes.ok ? mData : null)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Error desconocido')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [mes])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <div className="error-banner">{error}</div>
  if (!stats) return null

  // Categorías ordenadas por monto desc
  const cats = Object.entries(stats.por_categoria)
    .map(([name, v]) => ({ name: `${v.emoji} ${name}`, value: v.monto }))
    .sort((a, b) => b.value - a.value)

  const total = cats.reduce((s, c) => s + c.value, 0)
  const pieData = cats.map(c => ({ ...c, pct: total > 0 ? Math.round(c.value / total * 100) : 0 }))

  const barData = [{ name: mes, Gastos: stats.total_gastos, Ingresos: stats.total_ingresos }]

  return (
    <>
      {/* Tarjetas */}
      <div className="cards">
        <div className="card">
          <p className="card-label">Gastos</p>
          <p className="card-value gasto">{fmt(stats.total_gastos)}</p>
        </div>
        <div className="card">
          <p className="card-label">Ingresos</p>
          <p className="card-value ingreso">{fmt(stats.total_ingresos)}</p>
        </div>
        <div className="card">
          <p className="card-label">Saldo</p>
          <p className={`card-value ${stats.saldo >= 0 ? 'ingreso' : 'gasto'}`}>{fmt(stats.saldo)}</p>
        </div>
      </div>

      {/* Gráficos */}
      <div className="charts">
        {/* Donut por categoría */}
        <div className="chart-box">
          <h3>Por categoría</h3>
          {pieData.length === 0 ? (
            <p className="empty">Sin gastos este mes</p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={90}
                    paddingAngle={2}
                    label={false}
                  >
                    {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip content={<PieTooltip />} />
                </PieChart>
              </ResponsiveContainer>

              {/* Lista de categorías debajo */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                {pieData.map((c, i) => (
                  <div key={c.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: COLORS[i % COLORS.length], flexShrink: 0 }} />
                    <span style={{ flex: 1, color: 'var(--fg1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                    <span style={{ color: 'var(--fg3)', fontSize: 12, marginLeft: 4 }}>{c.pct}%</span>
                    <span style={{ fontWeight: 600, flexShrink: 0 }}>{fmt(c.value)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Bar chart */}
        <div className="chart-box">
          <h3>Resumen del mes</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={barData} margin={{ top: 4, right: 4, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={52} />
              <Tooltip formatter={(v) => fmt(v as number)} />
              <Bar dataKey="Gastos" fill="#ef4444" radius={[6, 6, 0, 0]} label={{ position: 'top', formatter: (v: any) => fmtK(v), fontSize: 11, fill: 'var(--fg2)' }} />
              <Bar dataKey="Ingresos" fill="#22c55e" radius={[6, 6, 0, 0]} label={{ position: 'top', formatter: (v: any) => fmtK(v), fontSize: 11, fill: 'var(--fg2)' }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Comparado con el mes pasado */}
      {metricas && (
        <div className="widget-box">
          <h3 className="widget-title">📊 Comparado con el mes pasado</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {metricas.tasa_ahorro.actual !== null && (
              <div style={{ fontSize: 14 }}>
                {metricas.tasa_ahorro.anterior !== null ? (
                  <>Ahorraste el <b>{metricas.tasa_ahorro.actual.toFixed(0)}%</b> de tus ingresos
                    {' '}(<span className={metricas.tasa_ahorro.actual >= metricas.tasa_ahorro.anterior ? 'ingreso' : 'gasto'}>
                      {metricas.tasa_ahorro.actual >= metricas.tasa_ahorro.anterior ? '▲' : '▼'} vs. {metricas.tasa_ahorro.anterior.toFixed(0)}% el mes pasado
                    </span>)
                  </>
                ) : (
                  <>Ahorraste el <b>{metricas.tasa_ahorro.actual.toFixed(0)}%</b> de tus ingresos este mes.</>
                )}
              </div>
            )}

            {metricas.medio_pago.actual && (
              <div style={{ fontSize: 14 }}>
                Pagaste <b>{metricas.medio_pago.actual.efectivo_pct}% en efectivo</b> y <b>{metricas.medio_pago.actual.tarjeta_pct}% con tarjeta</b>
                {metricas.medio_pago.anterior && (
                  <span className="muted"> (mes pasado: {metricas.medio_pago.anterior.efectivo_pct}% / {metricas.medio_pago.anterior.tarjeta_pct}%)</span>
                )}
              </div>
            )}

            {metricas.categorias_cambio.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                {metricas.categorias_cambio.map(c => (
                  <div key={c.nombre} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                    <span>{c.emoji} {c.nombre}</span>
                    <span style={{ marginLeft: 'auto', fontWeight: 600 }} className={c.pct_cambio <= 0 ? 'ingreso' : 'gasto'}>
                      {c.pct_cambio > 0 ? '▲' : '▼'} {Math.abs(c.pct_cambio)}% {c.pct_cambio <= 0 ? 'menos' : 'más'} que el mes pasado
                    </span>
                  </div>
                ))}
              </div>
            )}

            {!metricas.tasa_ahorro.actual && !metricas.medio_pago.actual && metricas.categorias_cambio.length === 0 && (
              <p className="muted" style={{ fontSize: 13, margin: 0 }}>Sin datos suficientes para comparar este mes.</p>
            )}
          </div>
        </div>
      )}
    </>
  )
}
