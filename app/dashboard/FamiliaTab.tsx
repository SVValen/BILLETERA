'use client'

import { useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert, BilleteraButton } from '@/app/components/design'

interface Item {
  asignacion_id: number
  movimiento_id: number
  descripcion: string
  cuota_nro: number | null
  cuota_total: number | null
  tarjeta: string
  monto: number
  parcial: boolean
  nota: string | null
}

interface Familiar {
  id: number
  nombre: string
  telefono: string | null
  items: Item[]
  total: number
}

interface SinAsignar {
  id: number
  descripcion: string
  monto: number
  cuota_plan_id: number | null
  tarjeta: string
  sugerido: boolean
}

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

function nombreMes(mes: string) {
  const [, m] = mes.split('-')
  return MESES[Number(m) - 1] ?? mes
}

function mensaje(f: Familiar, mes: string) {
  const lineas = f.items.map(i => {
    const cuota = i.cuota_nro && i.cuota_total && i.cuota_total > 1 ? ` (cuota ${i.cuota_nro}/${i.cuota_total})` : ''
    return `• ${i.descripcion}${cuota}: ${fmt(i.monto)}`
  })
  return [
    `Hola ${f.nombre}! 👋`,
    `Este es tu detalle mensual de las cuotas de ${nombreMes(mes)}:`,
    '',
    ...lineas,
    '',
    `*Total: ${fmt(f.total)}*`,
    '',
    'Gracias! 💛',
  ].join('\n')
}

function linkWhatsApp(f: Familiar, mes: string) {
  const texto = encodeURIComponent(mensaje(f, mes))
  return f.telefono ? `https://wa.me/${f.telefono}?text=${texto}` : `https://wa.me/?text=${texto}`
}

