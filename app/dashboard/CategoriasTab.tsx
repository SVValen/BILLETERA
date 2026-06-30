'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

interface Categoria {
  id: number
  nombre: string
  emoji: string
}

export default function CategoriasTab() {
  const [categorias, setCategorias] = useState<Categoria[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ nombre: '', emoji: '📌' })
  const [editId, setEditId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState({ nombre: '', emoji: '' })
  const [saving, setSaving] = useState(false)

  const fetch_ = useCallback(async () => {
    setLoading(true)
    const r = await fetchWithAuth('/api/presupuestos?resource=categorias')
    const data = await r.json()
    setCategorias(Array.isArray(data) ? data : [])
    setLoading(false)
  }, [])

  useEffect(() => { fetch_() }, [fetch_])

  async function crearCategoria() {
    if (!form.nombre.trim()) return
    setSaving(true)
    await fetchWithAuth('/api/presupuestos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource: 'categorias', nombre: form.nombre.trim(), emoji: form.emoji.trim() || '📌' }),
    })
    setForm({ nombre: '', emoji: '📌' })
    setShowForm(false)
    setSaving(false)
    await fetch_()
  }

  function startEdit(c: Categoria) {
    setEditId(c.id)
    setEditForm({ nombre: c.nombre, emoji: c.emoji })
  }

  async function guardarEdit(id: number) {
    if (!editForm.nombre.trim()) return
    setSaving(true)
    await fetchWithAuth(`/api/presupuestos?id=${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resource: 'categorias', nombre: editForm.nombre.trim(), emoji: editForm.emoji.trim() || '📌' }),
    })
    setEditId(null)
    setSaving(false)
    await fetch_()
  }

  return (
    <div className="tab-content">
      <div className="section-header">
        <h2 className="section-title">Categorías</h2>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>+ Nueva</button>
      </div>

      {showForm && (
        <div className="form-card">
          <div className="form-grid">
            <div>
              <p className="form-label">Emoji</p>
              <input className="form-input" placeholder="📌"
                value={form.emoji} onChange={e => setForm(f => ({ ...f, emoji: e.target.value }))} style={{ width: 80 }} />
            </div>
            <div>
              <p className="form-label">Nombre</p>
              <input className="form-input" placeholder="Ej: Regalos"
                value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} />
            </div>
          </div>
          <div className="form-row" style={{ marginTop: 12 }}>
            <button className="btn-primary" onClick={crearCategoria} disabled={saving}>
              {saving ? '...' : 'Crear categoría'}
            </button>
            <button className="btn-ghost" onClick={() => setShowForm(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="loading">Cargando...</p>
      ) : categorias.length === 0 ? (
        <p className="empty">Sin categorías.</p>
      ) : (
        <div className="table-box">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Emoji</th>
                  <th>Nombre</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {categorias.map(c => (
                  <tr key={c.id}>
                    {editId === c.id ? (
                      <>
                        <td>
                          <input className="form-input" value={editForm.emoji}
                            onChange={e => setEditForm(f => ({ ...f, emoji: e.target.value }))} style={{ width: 60 }} />
                        </td>
                        <td>
                          <input className="form-input" value={editForm.nombre}
                            onChange={e => setEditForm(f => ({ ...f, nombre: e.target.value }))} />
                        </td>
                        <td className="right">
                          <button className="btn-primary" onClick={() => guardarEdit(c.id)} disabled={saving}>
                            {saving ? '...' : 'Guardar'}
                          </button>
                          <button className="btn-ghost" onClick={() => setEditId(null)}>✕</button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td>{c.emoji}</td>
                        <td>{c.nombre}</td>
                        <td className="right">
                          <button className="btn-icon" onClick={() => startEdit(c)} title="Editar">✏️</button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
