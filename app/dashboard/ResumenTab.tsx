'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
} from 'recharts'

const COLORS = ['#6366f1', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899', '#84cc16']

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
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

export default function ResumenTab({ telegramId, mes }: { telegramId: string; mes: string }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [cuotas, setCuotas] = useState<Cuota[]>([])
  const [recurrentes, setRecurrentes] = useState<Recurrente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sRes, cRes, rRes] = await Promise.all([
        fetch(`/api/stats?mes=${mes}&usuario=${telegramId}`),
        fetch(`/api/cuotas?usuario=${telegramId}`),
        fetch(`/api/recurrentes?usuario=${telegramId}&dias=35`),
      ])
      if (!sRes.ok) throw new Error('Error al cargar estadísticas')
      const [sData, cData, rData] = await Promise.all([sRes.json(), cRes.json(), rRes.json()])
      setStats(sData)
      setCuotas(Array.isArray(cData) ? cData : [])
      setRecurrentes(Array.isArray(rData) ? rData : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }, [mes, telegramId])

  useEffect(() => { fetchData() }, [fetchData])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <div className="error-banner">{error}</div>
  if (!stats) return null

  const pieData = Object.entries(stats.por_categoria).map(([name, v]) => ({
    name: `${v.emoji} ${name}`, value: v.monto,
  }))
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
        <div className="chart-box">
          <h3>Por categoría</h3>
          {pieData.length === 0 ? (
            <p className="empty">Sin gastos este mes</p>
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={85} label={false}>
                  {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmt(v as number)} />
                <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="chart-box">
          <h3>Resumen del mes</h3>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={barData} margin={{ top: 4, right: 4, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => fmt(v as number)} />
              <Bar dataKey="Gastos" fill="#ef4444" radius={[6, 6, 0, 0]} />
              <Bar dataKey="Ingresos" fill="#22c55e" radius={[6, 6, 0, 0]} />
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
                  <span className="muted">Próxima: {new Date(c.proxima_cuota + 'T12:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })}</span>
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
