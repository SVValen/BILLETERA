'use client'

import { useEffect, useState, useCallback } from 'react'

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
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

export default function MovimientosTab({ telegramId, mes }: { telegramId: string; mes: string }) {
  const [movements, setMovements] = useState<Movement[]>([])
  const [loading, setLoading] = useState(true)
  const [pagina, setPagina] = useState(1)
  const [paginas, setPaginas] = useState(1)
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [qInput, setQInput] = useState('')
  const [filtroTipo, setFiltroTipo] = useState<'todos' | 'gasto' | 'ingreso'>('todos')

  const fetch_ = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams({
      usuario: telegramId,
      mes,
      pagina: String(pagina),
    })
    if (q) params.set('q', q)
    const r = await fetch(`/api/movements?${params}`)
    const data = await r.json()
    let rows: Movement[] = data.data || []
    if (filtroTipo !== 'todos') rows = rows.filter(m => m.tipo === filtroTipo)
    setMovements(rows)
    setTotal(data.total || 0)
    setPaginas(data.paginas || 1)
    setLoading(false)
  }, [telegramId, mes, pagina, q, filtroTipo])

  useEffect(() => {
    setPagina(1)
  }, [mes, q, filtroTipo])

  useEffect(() => { fetch_() }, [fetch_])

  function buscar() {
    setQ(qInput.trim())
    setPagina(1)
  }

  return (
    <div className="tab-content">
      <div className="section-header">
        <h2 className="section-title">Movimientos</h2>
        <span className="muted" style={{ fontSize: 13 }}>{total} total</span>
      </div>

      {/* Filtros */}
      <div className="filtros">
        <div className="search-row">
          <input
            className="form-input search-input"
            placeholder="Buscar por descripción..."
            value={qInput}
            onChange={e => setQInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && buscar()}
          />
          <button className="btn-primary" onClick={buscar}>Buscar</button>
          {q && <button className="btn-ghost" onClick={() => { setQ(''); setQInput('') }}>✕ Limpiar</button>}
        </div>
        <div className="tipo-filter">
          {(['todos', 'gasto', 'ingreso'] as const).map(t => (
            <button key={t} className={`filter-btn ${filtroTipo === t ? 'active' : ''}`}
              onClick={() => setFiltroTipo(t)}>
              {t === 'todos' ? 'Todos' : t === 'gasto' ? 'Gastos' : 'Ingresos'}
            </button>
          ))}
        </div>
      </div>

      {/* Tabla */}
      <div className="table-box">
        {loading ? (
          <p className="loading">Cargando...</p>
        ) : movements.length === 0 ? (
          <p className="empty">Sin movimientos{q ? ` para "${q}"` : ''} este mes.</p>
        ) : (
          <>
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

            {/* Paginación */}
            {paginas > 1 && (
              <div className="paginacion">
                <button className="btn-ghost" disabled={pagina === 1} onClick={() => setPagina(p => p - 1)}>
                  ← Anterior
                </button>
                <span className="muted">{pagina} / {paginas}</span>
                <button className="btn-ghost" disabled={pagina === paginas} onClick={() => setPagina(p => p + 1)}>
                  Siguiente →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
