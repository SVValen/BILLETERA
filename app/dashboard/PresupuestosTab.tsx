'use client'

import { useEffect, useState, useCallback } from 'react'

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

interface Presupuesto {
  id: number
  categoria_id: number
  categoria: string
  emoji: string
  presupuestado: number
  gastado: number
  disponible: number
  porcentaje: number
}

const CATEGORIAS = [
  { id: 1, nombre: 'Supermercado', emoji: '🛒' },
  { id: 2, nombre: 'Transporte', emoji: '🚗' },
  { id: 3, nombre: 'Comida', emoji: '🍽️' },
  { id: 4, nombre: 'Servicios', emoji: '💡' },
  { id: 5, nombre: 'Entretenimiento', emoji: '🎬' },
  { id: 6, nombre: 'Salud', emoji: '🏥' },
  { id: 8, nombre: 'Ropa', emoji: '👕' },
  { id: 9, nombre: 'Educación', emoji: '📚' },
  { id: 10, nombre: 'Vivienda', emoji: '🏠' },
  { id: 11, nombre: 'Mascotas', emoji: '🐾' },
  { id: 12, nombre: 'Viajes', emoji: '✈️' },
  { id: 13, nombre: 'Seguros', emoji: '🛡️' },
  { id: 14, nombre: 'Inversiones', emoji: '💰' },
  { id: 15, nombre: 'Compras Online', emoji: '💳' },
  { id: 16, nombre: 'Belleza', emoji: '✨' },
]

export default function PresupuestosTab({ telegramId, mes }: { telegramId: string; mes: string }) {
  const [presupuestos, setPresupuestos] = useState<Presupuesto[]>([])
  const [loading, setLoading] = useState(true)
  const [editando, setEditando] = useState<{ id?: number; cat_id: number; nombre: string; emoji: string } | null>(null)
  const [inputMonto, setInputMonto] = useState('')
  const [saving, setSaving] = useState(false)
  const [showAdd, setShowAdd] = useState(false)

  const fetch_ = useCallback(async () => {
    setLoading(true)
    const r = await fetch(`/api/presupuestos?usuario=${telegramId}&mes=${mes}`)
    const data = await r.json()
    setPresupuestos(Array.isArray(data) ? data : [])
    setLoading(false)
  }, [telegramId, mes])

  useEffect(() => { fetch_() }, [fetch_])

  async function guardar() {
    if (!editando || !inputMonto) return
    setSaving(true)
    const monto = parseFloat(inputMonto.replace(/\./g, '').replace(',', '.'))
    await fetch('/api/presupuestos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario: telegramId, categoria_id: editando.cat_id, monto, mes }),
    })
    setEditando(null)
    setInputMonto('')
    setSaving(false)
    setShowAdd(false)
    await fetch_()
  }

  async function eliminar(id: number) {
    await fetch(`/api/presupuestos?id=${id}`, { method: 'DELETE' })
    await fetch_()
  }

  const catsSinPresupuesto = CATEGORIAS.filter(c => !presupuestos.find(p => p.categoria_id === c.id))

  return (
    <div className="tab-content">
      <div className="section-header">
        <h2 className="section-title">Presupuestos — {mes}</h2>
        {catsSinPresupuesto.length > 0 && (
          <button className="btn-primary" onClick={() => setShowAdd(!showAdd)}>
            + Agregar
          </button>
        )}
      </div>

      {showAdd && (
        <div className="form-card">
          <p className="form-label">Categoría</p>
          <select
            className="form-select"
            onChange={e => {
              const cat = CATEGORIAS.find(c => c.id === +e.target.value)
              if (cat) setEditando({ cat_id: cat.id, nombre: cat.nombre, emoji: cat.emoji })
            }}
            defaultValue=""
          >
            <option value="" disabled>Elegir categoría...</option>
            {catsSinPresupuesto.map(c => (
              <option key={c.id} value={c.id}>{c.emoji} {c.nombre}</option>
            ))}
          </select>
          <p className="form-label" style={{ marginTop: 12 }}>Presupuesto mensual</p>
          <div className="form-row">
            <input
              className="form-input"
              type="number"
              placeholder="Ej: 20000"
              value={inputMonto}
              onChange={e => setInputMonto(e.target.value)}
            />
            <button className="btn-primary" onClick={guardar} disabled={saving || !editando || !inputMonto}>
              {saving ? '...' : 'Guardar'}
            </button>
            <button className="btn-ghost" onClick={() => { setShowAdd(false); setEditando(null); setInputMonto('') }}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="loading">Cargando...</p>
      ) : presupuestos.length === 0 ? (
        <div className="empty">
          Sin presupuestos para {mes}.<br />
          <span>Usá el botón "Agregar" o mandá /presupuesto comida 20000 en el bot.</span>
        </div>
      ) : (
        <div className="presupuestos-list">
          {presupuestos.map(p => {
            const color = p.porcentaje >= 100 ? '#ef4444' : p.porcentaje >= 80 ? '#f59e0b' : '#22c55e'
            const isEdit = editando?.id === p.id
            return (
              <div key={p.id} className="pres-item">
                <div className="pres-header">
                  <span className="pres-cat">{p.emoji} {p.categoria}</span>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className="pres-pct" style={{ color }}>{p.porcentaje.toFixed(0)}%</span>
                    <button className="btn-icon" onClick={() => {
                      setEditando({ id: p.id, cat_id: p.categoria_id, nombre: p.categoria, emoji: p.emoji })
                      setInputMonto(String(p.presupuestado))
                      setShowAdd(false)
                    }}>✏️</button>
                    <button className="btn-icon" onClick={() => eliminar(p.id)}>🗑️</button>
                  </div>
                </div>
                {isEdit ? (
                  <div className="form-row" style={{ marginTop: 8 }}>
                    <input className="form-input" type="number" value={inputMonto}
                      onChange={e => setInputMonto(e.target.value)} />
                    <button className="btn-primary" onClick={guardar} disabled={saving}>{saving ? '...' : 'Guardar'}</button>
                    <button className="btn-ghost" onClick={() => { setEditando(null); setInputMonto('') }}>✕</button>
                  </div>
                ) : (
                  <>
                    <div className="progress-bar" style={{ marginTop: 8 }}>
                      <div className="progress-fill" style={{ width: `${Math.min(p.porcentaje, 100)}%`, background: color }} />
                    </div>
                    <div className="pres-meta">
                      <span>Gastado: {fmt(p.gastado)}</span>
                      <span>Presupuesto: {fmt(p.presupuestado)}</span>
                      <span style={{ color: p.disponible < 0 ? '#ef4444' : '#22c55e' }}>
                        {p.disponible >= 0 ? `Disponible: ${fmt(p.disponible)}` : `Exceso: ${fmt(-p.disponible)}`}
                      </span>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
