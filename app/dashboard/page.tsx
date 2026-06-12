'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
} from 'recharts'

interface Stats {
  mes: string
  total_gastos: number
  total_ingresos: number
  saldo: number
  por_categoria: Record<string, { monto: number; emoji: string }>
}

interface Movement {
  id: number
  fecha: string
  descripcion: string
  monto: number
  tipo: 'gasto' | 'ingreso'
  origen: string
  categorias: { nombre: string; emoji: string } | null
}

const COLORS = ['#6366f1', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899', '#84cc16']

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', {
    style: 'currency', currency: 'ARS', maximumFractionDigits: 0,
  }).format(n)
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [movements, setMovements] = useState<Movement[]>([])
  const [mes, setMes] = useState(() => new Date().toISOString().slice(0, 7))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sRes, mRes] = await Promise.all([
        fetch(`/api/stats?mes=${mes}`),
        fetch(`/api/movements?mes=${mes}`),
      ])
      if (!sRes.ok || !mRes.ok) throw new Error('Error al cargar datos')
      const [sData, mData] = await Promise.all([sRes.json(), mRes.json()])
      setStats(sData)
      setMovements(mData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }, [mes])

  useEffect(() => { fetchData() }, [fetchData])

  const pieData = stats
    ? Object.entries(stats.por_categoria).map(([name, v]) => ({
        name: `${v.emoji} ${name}`,
        value: v.monto,
      }))
    : []

  const barData = stats
    ? [{ name: mes, Gastos: stats.total_gastos, Ingresos: stats.total_ingresos }]
    : []

  return (
    <div className="page">
      {/* Header */}
      <div className="header">
        <h1>Billetera 💰</h1>
        <div className="header-right">
          <label htmlFor="mes-input">Mes:</label>
          <input
            id="mes-input"
            type="month"
            value={mes}
            onChange={e => setMes(e.target.value)}
            className="month-input"
          />
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="loading">Cargando...</p>
      ) : stats && (
        <>
          {/* Tarjetas resumen */}
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
              <p className={`card-value ${stats.saldo >= 0 ? 'ingreso' : 'gasto'}`}>
                {fmt(stats.saldo)}
              </p>
            </div>
          </div>

          {/* Gráficos */}
          <div className="charts">
            <div className="chart-box">
              <h3>Por categoría</h3>
              {pieData.length === 0 ? (
                <p className="empty">Sin datos</p>
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

          {/* Tabla */}
          <div className="table-box">
            <div className="table-header">
              <h3>Movimientos{movements.length > 0 ? ` (${movements.length})` : ''}</h3>
            </div>
            {movements.length === 0 ? (
              <p className="empty">
                Sin movimientos este mes.<br />
                <span>Enviá un mensaje a tu bot de Telegram para registrar uno.</span>
              </p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Descripción</th>
                      <th>Categoría</th>
                      <th>Origen</th>
                      <th className="right">Monto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {movements.map(m => (
                      <tr key={m.id}>
                        <td className="date">{m.fecha}</td>
                        <td>{m.descripcion}</td>
                        <td>{m.categorias ? `${m.categorias.emoji} ${m.categorias.nombre}` : '—'}</td>
                        <td className="muted">{m.origen}</td>
                        <td className={`right ${m.tipo}`}>
                          {m.tipo === 'gasto' ? '-' : '+'}{fmt(m.monto)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
