'use client'

import { useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert, BilleteraBadge } from '@/app/components/design'
import { PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

interface Posicion {
  id: number
  instrumento_id: number
  tipo: string
  monto_ars: number
  monto_usd: number
  monto_usd_entrada: number
  precio_entrada: number | null
  cantidad: number | null
  tna_contratada: number
  fecha_entrada: string
  fecha_vencimiento: string | null
  rendimiento_acumulado: number | null
  broker: string | null
  estado: string
  instrumentos_rf: {
    nombre: string
    tipo: string
    tna_actual: number
    precio_actual: number | null
  }
}

interface RFData {
  posiciones: Posicion[]
  dolar_mep: number
  carry_trade: {
    accion: string
    tna_mensual: number
    carry_mensual: number
  }
  total_usd: number
  total_ars: number
  rendimiento_total_usd: number
}

const COLORS = ['#6366f1', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899', '#84cc16', '#f97316']

export default function LiquidezTab() {
  const [data, setData] = useState<RFData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetchWithAuth('/api/dashboard/rf')
        if (!res.ok) throw new Error('Error al cargar datos de RF')
        const result = await res.json()
        setData(result)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error desconocido')
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <BilleteraAlert variant="danger" title="Error">{error}</BilleteraAlert>
  if (!data) return <p className="empty">Sin datos</p>

  const { posiciones, dolar_mep, carry_trade, total_usd, total_ars, rendimiento_total_usd } = data

  const carryVariant = carry_trade.accion === 'entrar' ? 'green' : carry_trade.accion === 'salir' ? 'red' : 'gold'
  const carryIcon = carry_trade.accion === 'entrar' ? '🟢' : carry_trade.accion === 'salir' ? '🔴' : '🟡'

  // Datos para gráfico de composición
  const composicionData = posiciones.map((pos) => ({
    name: pos.instrumentos_rf?.nombre || 'instrumento',
    value: pos.monto_ars,
    usd: pos.monto_usd || pos.monto_ars / dolar_mep,
  }))

  // Datos para gráfico de rendimiento histórico (generado a partir de posiciones)
  const historicoData = posiciones
    .sort((a, b) => new Date(a.fecha_entrada).getTime() - new Date(b.fecha_entrada).getTime())
    .map((pos) => {
      const fecha = new Date(pos.fecha_entrada)
      return {
        fecha: fecha.toLocaleDateString('es-AR', { month: 'short', day: 'numeric' }),
        rendimiento_usd: (pos.rendimiento_acumulado || 0),
      }
    })

  return (
    <div className="tab-content">
      <div className="section-header">
        <h2 className="section-title">💼 Renta Fija</h2>
      </div>

      {/* Carry Trade */}
      <div className="widget-box">
        <h3 className="widget-title">{carryIcon} Carry Trade</h3>
        <div className="objetivo-stats">
          <div className="obj-stat">
            <span className="obj-stat-label">Acción</span>
            <BilleteraBadge variant={carryVariant}>{carry_trade.accion.toUpperCase()}</BilleteraBadge>
          </div>
          <div className="obj-stat">
            <span className="obj-stat-label">Carry mensual</span>
            <span className="obj-stat-value">{carry_trade.carry_mensual > 0 ? '+' : ''}{carry_trade.carry_mensual.toFixed(2)}%</span>
          </div>
          <div className="obj-stat">
            <span className="obj-stat-label">TNA caución</span>
            <span className="obj-stat-value">{carry_trade.tna_mensual.toFixed(1)}%/mes</span>
          </div>
          <div className="obj-stat">
            <span className="obj-stat-label">Dólar MEP</span>
            <span className="obj-stat-value">${dolar_mep.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</span>
          </div>
        </div>
      </div>

      {/* Resumen */}
      <div className="cards">
        <div className="card">
          <p className="card-label">Capital invertido</p>
          <p className="card-value">${total_ars.toLocaleString('es-AR', { maximumFractionDigits: 0 })}</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>≈ ${total_usd.toLocaleString('es-AR', { maximumFractionDigits: 0 })} USD</p>
        </div>
        <div className="card">
          <p className="card-label">Rendimiento acumulado</p>
          <p className="card-value ingreso">${rendimiento_total_usd > 0 ? '+' : ''}{rendimiento_total_usd.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>{rendimiento_total_usd > 0 ? '+' : ''}{(rendimiento_total_usd / total_usd * 100).toFixed(2)}%</p>
        </div>
        <div className="card">
          <p className="card-label">Posiciones abiertas</p>
          <p className="card-value">{posiciones.length}</p>
        </div>
        <div className="card">
          <p className="card-label">Promedio TNA</p>
          <p className="card-value">
            {posiciones.length > 0
              ? (posiciones.reduce((sum, p) => sum + (p.tna_contratada || 0), 0) / posiciones.length).toFixed(1)
              : '—'}%
          </p>
        </div>
      </div>

      {/* Gráficos */}
      {(posiciones.length > 0 || historicoData.length > 0) && (
        <div className="charts">
          {posiciones.length > 0 && (
            <div className="chart-box">
              <h3>📊 Composición</h3>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={composicionData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, value }) => `${name} $${(value as number) / 1000}k`}
                    outerRadius={80}
                    dataKey="value"
                  >
                    {composicionData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => value !== undefined ? `$${(Number(value) / 1000).toFixed(0)}k` : ''} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {historicoData.length > 0 && (
            <div className="chart-box">
              <h3>📈 Rendimiento</h3>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={historicoData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="fecha" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(value) => value !== undefined ? `$${Number(value).toFixed(2)} USD` : ''} />
                  <Line type="monotone" dataKey="rendimiento_usd" stroke="var(--b-green)" dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Tabla de posiciones */}
      {posiciones.length > 0 ? (
        <div className="table-box">
          <div className="table-header"><h3>📄 Posiciones abiertas</h3></div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Instrumento</th>
                  <th className="right">Monto ARS</th>
                  <th className="right">Precio</th>
                  <th className="right">TNA</th>
                  <th className="right">Variación</th>
                  <th className="right">Vencimiento</th>
                  <th className="right">Rendimiento USD</th>
                </tr>
              </thead>
              <tbody>
                {posiciones.map((pos) => {
                  const inst = pos.instrumentos_rf || ({} as Posicion['instrumentos_rf'])
                  const precio_entrada = pos.precio_entrada || pos.monto_ars
                  const precio_actual = inst.precio_actual || precio_entrada
                  const variacion = ((precio_actual - precio_entrada) / precio_entrada * 100)
                  const venc = pos.fecha_vencimiento ? new Date(pos.fecha_vencimiento).toLocaleDateString('es-AR', { month: 'short', day: 'numeric' }) : '—'
                  const broker_txt = pos.broker ? ` (${pos.broker})` : ''

                  return (
                    <tr key={pos.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{inst.nombre}</div>
                        <div className="muted" style={{ fontSize: 12 }}>{pos.tipo}{broker_txt}</div>
                      </td>
                      <td className="right">${pos.monto_ars.toLocaleString('es-AR', { maximumFractionDigits: 0 })}</td>
                      <td className="right muted">${precio_actual.toLocaleString('es-AR', { maximumFractionDigits: 2 })}</td>
                      <td className="right" style={{ fontWeight: 600 }}>{pos.tna_contratada?.toFixed(1)}%</td>
                      <td className={`right ${variacion > 0 ? 'ingreso' : 'gasto'}`}>
                        {variacion > 0 ? '+' : ''}{variacion.toFixed(2)}%
                      </td>
                      <td className="right muted">{venc}</td>
                      <td className="right ingreso">
                        ${(pos.rendimiento_acumulado ?? 0) > 0 ? '+' : ''}{(pos.rendimiento_acumulado ?? 0).toLocaleString('es-AR', { maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="empty">
          Sin posiciones RF abiertas<br />
          <span>Usá <code>/plan_renta</code> en el bot para crear una</span>
        </p>
      )}

      {/* Tips */}
      <BilleteraAlert variant="info" title="💡 Tips">
        Carry trade {carryIcon} indica si {carry_trade.accion === 'entrar' ? 'conviene estar en ARS' : 'conviene USD'}.
        Rendimiento se actualiza cada vez que se recalculan precios.
        Usá <code>/liquidez</code> en el bot para actualizar precios.
      </BilleteraAlert>
    </div>
  )
}
