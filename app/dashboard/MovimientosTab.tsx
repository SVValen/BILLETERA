'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

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
  tarjeta_id: number | null
  tarjetas: { nombre: string } | null
  forma_pago: string
}

const CATEGORIAS = [
  { id: 1,  emoji: '🛒', nombre: 'Supermercado' },
  { id: 2,  emoji: '🚗', nombre: 'Transporte' },
  { id: 3,  emoji: '🍽️', nombre: 'Comida' },
  { id: 4,  emoji: '💡', nombre: 'Servicios' },
  { id: 5,  emoji: '🎬', nombre: 'Entretenimiento' },
  { id: 6,  emoji: '🏥', nombre: 'Salud' },
  { id: 7,  emoji: '📌', nombre: 'Otros' },
  { id: 8,  emoji: '👕', nombre: 'Ropa' },
  { id: 9,  emoji: '📚', nombre: 'Educación' },
  { id: 10, emoji: '🏠', nombre: 'Vivienda' },
  { id: 11, emoji: '🐾', nombre: 'Mascotas' },
  { id: 12, emoji: '✈️', nombre: 'Viajes' },
  { id: 13, emoji: '🛡️', nombre: 'Seguros' },
  { id: 14, emoji: '💰', nombre: 'Inversiones' },
  { id: 15, emoji: '💳', nombre: 'Compras Online' },
  { id: 16, emoji: '✨', nombre: 'Belleza' },
  { id: 17, emoji: '💵', nombre: 'Ingresos' },
  { id: 18, emoji: '📱', nombre: 'Suscripciones' },
]

export default function MovimientosTab({ mes }: { mes: string }) {
  const [movements, setMovements] = useState<Movement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pagina, setPagina] = useState(1)
  const [paginas, setPaginas] = useState(1)
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [qInput, setQInput] = useState('')
  const [filtroTipo, setFiltroTipo] = useState<'todos' | 'gasto' | 'ingreso'>('todos')
  const [filtroCategoria, setFiltroCategoria] = useState('')
  const [fechaDesde, setFechaDesde] = useState('')
  const [fechaHasta, setFechaHasta] = useState('')

  const fetch_ = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ mes, pagina: String(pagina) })
      if (q) params.set('q', q)
      if (filtroTipo !== 'todos') params.set('tipo', filtroTipo)
      if (filtroCategoria) params.set('categoria_id', filtroCategoria)
      if (fechaDesde) params.set('fecha_desde', fechaDesde)
      if (fechaHasta) params.set('fecha_hasta', fechaHasta)
      const r = await fetchWithAuth(`/api/movements?${params}`)
      if (!r.ok) throw new Error('Error al cargar movimientos')
      const data = await r.json()
      setMovements(data.data || [])
      setTotal(data.total || 0)
      setPaginas(data.paginas || 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }, [mes, pagina, q, filtroTipo, filtroCategoria, fechaDesde, fechaHasta])

  useEffect(() => {
    setPagina(1)
  }, [mes, q, filtroTipo, filtroCategoria, fechaDesde, fechaHasta])

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
        <div className="filtros-row">
          <div className="tipo-filter">
            {(['todos', 'gasto', 'ingreso'] as const).map(t => (
              <button key={t} className={`filter-btn ${filtroTipo === t ? 'active' : ''}`}
                onClick={() => setFiltroTipo(t)}>
                {t === 'todos' ? 'Todos' : t === 'gasto' ? 'Gastos' : 'Ingresos'}
              </button>
            ))}
          </div>
          <select
            className="cat-select"
            value={filtroCategoria}
            onChange={e => setFiltroCategoria(e.target.value)}
          >
            <option value="">Todas las categorías</option>
            {CATEGORIAS.map(c => (
              <option key={c.id} value={String(c.id)}>{c.emoji} {c.nombre}</option>
            ))}
          </select>
          <input
            type="date"
            className="form-input"
            value={fechaDesde}
            max={fechaHasta || undefined}
            onChange={e => setFechaDesde(e.target.value)}
            title="Desde"
          />
          <input
            type="date"
            className="form-input"
            value={fechaHasta}
            min={fechaDesde || undefined}
            onChange={e => setFechaHasta(e.target.value)}
            title="Hasta"
          />
          {(fechaDesde || fechaHasta) && (
            <button className="btn-ghost" onClick={() => { setFechaDesde(''); setFechaHasta('') }}>
              ✕ Quitar fechas
            </button>
          )}
        </div>
      </div>

      {/* Tabla */}
      <div className="table-box">
        {error ? (
          <div className="error-banner">{error} <button className="btn-ghost" onClick={fetch_}>Reintentar</button></div>
        ) : loading ? (
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
                    <th>Medio de pago</th>
                    <th>Forma de pago</th>
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
                      <td>{m.tarjetas ? `💳 ${m.tarjetas.nombre}` : '💵 Efectivo'}</td>
                      <td className="muted">{m.forma_pago}</td>
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
