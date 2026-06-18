'use client'

import { useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

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

  if (loading) return <div className="flex justify-center p-8">Cargando...</div>
  if (error) return <div className="text-red-600 p-4">⚠️ {error}</div>
  if (!data) return <div className="p-4">Sin datos</div>

  const { posiciones, dolar_mep, carry_trade, total_usd, total_ars, rendimiento_total_usd } = data

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
    .map((pos, idx) => {
      const dias = Math.floor(
        (new Date().getTime() - new Date(pos.fecha_entrada).getTime()) / (1000 * 60 * 60 * 24)
      )
      const fecha = new Date(pos.fecha_entrada)
      return {
        fecha: fecha.toLocaleDateString('es-AR', { month: 'short', day: 'numeric' }),
        rendimiento_usd: (pos.rendimiento_acumulado || 0),
      }
    })

  const COLORS = ['#6366f1', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#ec4899', '#84cc16', '#f97316']

  return (
    <div className="space-y-6">
      {/* Carry Trade */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">{carryIcon} Carry Trade</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-fg2">Acción:</span>
            <p className="font-bold text-lg">{carry_trade.accion.toUpperCase()}</p>
          </div>
          <div>
            <span className="text-fg2">Carry mensual:</span>
            <p className="font-bold text-lg">{carry_trade.carry_mensual:+.2f}%</p>
          </div>
          <div>
            <span className="text-fg2">TNA caución:</span>
            <p className="font-bold">{carry_trade.tna_mensual:.1f}%/mes</p>
          </div>
          <div>
            <span className="text-fg2">Dólar MEP:</span>
            <p className="font-bold">${dolar_mep:,.2f}</p>
          </div>
        </div>
      </div>

      {/* Resumen */}
      <div className="card">
        <h3 className="text-lg font-semibold mb-4">💼 Tu Renta Fija</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-fg2">Capital invertido:</span>
            <p className="font-bold text-lg">${total_ars:,.0f}</p>
            <p className="text-xs text-fg2">≈ ${total_usd:,.0f} USD</p>
          </div>
          <div>
            <span className="text-fg2">Rendimiento acumulado:</span>
            <p className="font-bold text-lg text-green-500">${rendimiento_total_usd:+,.2f}</p>
            <p className="text-xs text-fg2">{(rendimiento_total_usd / total_usd * 100):+.2f}%</p>
          </div>
          <div>
            <span className="text-fg2">Posiciones abiertas:</span>
            <p className="font-bold text-lg">{posiciones.length}</p>
          </div>
          <div>
            <span className="text-fg2">Promedio TNA:</span>
            <p className="font-bold text-lg">
              {posiciones.length > 0 
                ? (posiciones.reduce((sum, p) => sum + (p.tna_contratada || 0), 0) / posiciones.length).toFixed(1)
                : '—'}%
            </p>
          </div>
        </div>
      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-2 gap-4">
        {/* Composición */}
        {posiciones.length > 0 && (
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">📊 Composición</h3>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={composicionData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name} $${value/1000}k`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {composicionData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => `$${(value/1000).toFixed(0)}k`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Rendimiento histórico */}
        {historicoData.length > 0 && (
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">📈 Rendimiento</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={historicoData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="fecha" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: number) => `$${value.toFixed(2)} USD`} />
                <Line type="monotone" dataKey="rendimiento_usd" stroke="#22c55e" dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Tabla de posiciones */}
      {posiciones.length > 0 ? (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4">📄 Posiciones abiertas</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-fg3">
                <tr className="text-fg2 text-xs font-semibold">
                  <th className="text-left py-2">Instrumento</th>
                  <th className="text-right py-2">Monto ARS</th>
                  <th className="text-right py-2">Precio</th>
                  <th className="text-right py-2">TNA</th>
                  <th className="text-right py-2">Variación</th>
                  <th className="text-right py-2">Vencimiento</th>
                  <th className="text-right py-2">Rendimiento USD</th>
                </tr>
              </thead>
              <tbody>
                {posiciones.map((pos) => {
                  const inst = pos.instrumentos_rf || {}
                  const precio_entrada = pos.precio_entrada || pos.monto_ars
                  const precio_actual = inst.precio_actual || precio_entrada
                  const variacion = ((precio_actual - precio_entrada) / precio_entrada * 100)
                  const venc = pos.fecha_vencimiento ? new Date(pos.fecha_vencimiento).toLocaleDateString('es-AR', { month: 'short', day: 'numeric' }) : '—'
                  const broker_txt = pos.broker ? ` (${pos.broker})` : ''

                  return (
                    <tr key={pos.id} className="border-b border-fg3 hover:bg-fg1/30">
                      <td className="py-3">
                        <div className="font-medium">{inst.nombre}</div>
                        <div className="text-xs text-fg2">{pos.tipo}{broker_txt}</div>
                      </td>
                      <td className="text-right">${pos.monto_ars:,.0f}</td>
                      <td className="text-right text-xs text-fg2">
                        ${precio_actual:,.2f}
                      </td>
                      <td className="text-right font-medium">{pos.tna_contratada?.toFixed(1)}%</td>
                      <td className="text-right">
                        <span className={variacion > 0 ? 'text-green-500' : 'text-red-500'}>
                          {variacion:+.2f}%
                        </span>
                      </td>
                      <td className="text-right text-xs text-fg2">{venc}</td>
                      <td className="text-right font-medium">
                        <span className="text-green-500">${pos.rendimiento_acumulado ?? 0:+,.2f}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card text-center py-8 text-fg2">
          <p>Sin posiciones RF abiertas</p>
          <p className="text-xs">Usa <code className="bg-fg1 px-1 rounded">/plan_renta</code> para crear una</p>
        </div>
      )}

      {/* Tips */}
      <div className="card bg-blue-500/10 border border-blue-500/20">
        <h4 className="font-semibold mb-2">💡 Tips</h4>
        <ul className="text-sm text-fg2 space-y-1">
          <li>• Carry trade {carryIcon} indica si {carry_trade.accion === 'entrar' ? 'conviene estar en ARS' : 'conviene USD'}</li>
          <li>• Rendimiento se actualiza cada vez que se recalculan precios</li>
          <li>• Usá <code className="bg-fg1 px-1 rounded text-xs">/liquidez</code> en bot para actualizar precios</li>
        </ul>
      </div>
    </div>
  )
}
