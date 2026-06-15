'use client'

import { useEffect, useState, useCallback } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

interface Objetivo {
  id: number
  nombre: string
  monto_objetivo: number
  monto_actual: number
  falta: number
  porcentaje: number
  fecha_objetivo: string
  dias_faltan: number
  meses_faltan: number
  recomendado_mensual: number
}

export default function ObjetivosTab() {
  const [objetivos, setObjetivos] = useState<Objetivo[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ nombre: '', monto: '', fecha: '' })
  const [aporteId, setAporteId] = useState<number | null>(null)
  const [aporteVal, setAporteVal] = useState('')
  const [saving, setSaving] = useState(false)

  const fetch_ = useCallback(async () => {
    setLoading(true)
    const r = await fetchWithAuth('/api/objetivos')
    const data = await r.json()
    setObjetivos(Array.isArray(data) ? data : [])
    setLoading(false)
  }, [])

  useEffect(() => { fetch_() }, [fetch_])

  async function crearObjetivo() {
    if (!form.nombre || !form.monto || !form.fecha) return
    setSaving(true)
    await fetchWithAuth('/api/objetivos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre: form.nombre,
        monto_objetivo: parseFloat(form.monto),
        fecha_objetivo: form.fecha,
      }),
    })
    setForm({ nombre: '', monto: '', fecha: '' })
    setShowForm(false)
    setSaving(false)
    await fetch_()
  }

  async function aportar(id: number) {
    if (!aporteVal) return
    setSaving(true)
    await fetchWithAuth(`/api/objetivos?id=${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aporte: parseFloat(aporteVal) }),
    })
    setAporteId(null)
    setAporteVal('')
    setSaving(false)
    await fetch_()
  }

  async function eliminar(id: number) {
    if (!confirm('¿Eliminar este objetivo?')) return
    await fetchWithAuth(`/api/objetivos?id=${id}`, { method: 'DELETE' })
    await fetch_()
  }

  return (
    <div className="tab-content">
      <div className="section-header">
        <h2 className="section-title">Objetivos de ahorro</h2>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>+ Nuevo</button>
      </div>

      {showForm && (
        <div className="form-card">
          <div className="form-grid">
            <div>
              <p className="form-label">Nombre del objetivo</p>
              <input className="form-input" placeholder="Ej: Vacaciones Europa"
                value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} />
            </div>
            <div>
              <p className="form-label">Monto objetivo ($)</p>
              <input className="form-input" type="number" placeholder="Ej: 500000"
                value={form.monto} onChange={e => setForm(f => ({ ...f, monto: e.target.value }))} />
            </div>
            <div>
              <p className="form-label">Fecha límite</p>
              <input className="form-input" type="date"
                value={form.fecha} onChange={e => setForm(f => ({ ...f, fecha: e.target.value }))} />
            </div>
          </div>
          <div className="form-row" style={{ marginTop: 12 }}>
            <button className="btn-primary" onClick={crearObjetivo} disabled={saving}>
              {saving ? '...' : 'Crear objetivo'}
            </button>
            <button className="btn-ghost" onClick={() => setShowForm(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="loading">Cargando...</p>
      ) : objetivos.length === 0 ? (
        <div className="empty">
          Sin objetivos de ahorro.<br />
          <span>Creá uno con el botón "Nuevo".</span>
        </div>
      ) : (
        <div className="objetivos-list">
          {objetivos.map(obj => (
            <div key={obj.id} className="objetivo-card">
              <div className="objetivo-header">
                <span className="objetivo-nombre">🎯 {obj.nombre}</span>
                <button className="btn-icon" onClick={() => eliminar(obj.id)}>🗑️</button>
              </div>

              <div className="objetivo-progress">
                <div className="progress-bar">
                  <div className="progress-fill"
                    style={{ width: `${obj.porcentaje}%`, background: obj.porcentaje >= 100 ? '#22c55e' : '#6366f1' }} />
                </div>
                <span className="objetivo-pct">{obj.porcentaje.toFixed(0)}%</span>
              </div>

              <div className="objetivo-stats">
                <div className="obj-stat">
                  <span className="obj-stat-label">Acumulado</span>
                  <span className="obj-stat-value ingreso">{fmt(obj.monto_actual)}</span>
                </div>
                <div className="obj-stat">
                  <span className="obj-stat-label">Objetivo</span>
                  <span className="obj-stat-value">{fmt(obj.monto_objetivo)}</span>
                </div>
                <div className="obj-stat">
                  <span className="obj-stat-label">Falta</span>
                  <span className="obj-stat-value gasto">{fmt(obj.falta)}</span>
                </div>
                <div className="obj-stat">
                  <span className="obj-stat-label">Mensual rec.</span>
                  <span className="obj-stat-value">{fmt(obj.recomendado_mensual)}</span>
                </div>
              </div>

              <div className="objetivo-footer">
                <span className="muted">
                  Vence {new Date(obj.fecha_objetivo + 'T12:00:00').toLocaleDateString('es-AR', { day: 'numeric', month: 'long', year: 'numeric' })}
                  {obj.dias_faltan > 0 ? ` (${obj.meses_faltan} meses)` : ' — vencido'}
                </span>
                {aporteId === obj.id ? (
                  <div className="form-row">
                    <input className="form-input" type="number" placeholder="Monto a aportar"
                      value={aporteVal} onChange={e => setAporteVal(e.target.value)} style={{ width: 140 }} />
                    <button className="btn-primary" onClick={() => aportar(obj.id)} disabled={saving}>
                      {saving ? '...' : 'Aportar'}
                    </button>
                    <button className="btn-ghost" onClick={() => { setAporteId(null); setAporteVal('') }}>✕</button>
                  </div>
                ) : (
                  obj.porcentaje < 100 && (
                    <button className="btn-primary" onClick={() => setAporteId(obj.id)}>+ Aportar</button>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
