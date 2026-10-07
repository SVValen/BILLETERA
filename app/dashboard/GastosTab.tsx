'use client'

import { useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert } from '@/app/components/design'
import { fmt, nombreMes, mesCorto, sumarMeses } from './mes-utils'

interface Rubro { rubro: string; monto: number; anterior: number; pct: number }
interface Datos { mes: string; total: number; total_anterior: number; rubros: Rubro[] }

export default function GastosTab({ mes }: { mes: string }) {
  const [data, setData] = useState<Datos | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    fetchWithAuth(`/api/stats?mes=${mes}&resource=rubros`)
      .then(r => r.json())
      .then(d => { if (!cancel) { if (d?.error) setError(d.error); else setData(d) } })
      .catch(e => { if (!cancel) setError(e instanceof Error ? e.message : 'No se pudo cargar') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [mes])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <BilleteraAlert variant="danger" title="No se pudo cargar">{error}</BilleteraAlert>
  if (!data || data.rubros.length === 0) return <p className="empty">No hay gastos en {nombreMes(mes)}.</p>

  const max = Math.max(1, ...data.rubros.map(r => r.monto))
  const ant = mesCorto(sumarMeses(mes, -1))
  const dif = data.total - data.total_anterior

  return (
    <div className="mes">
      <div className="mes-intro">
        <h2 className="mes-titulo">En qué gasto · {nombreMes(mes)}</h2>
        <p>
          Sale <strong>{fmt(data.total)}</strong>
          {data.total_anterior > 0 && <> · {dif >= 0 ? `${fmt(dif)} más` : `${fmt(-dif)} menos`} que en {ant}</>}
        </p>
      </div>
      <section className="mes-card" aria-label="Gastos por rubro">
        <table className="rubros">
          <thead>
            <tr>
              <th scope="col">Rubro</th>
              <th scope="col"><span className="sr-only">Proporción</span></th>
              <th scope="col" className="num">{mesCorto(mes)}</th>
              <th scope="col" className="num">{ant}</th>
            </tr>
          </thead>
          <tbody>
            {data.rubros.map(r => {
              const cambio = r.anterior > 0 ? Math.round(((r.monto - r.anterior) / r.anterior) * 100) : null
              return (
                <tr key={r.rubro} title={`${r.rubro}: ${fmt(r.monto)} (${r.pct}% del mes)`}>
                  <th scope="row">{r.rubro}<span className="mes-det"> · {r.pct}%</span></th>
                  <td className="rubros-barra-celda">
                    <span className="rubros-barra" style={{ width: `${Math.max(1, (r.monto / max) * 100)}%` }} />
                  </td>
                  <td className="num"><strong>{fmt(r.monto)}</strong></td>
                  <td className="num mes-det">
                    {r.anterior > 0 ? fmt(r.anterior) : '—'}
                    {cambio != null && Math.abs(cambio) >= 10 && <span className="rubros-cambio"> ({cambio > 0 ? '+' : ''}{cambio}%)</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </div>
  )
}