export default function FamiliaTab({ mes }: { mes: string }) {
  const [familiares, setFamiliares] = useState<Familiar[]>([])
  const [sinAsignar, setSinAsignar] = useState<SinAsignar[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [copiado, setCopiado] = useState<number | null>(null)
  const [asignar, setAsignar] = useState<Record<number, { familiar_id: string; monto: string }>>({})
  const [verTodas, setVerTodas] = useState(false)
  const [telefonos, setTelefonos] = useState<Record<number, string>>({})
  const [nuevo, setNuevo] = useState({ nombre: '', telefono: '' })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchWithAuth(`/api/familia?mes=${mes}`)
      .then(r => r.json())
      .then(d => {
        if (cancelled) return
        if (d?.error) { setError(d.error); return }
        setFamiliares(d.familiares ?? [])
        setSinAsignar(d.sin_asignar ?? [])
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'No se pudo cargar') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [mes, reload])

  const post = async (key: string, body: object) => {
    setOcupado(key)
    try {
      const r = await fetchWithAuth('/api/familia', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (d?.error) setError(d.error)
      setReload(k => k + 1)
    } finally {
      setOcupado(null)
    }
  }

  const copiar = async (f: Familiar) => {
    await navigator.clipboard.writeText(mensaje(f, mes))
    setCopiado(f.id)
    setTimeout(() => setCopiado(null), 2000)
  }

  if (loading) return <p className="loading">Cargando...</p>

  const visibles = verTodas ? sinAsignar : sinAsignar.filter(s => s.sugerido)

  return (
    <>
      {error && <BilleteraAlert variant="danger" title="Algo no salió">{error}</BilleteraAlert>}

      {familiares.length === 0 && (
        <p className="empty">Todavía no cargaste familiares. Agregá uno abajo para empezar a asignarle compras.</p>
      )}

      {familiares.map(f => (
        <div key={f.id} className="widget-box">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <h3 className="widget-title" style={{ margin: 0 }}>{f.nombre}</h3>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'var(--font-display)' }}>{fmt(f.total)}</div>
          </div>

          {f.items.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>No tiene cuotas en {nombreMes(mes)}.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
              {f.items.map(i => (
                <div key={`${i.asignacion_id}-${i.movimiento_id}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, fontSize: 14, flexWrap: 'wrap' }}>
                  <span>
                    {i.descripcion}
                    {i.cuota_nro && i.cuota_total && i.cuota_total > 1 && <span className="muted"> {i.cuota_nro}/{i.cuota_total}</span>}
                    <span className="muted" style={{ fontSize: 12 }}> · {i.tarjeta}{i.parcial ? ', parte' : ''}</span>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <strong>{fmt(i.monto)}</strong>
                    <BilleteraButton size="sm" variant="ghost" loading={ocupado === `des-${i.asignacion_id}`}
                      onClick={() => post(`des-${i.asignacion_id}`, { resource: 'desasignar', id: i.asignacion_id })}>
                      Quitar
                    </BilleteraButton>
                  </span>
                </div>
              ))}
            </div>
          )}

          {f.items.length > 0 && (
            <>
              <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 13, background: 'var(--bg3)', borderRadius: 10, padding: '12px 14px', margin: '0 0 12px' }}>
                {mensaje(f, mes)}
              </pre>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <BilleteraButton size="sm" variant="outline" onClick={() => copiar(f)}>
                  {copiado === f.id ? 'Copiado ✓' : 'Copiar mensaje'}
                </BilleteraButton>
                <a href={linkWhatsApp(f, mes)} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                  <BilleteraButton size="sm" variant="primary">
                    {f.telefono ? `Abrir WhatsApp con ${f.nombre}` : 'Abrir WhatsApp (elegís el contacto)'}
                  </BilleteraButton>
                </a>
              </div>
            </>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            <input className="month-input" style={{ width: 190 }} inputMode="tel"
              placeholder="WhatsApp (ej. 5493624123456)"
              value={telefonos[f.id] ?? f.telefono ?? ''}
              onChange={e => setTelefonos(prev => ({ ...prev, [f.id]: e.target.value }))}
              aria-label={`Teléfono de ${f.nombre}`} />
            {(telefonos[f.id] ?? f.telefono ?? '') !== (f.telefono ?? '') && (
              <BilleteraButton size="sm" variant="ghost" loading={ocupado === `tel-${f.id}`}
                onClick={() => post(`tel-${f.id}`, { resource: 'familiar', id: f.id, nombre: f.nombre, telefono: telefonos[f.id] })}>
                Guardar teléfono
              </BilleteraButton>
            )}
          </div>
        </div>
      ))}

      {/* Compras del mes sin asignar */}
      <div className="widget-box">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <h3 className="widget-title" style={{ margin: 0 }}>Compras sin asignar en {nombreMes(mes)}</h3>
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={verTodas} onChange={e => setVerTodas(e.target.checked)} />
            Ver todas las compras con tarjeta
          </label>
        </div>
        {visibles.length === 0 ? (
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            {verTodas ? 'No quedan compras sin asignar.' : 'No hay compras de "Compras familia" sin asignar. Tildá "Ver todas" para elegir otra.'}
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {visibles.map(s => {
              const sel = asignar[s.id] ?? { familiar_id: '', monto: '' }
              return (
                <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 14 }}>
                  <span>{s.descripcion} <span className="muted" style={{ fontSize: 12 }}>· {s.tarjeta}</span></span>
                  <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <strong>{fmt(s.monto)}</strong>
                    <select className="month-input" value={sel.familiar_id}
                      onChange={e => setAsignar(prev => ({ ...prev, [s.id]: { ...sel, familiar_id: e.target.value } }))}
                      aria-label={`Familiar para ${s.descripcion}`}>
                      <option value="">¿De quién?</option>
                      {familiares.map(f => <option key={f.id} value={f.id}>{f.nombre}</option>)}
                    </select>
                    <input className="month-input" style={{ width: 120 }} inputMode="decimal" placeholder="Por mes (opcional)"
                      value={sel.monto} onChange={e => setAsignar(prev => ({ ...prev, [s.id]: { ...sel, monto: e.target.value } }))}
                      aria-label="Lo que te pasa por mes, si no es la cuota entera" />
                    <BilleteraButton size="sm" variant="outline" disabled={!sel.familiar_id} loading={ocupado === `as-${s.id}`}
                      onClick={() => post(`as-${s.id}`, {
                        resource: 'asignar', familiar_id: Number(sel.familiar_id), movimiento_id: s.id, por_plan: true,
                        monto_mensual: sel.monto ? Number(sel.monto.replace(/\./g, '').replace(',', '.')) : null,
                      })}>
                      Asignar
                    </BilleteraButton>
                  </span>
                </div>
              )
            })}
          </div>
        )}
        <p className="muted" style={{ fontSize: 12, margin: '12px 0 0' }}>
          Si es una compra en cuotas, se asigna el plan completo: le aparece todos los meses hasta la última cuota.
        </p>
      </div>

      {/* Alta de familiar */}
      <div className="widget-box">
        <h3 className="widget-title">Agregar familiar</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input className="month-input" placeholder="Nombre" value={nuevo.nombre}
            onChange={e => setNuevo({ ...nuevo, nombre: e.target.value })} aria-label="Nombre del familiar" />
          <input className="month-input" placeholder="WhatsApp (opcional)" inputMode="tel" value={nuevo.telefono}
            onChange={e => setNuevo({ ...nuevo, telefono: e.target.value })} aria-label="Teléfono del familiar" />
          <BilleteraButton size="sm" variant="primary" disabled={!nuevo.nombre.trim()} loading={ocupado === 'nuevo'}
            onClick={async () => { await post('nuevo', { resource: 'familiar', ...nuevo }); setNuevo({ nombre: '', telefono: '' }) }}>
            Agregar
          </BilleteraButton>
        </div>
      </div>
    </>
  )
}
