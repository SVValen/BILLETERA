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

const COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899']

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

function Card({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 12, padding: '20px 24px',
      boxShadow: '0 1px 4px rgba(0,0,0,.08)',
    }}>
      <p style={{ margin: 0, fontSize: 13, color: '#888' }}>{label}</p>
      <p style={{ margin: '6px 0 0', fontSize: 26, fontWeight: 700, color: color ?? '#111' }}>{value}</p>
    </div>
  )
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
      const [statsRes, movRes] = await Promise.all([
        fetch(`/api/stats?mes=${mes}`),
        fetch(`/api/movements?mes=${mes}`),
      ])
      if (!statsRes.ok || !movRes.ok) throw new Error('Error al cargar datos')
      const [statsData, movData] = await Promise.all([statsRes.json(), movRes.json()])
      setStats(statsData)
      setMovements(movData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }, [mes])

  useEffect(() => { fetchData() }, [fetchData])

  const pieData = stats
    ? Object.entries(stats.por_categoria).map(([name, v]) => ({ name: `${v.emoji} ${name}`, value: v.monto }))
    : []

  const barData = stats
    ? [{ name: 'Mes', Gastos: stats.total_gastos, Ingresos: stats.total_ingresos }]
    : []

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '32px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Billetera 💰</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 14, color: '#555' }}>Mes:</label>
          <input
            type="month"
            value={mes}
            onChange={e => setMes(e.target.value)}
            style={{
              border: '1px solid #ddd', borderRadius: 8, padding: '6px 10px',
              fontSize: 14, background: '#fff', cursor: 'pointer',
            }}
          />
        </div>
      </div>

      {error && (
        <div style={{ background: '#fee2e2', color: '#b91c1c', borderRadius: 8, padding: '12px 16px', marginBottom: 20 }}>
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: '#888', textAlign: 'center', marginTop: 60 }}>Cargando...</p>
      ) : stats && (
        <>
          {/* Tarjetas resumen */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 32 }}>
            <Card label="Total Gastos" value={fmt(stats.total_gastos)} color="#ef4444" />
            <Card label="Total Ingresos" value={fmt(stats.total_ingresos)} color="#22c55e" />
            <Card label="Saldo" value={fmt(stats.saldo)} color={stats.saldo >= 0 ? '#22c55e' : '#ef4444'} />
          </div>

          {/* Gráficos */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
            {/* Pie chart */}
            <div style={{ background: '#fff', borderRadius: 12, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 15 }}>Gastos por categoría</h3>
              {pieData.length === 0 ? (
                <p style={{ color: '#aaa', textAlign: 'center', margin: '40px 0' }}>Sin datos</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={false}>
                      {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v: number) => fmt(v)} />
                    <Legend iconSize={10} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Bar chart */}
            <div style={{ background: '#fff', borderRadius: 12, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 15 }}>Resumen del mes</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={barData} margin={{ top: 0, right: 0, left: 20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v: number) => fmt(v)} />
                  <Bar dataKey="Gastos" fill="#ef4444" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="Ingresos" fill="#22c55e" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Tabla movimientos */}
          <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px 12px', borderBottom: '1px solid #f0f0f0' }}>
              <h3 style={{ margin: 0, fontSize: 15 }}>Movimientos</h3>
            </div>
            {movements.length === 0 ? (
              <p style={{ color: '#aaa', textAlign: 'center', padding: '40px 0' }}>
                Sin movimientos este mes.<br />
                <span style={{ fontSize: 13 }}>Enviá un mensaje a tu bot de Telegram para registrar uno.</span>
              </p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: '#f9f9f9' }}>
                    {['Fecha', 'Descripción', 'Categoría', 'Origen', 'Monto'].map(h => (
                      <th key={h} style={{ textAlign: h === 'Monto' ? 'right' : 'left', padding: '10px 16px', fontWeight: 600, color: '#555', fontSize: 12 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {movements.map(m => (
                    <tr key={m.id} style={{ borderTop: '1px solid #f0f0f0' }}>
                      <td style={{ padding: '12px 16px', color: '#888', whiteSpace: 'nowrap' }}>{m.fecha}</td>
                      <td style={{ padding: '12px 16px' }}>{m.descripcion}</td>
                      <td style={{ padding: '12px 16px' }}>
                        {m.categorias ? `${m.categorias.emoji} ${m.categorias.nombre}` : '—'}
                      </td>
                      <td style={{ padding: '12px 16px', color: '#aaa', fontSize: 12 }}>{m.origen}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, color: m.tipo === 'gasto' ? '#ef4444' : '#22c55e' }}>
                        {m.tipo === 'gasto' ? '-' : '+'}{fmt(m.monto)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
