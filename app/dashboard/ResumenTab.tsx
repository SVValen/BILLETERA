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

export default function ResumenTab({ mes }: { mes: string }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [cuotas, setCuotas] = useState<Cuota[]>([])
  const [recurrentes, setRecurrentes] = useState<Recurrente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [sRes, cRes, rRes] = await Promise.all([
          fetchWithAuth(`/api/stats?mes=${mes}`),
          fetchWithAuth(`/api/cuotas?mes=${mes}`),
          fetchWithAuth(`/api/recurrentes?dias=35`),
        ])
        if (cancelled) return
        if (!sRes.ok) throw new Error('Error al cargar estadísticas')
        const [sData, cData, rData] = await Promise.all([sRes.json(), cRes.json(), rRes.json()])
        if (cancelled) return
        setStats(sData)
        setCuotas(Array.isArray(cData) ? cData : [])
        setRecurrentes(Array.isArray(rData) ? rData : [])
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

      {/* Cuotas en proceso */}
      {cuotas.length > 0 && (
        <div className="widget-box">
          <h3 className="widget-title">💳 Cuotas en proceso</h3>
          <div className="cuotas-list">
            {cuotas.map(c => (
              <div key={c.id} className="cuota-item">
                <div className="cuota-header">
                  <span className="cuota-desc">{c.emoji} {c.descripcion}</span>
                  <span className="cuota-monto">{fmt(c.monto_cuota)}/mes</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${c.porcentaje}%` }} />
                </div>
                <div className="cuota-meta">
                  <span>Cuota {c.pagadas}/{c.num_cuotas}</span>
                  {c.proxima_cuota && (
                    <span className="muted">Próxima: {new Date(c.proxima_cuota + 'T12:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })}</span>
                  )}
                </div>
              </div>
            ))}
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
                  {r.dias_faltan === 0 ? 'Hoy' : r.dias_faltan === 1 ? 'Mañana' : `en ${r.dias_faltan}d`}
                </span>
                <span className="recurrente-monto">{fmt(r.monto)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
