'use client'

import { useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert } from '@/app/components/design'
import { fmt, nombreMes, Chevron } from './mes-utils'

interface MesProx {
  mes: string
  entra: number
  sale: number
  te_queda: number
  hay_estimados: boolean
  entra_grupos: { grupo: string; total: number }[]
  sale_grupos: { grupo: string; nombre: string; total: number }[]
}

export default function ProximosTab({ desde, onAbrirMes }: { desde: string; onAbrirMes: (mes: string) => void }) {
  const [meses, setMeses] = useState<MesProx[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [abierto, setAbierto] = useState<string | null>(null)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    fetchWithAuth(`/api/stats?mes=${desde}&resource=proximos&n=6`)
      .then(r => r.json())
      .then(d => {
        if (cancel) return
        if (d?.error) setError(d.error)
        else setMeses(d.meses ?? [])
      })
      .catch(e => { if (!cancel) setError(e instanceof Error ? e.message : 'No se pudo cargar') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [desde])

  if (loading) return <p className="loading">Cargando...</p>
  if (error) return <BilleteraAlert variant="danger" title="No se pudo cargar">{error}</BilleteraAlert>

  const max = Math.max(1, ...meses.map(m => Math.max(m.entra, m.sale)))

  return (
    <div className="mes">
      <div className="mes-intro">
        <h2 className="mes-titulo">Próximos meses</h2>
        <p>Lo que ya sabés que entra y lo que ya está comprometido (cuotas, préstamos, alquiler). No incluye lo que todavía no gastaste.</p>
      </div>

      <section className="mes-card" aria-label="Próximos meses">
        {meses.map(m => {
          const ab = abierto === m.mes
          return (
            <div key={m.mes} className="prox-mes">
              <button type="button" className="prox-row" aria-expanded={ab} onClick={() => setAbierto(ab ? null : m.mes)}>
                <Chevron dir={ab ? 'down' : 'right'} />
                <span className="prox-nombre">{nombreMes(m.mes)}{m.hay_estimados && <span className="mes-det"> · con estimados</span>}</span>
                <span className="prox-barras" aria-hidden="true">
                  <span className="prox-barra prox-barra-entra" style={{ width: `${(m.entra / max) * 100}%` }} title={`Entra ${fmt(m.entra)}`} />
                  <span className="prox-barra prox-barra-sale" style={{ width: `${(m.sale / max) * 100}%` }} title={`Comprometido ${fmt(m.sale)}`} />
                </span>
                <span className="prox-cifras">
                  <span><span className="mes-label">Entra</span> {fmt(m.entra)}</span>
                  <span><span className="mes-label">Comprometido</span> {fmt(m.sale)}</span>
                </span>
                {m.entra > 0
                  ? <span className={`prox-queda ${m.te_queda < 0 ? 'negativo' : ''}`}>{fmt(m.te_queda)}</span>
                  : <span className="prox-queda sin-datos">Faltan cargar ingresos</span>}
              </button>
              {ab && (
                <div className="prox-detalle">
                  <div>
                    <h4>Entra</h4>
                    {m.entra_grupos.length === 0 && <p className="mes-det">Sin ingresos cargados todavía.</p>}
                    {m.entra_grupos.map(g => <div className="mes-sub" key={g.grupo}><span>{g.grupo}</span><span>{fmt(g.total)}</span></div>)}
                  </div>
                  <div>
                    <h4>Comprometido</h4>
                    {m.sale_grupos.map(g => <div className="mes-sub" key={g.grupo}><span>{g.nombre}</span><span>{fmt(g.total)}</span></div>)}
                  </div>
                  <button type="button" className="mes-link" onClick={() => onAbrirMes(m.mes)}>Abrir {nombreMes(m.mes)}</button>
                </div>
              )}
            </div>
          )
        })}
        <div className="prox-leyenda" aria-hidden="true">
          <span><i className="prox-barra-entra" /> Entra</span>
          <span><i className="prox-barra-sale" /> Comprometido</span>
          <span className="prox-leyenda-queda">Te quedaría</span>
        </div>
      </section>
    </div>
  )
}
