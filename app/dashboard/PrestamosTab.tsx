'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

// ── Tipos ────────────────────────────────────────────────────────────────────

interface Prestamo {
  id: number
  nombre: string
  total_cuotas: number
  total_cuotas_real: number
  cuotas_pagadas: number
  cuotas_pendientes: number
  proxima: { numero_cuota: number; mes_previsto: string; monto_ordinario: number | null; capital: number } | null
}

interface Cuota {
  id: number
  numero_cuota: number
  mes_previsto: string
  capital: number
  monto_ordinario: number | null
  monto_adelanto: number | null
  pagado: boolean
  tipo_pago: string | null
  monto_pagado: number | null
  fecha_pago: string | null
}

interface CuotaRow {
  numero_cuota: number
  mes: string
  capital: number
  monto_ordinario: number | null
  pagado: boolean
  tipo_pago: string | null
  monto_pagado: number | null
  fecha_pago: string | null
}

interface ParseError { row: number; mensaje: string }

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmt = (n: number) =>
  new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)

function parseNum(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = parseFloat(String(v).replace(/[$\s.]/g, '').replace(',', '.'))
  return isNaN(n) ? null : n
}

function parseBool(v: unknown): boolean {
  const s = String(v ?? '').toLowerCase().trim()
  return s === 'true' || s === '1' || s === 'si' || s === 'sí' || s === 'yes'
}

function parseFecha(v: unknown): string | null {
  if (!v) return null
  if (typeof v === 'number') {
    const d = XLSX.SSF.parse_date_code(v)
    if (!d) return null
    return `${d.y}-${String(d.m).padStart(2, '0')}-${String(d.d).padStart(2, '0')}`
  }
  const s = String(v).trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(s)) {
    const [d, m, y] = s.split('/')
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
  }
  return s || null
}

function parseMes(v: unknown): string | null {
  if (!v) return null
  if (typeof v === 'number') {
    const d = XLSX.SSF.parse_date_code(v)
    if (!d) return null
    return `${d.y}-${String(d.m).padStart(2, '0')}`
  }
  const s = String(v).trim()
  if (/^\d{4}-\d{2}$/.test(s)) return s
  if (/^\d{1,2}\/\d{4}$/.test(s)) {
    const [m, y] = s.split('/')
    return `${y}-${m.padStart(2, '0')}`
  }
  return s || null
}

const COL_MAP: Record<string, string> = {
  numero_cuota: 'numero_cuota', nro: 'numero_cuota', 'nro.': 'numero_cuota',
  cuota: 'numero_cuota', 'n°': 'numero_cuota', numero: 'numero_cuota',
  mes: 'mes', mes_previsto: 'mes', 'mes previsto': 'mes', fecha: 'mes',
  capital: 'capital',
  monto_ordinario: 'monto_ordinario', 'monto ordinario': 'monto_ordinario',
  monto: 'monto_ordinario', total: 'monto_ordinario',
  pagado: 'pagado', estado: 'pagado',
  tipo_pago: 'tipo_pago', 'tipo pago': 'tipo_pago', tipo: 'tipo_pago',
  monto_pagado: 'monto_pagado', 'monto pagado': 'monto_pagado',
  fecha_pago: 'fecha_pago', 'fecha pago': 'fecha_pago', 'fecha de pago': 'fecha_pago',
}

function parseSheet(ws: XLSX.WorkSheet): { rows: CuotaRow[]; errors: ParseError[] } {
  const data = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, defval: '' }) as unknown[][]
  if (data.length < 2) return { rows: [], errors: [{ row: 0, mensaje: 'Hoja vacía o sin datos' }] }
  const headers = (data[0] as unknown[]).map(String)
  const idx: Record<string, number> = {}
  headers.forEach((h, i) => { const k = COL_MAP[h.toLowerCase().trim()]; if (k && !(k in idx)) idx[k] = i })
  const errors: ParseError[] = []
  const rows: CuotaRow[] = []
  for (let i = 1; i < data.length; i++) {
    const r = data[i] as unknown[]
    if (r.every(c => c === '' || c == null)) continue
    const g = (key: string) => idx[key] !== undefined ? r[idx[key]] : undefined
    const nCuota = parseNum(g('numero_cuota'))
    if (!nCuota) { errors.push({ row: i + 1, mensaje: 'numero_cuota vacío' }); continue }
    const mes = parseMes(g('mes'))
    if (!mes) { errors.push({ row: i + 1, mensaje: `Cuota ${nCuota}: mes inválido` }); continue }
    const capital = parseNum(g('capital'))
    if (!capital) { errors.push({ row: i + 1, mensaje: `Cuota ${nCuota}: capital inválido` }); continue }
    rows.push({
      numero_cuota: nCuota, mes, capital,
      monto_ordinario: parseNum(g('monto_ordinario')),
      pagado: parseBool(g('pagado')),
      tipo_pago: g('tipo_pago') ? String(g('tipo_pago')).toLowerCase().trim() || null : null,
      monto_pagado: parseNum(g('monto_pagado')),
      fecha_pago: parseFecha(g('fecha_pago')),
    })
  }
  return { rows, errors }
}

// ── Estilos ──────────────────────────────────────────────────────────────────

const th: React.CSSProperties = { padding: '6px 10px', textAlign: 'left', fontWeight: 600, border: '1px solid var(--border, #e0e0e0)', fontSize: 12 }
const td: React.CSSProperties = { padding: '5px 10px', border: '1px solid var(--border, #e0e0e0)', fontSize: 12 }
const codeStyle: React.CSSProperties = { background: 'var(--border, #eee)', padding: '1px 5px', borderRadius: 3, fontFamily: 'monospace', fontSize: 11 }
const card: React.CSSProperties = { background: 'var(--card-bg, #f8f9fa)', border: '1px solid var(--border, #e0e0e0)', borderRadius: 10, padding: '16px 20px', marginBottom: 16 }

// ── Vista de cuotas ──────────────────────────────────────────────────────────

function CuotasView({ prestamo, onBack }: { prestamo: Prestamo; onBack: () => void }) {
  const [cuotas, setCuotas] = useState<Cuota[]>([])
  const [loading, setLoading] = useState(true)
  const [filtro, setFiltro] = useState<'todas' | 'pagadas' | 'pendientes'>('todas')

  useEffect(() => {
    fetchWithAuth(`/api/inversiones?resource=prestamo_cuotas&prestamo_id=${prestamo.id}`)
      .then(r => r.json())
      .then(d => { setCuotas(Array.isArray(d) ? d : []); setLoading(false) })
  }, [prestamo.id])

  const visible = cuotas.filter(c =>
    filtro === 'todas' ? true : filtro === 'pagadas' ? c.pagado : !c.pagado
  )

  const totalPagado = cuotas.filter(c => c.pagado).reduce((s, c) => s + (c.monto_pagado ?? 0), 0)
  const totalPendiente = cuotas.filter(c => !c.pagado).reduce((s, c) => s + (c.monto_ordinario ?? c.capital), 0)
  const pct = prestamo.total_cuotas_real > 0 ? Math.round(prestamo.cuotas_pagadas / prestamo.total_cuotas_real * 100) : 0

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <button onClick={onBack} style={{ background: 'none', border: '1px solid var(--border,#ccc)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 13 }}>
          ← Volver
        </button>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>🏦 {prestamo.nombre}</h2>
      </div>

      {/* Stats cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Cuotas pagadas', value: `${prestamo.cuotas_pagadas} / ${prestamo.total_cuotas_real}`, color: '#065f46' },
          { label: 'Avance', value: `${pct}%`, color: '#1d4ed8' },
          { label: 'Total abonado', value: `$${fmt(totalPagado)}`, color: '#065f46' },
          { label: 'Saldo pendiente', value: `$${fmt(totalPendiente)}`, color: '#991b1b' },
        ].map(s => (
          <div key={s.label} style={{ ...card, marginBottom: 0, textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Barra de progreso */}
      <div style={{ ...card, marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
          <span>{prestamo.cuotas_pagadas} pagadas</span>
          <span>{prestamo.cuotas_pendientes} pendientes</span>
        </div>
        <div style={{ background: '#e5e7eb', borderRadius: 6, height: 10, overflow: 'hidden' }}>
          <div style={{ background: '#2563eb', height: '100%', width: `${pct}%`, borderRadius: 6, transition: 'width 0.4s' }} />
        </div>
        {prestamo.proxima && (
          <div style={{ marginTop: 10, fontSize: 13 }}>
            ⏳ <strong>Próxima:</strong> cuota #{prestamo.proxima.numero_cuota} — {prestamo.proxima.mes_previsto}
            {prestamo.proxima.monto_ordinario ? ` — $${fmt(prestamo.proxima.monto_ordinario)}` : ''}
          </div>
        )}
        {!prestamo.proxima && <div style={{ marginTop: 10, fontSize: 13, color: '#065f46', fontWeight: 600 }}>🎉 ¡Préstamo cancelado!</div>}
      </div>

      {/* Filtros */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {(['todas', 'pagadas', 'pendientes'] as const).map(f => (
          <button key={f} onClick={() => setFiltro(f)}
            style={{ padding: '4px 14px', borderRadius: 6, border: '1px solid var(--border,#ccc)', cursor: 'pointer', fontWeight: filtro === f ? 700 : 400, background: filtro === f ? '#2563eb' : 'transparent', color: filtro === f ? '#fff' : 'inherit', fontSize: 13 }}>
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: '#888', alignSelf: 'center' }}>{visible.length} cuotas</span>
      </div>

      {/* Tabla */}
      {loading ? (
        <p style={{ color: '#888', textAlign: 'center', padding: 24 }}>Cargando cuotas…</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'var(--border, #e8e8e8)' }}>
                {['#', 'Mes', 'Estado', 'Capital', 'Ordinario', 'Adelanto (×1.25)', 'Tipo pago', 'Monto pagado', 'Fecha pago'].map(h => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map(c => (
                <tr key={c.id} style={{ background: c.pagado ? 'var(--success-bg, #f0fff4)' : undefined }}>
                  <td style={td}>{c.numero_cuota}</td>
                  <td style={td}>{c.mes_previsto}</td>
                  <td style={{ ...td, textAlign: 'center' }}>
                    {c.pagado
                      ? <span style={{ color: '#065f46', fontWeight: 600 }}>✅ Pagada</span>
                      : <span style={{ color: '#92400e' }}>⏳ Pendiente</span>}
                  </td>
                  <td style={{ ...td, textAlign: 'right' }}>${fmt(c.capital)}</td>
                  <td style={{ ...td, textAlign: 'right' }}>{c.monto_ordinario ? `$${fmt(c.monto_ordinario)}` : '—'}</td>
                  <td style={{ ...td, textAlign: 'right', color: '#2563eb' }}>${fmt(c.capital * 1.25)}</td>
                  <td style={td}>{c.tipo_pago ?? '—'}</td>
                  <td style={{ ...td, textAlign: 'right' }}>{c.monto_pagado ? `$${fmt(c.monto_pagado)}` : '—'}</td>
                  <td style={td}>{c.fecha_pago ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Componente principal ─────────────────────────────────────────────────────

export default function PrestamosTab() {
  const [prestamos, setPrestamos] = useState<Prestamo[]>([])
  const [loadingPrest, setLoadingPrest] = useState(true)
  const [selected, setSelected] = useState<Prestamo | null>(null)
  const [showImport, setShowImport] = useState(false)

  // Import state
  const inputRef = useRef<HTMLInputElement>(null)
  const [nombre, setNombre] = useState('')
  const [rows, setRows] = useState<CuotaRow[]>([])
  const [errors, setErrors] = useState<ParseError[]>([])
  const [fileName, setFileName] = useState('')
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const loadPrestamos = useCallback(async () => {
    setLoadingPrest(true)
    const r = await fetchWithAuth('/api/inversiones?resource=prestamos')
    const data = await r.json()
    setPrestamos(Array.isArray(data) ? data : [])
    setLoadingPrest(false)
  }, [])

  useEffect(() => { loadPrestamos() }, [loadPrestamos])

  function handleFile(file: File) {
    setResult(null)
    setFileName(file.name)
    const reader = new FileReader()
    reader.onload = (e) => {
      const data = e.target?.result
      if (!data) return
      const wb = XLSX.read(data, { type: 'array' })
      const ws = wb.Sheets[wb.SheetNames[0]]
      const { rows: parsed, errors: errs } = parseSheet(ws)
      setRows(parsed)
      setErrors(errs)
    }
    reader.readAsArrayBuffer(file)
  }

  async function handleImport() {
    if (!nombre.trim()) { alert('Escribí el nombre del préstamo.'); return }
    if (!rows.length) { alert('No hay filas válidas.'); return }
    setImporting(true)
    setResult(null)
    try {
      const res = await fetchWithAuth('/api/inversiones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource: 'importar_prestamo', nombre: nombre.trim(), cuotas: rows }),
      })
      const json = await res.json()
      if (res.ok && json.ok) {
        setResult({ ok: true, msg: `✅ ${json.cuotas} cuotas importadas correctamente.` })
        setRows([]); setErrors([]); setFileName(''); setNombre('')
        setShowImport(false)
        await loadPrestamos()
      } else {
        setResult({ ok: false, msg: `❌ ${json.error || 'Error desconocido'}` })
      }
    } catch {
      setResult({ ok: false, msg: '❌ Error de red.' })
    } finally {
      setImporting(false)
    }
  }

  // ── Vista: cronograma de cuotas de un préstamo ───────────────────────────
  if (selected) {
    return <CuotasView prestamo={selected} onBack={() => setSelected(null)} />
  }

  // ── Vista: lista de préstamos + formulario de importación ────────────────
  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '24px 16px' }}>

      {/* Título */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>🏦 Préstamos</h2>
        <button onClick={() => { setShowImport(v => !v); setResult(null) }}
          style={{ padding: '6px 16px', borderRadius: 8, border: '1px solid var(--border,#ccc)', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
          {showImport ? 'Cancelar' : '+ Importar cronograma'}
        </button>
      </div>

      {/* Lista de préstamos */}
      {loadingPrest ? (
        <p style={{ color: '#888', textAlign: 'center', padding: 32 }}>Cargando…</p>
      ) : prestamos.length === 0 && !showImport ? (
        <div style={{ ...card, textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🏦</div>
          <p style={{ fontWeight: 600, marginBottom: 8 }}>No tenés préstamos importados</p>
          <p style={{ color: '#888', fontSize: 13, marginBottom: 16 }}>Importá el cronograma de cuotas desde tu banco o planilla Excel.</p>
          <button onClick={() => setShowImport(true)}
            style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>
            + Importar cronograma
          </button>
        </div>
      ) : (
        <div style={{ marginBottom: showImport ? 24 : 0 }}>
          {prestamos.map(p => {
            const pct = p.total_cuotas_real > 0 ? Math.round(p.cuotas_pagadas / p.total_cuotas_real * 100) : 0
            const cancelado = p.cuotas_pendientes === 0
            return (
              <div key={p.id} style={{ ...card, cursor: 'pointer' }} onClick={() => setSelected(p)}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: 16 }}>{p.nombre}</span>
                    {cancelado && <span style={{ marginLeft: 8, fontSize: 12, color: '#065f46', background: '#d1fae5', padding: '1px 8px', borderRadius: 10 }}>✅ Cancelado</span>}
                  </div>
                  <span style={{ fontSize: 12, color: '#2563eb', fontWeight: 600 }}>{pct}% →</span>
                </div>
                <div style={{ background: '#e5e7eb', borderRadius: 6, height: 8, marginBottom: 10 }}>
                  <div style={{ background: cancelado ? '#10b981' : '#2563eb', height: '100%', width: `${pct}%`, borderRadius: 6 }} />
                </div>
                <div style={{ display: 'flex', gap: 20, fontSize: 13 }}>
                  <span>✅ {p.cuotas_pagadas} pagadas</span>
                  <span>⏳ {p.cuotas_pendientes} pendientes</span>
                  <span style={{ color: '#888' }}>Total: {p.total_cuotas_real} cuotas</span>
                </div>
                {p.proxima && (
                  <div style={{ marginTop: 8, fontSize: 12, color: '#92400e', background: '#fef3c7', padding: '4px 10px', borderRadius: 6, display: 'inline-block' }}>
                    Próxima: cuota #{p.proxima.numero_cuota} · {p.proxima.mes_previsto}
                    {p.proxima.monto_ordinario ? ` · $${fmt(p.proxima.monto_ordinario)}` : ''}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Formulario de importación */}
      {showImport && (
        <div style={{ borderTop: prestamos.length > 0 ? '1px solid var(--border,#e0e0e0)' : 'none', paddingTop: prestamos.length > 0 ? 24 : 0 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Importar cronograma</h3>

          {/* Formato */}
          <details style={{ marginBottom: 20, ...card }}>
            <summary style={{ fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
              📋 Formato esperado del archivo
            </summary>
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <p style={{ marginBottom: 8 }}>
                <strong>Extensiones admitidas:</strong>{' '}
                {['.xlsx', '.xls', '.csv'].map(e => <code key={e} style={{ ...codeStyle, marginRight: 4 }}>{e}</code>)}
              </p>
              <p style={{ marginBottom: 10 }}>Primera fila = encabezados. Columnas detectadas automáticamente por nombre:</p>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--border,#e8e8e8)' }}>
                    {['Columna', 'Tipo', '¿Requerida?', 'Descripción'].map(h => <th key={h} style={th}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['numero_cuota', 'Número', '✅', 'Número de cuota (1, 2, 3…)'],
                    ['mes', 'Texto / Fecha', '✅', 'Mes previsto: YYYY-MM, MM/YYYY o fecha de Excel'],
                    ['capital', 'Número', '✅', 'Capital de la cuota (sin interés ni IVA)'],
                    ['monto_ordinario', 'Número', '—', 'Monto total en fecha (capital + interés + IVA)'],
                    ['pagado', 'Booleano', '—', 'true/false · SI/NO · 1/0'],
                    ['tipo_pago', 'Texto', '—', '"ordinaria" o "adelanto"'],
                    ['monto_pagado', 'Número', '—', 'Lo que efectivamente se abonó'],
                    ['fecha_pago', 'Fecha', '—', 'DD/MM/YYYY o YYYY-MM-DD'],
                  ].map(([col, tipo, req, desc]) => (
                    <tr key={col}>
                      <td style={td}><code style={codeStyle}>{col}</code></td>
                      <td style={td}>{tipo}</td>
                      <td style={{ ...td, textAlign: 'center' }}>{req}</td>
                      <td style={td}>{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p style={{ marginTop: 10, color: '#888', fontSize: 12 }}>
                💡 El adelanto se calcula automáticamente como <strong>capital × 1,25</strong>. Las cuotas con <code style={codeStyle}>pagado = true</code> quedan como historial.
              </p>
            </div>
          </details>

          {/* Nombre */}
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Nombre del préstamo</label>
            <input type="text" value={nombre} onChange={e => setNombre(e.target.value)}
              placeholder="Ej: Préstamo auto"
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border,#ccc)', fontSize: 14, boxSizing: 'border-box' }} />
          </div>

          {/* Drop zone */}
          <div onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
            onDragOver={e => e.preventDefault()}
            onClick={() => inputRef.current?.click()}
            style={{ border: '2px dashed var(--border,#ccc)', borderRadius: 10, padding: '32px 24px', textAlign: 'center', cursor: 'pointer', marginBottom: 16 }}>
            <div style={{ fontSize: 28, marginBottom: 6 }}>📂</div>
            <p style={{ fontWeight: 600, marginBottom: 4 }}>{fileName || 'Arrastrá el archivo acá o hacé clic'}</p>
            <p style={{ fontSize: 12, color: '#888' }}>Admite .xlsx · .xls · .csv</p>
            <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }}
              onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
          </div>

          {/* Errores */}
          {errors.length > 0 && (
            <div style={{ background: '#fff3cd', border: '1px solid #ffc107', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 12 }}>
              <strong>⚠️ {errors.length} fila{errors.length > 1 ? 's' : ''} omitidas:</strong>
              <ul style={{ marginTop: 4, paddingLeft: 18 }}>
                {errors.slice(0, 6).map((e, i) => <li key={i}>Fila {e.row}: {e.mensaje}</li>)}
                {errors.length > 6 && <li>…y {errors.length - 6} más</li>}
              </ul>
            </div>
          )}

          {/* Preview */}
          {rows.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                Vista previa — {rows.length} cuotas · {rows.filter(r => r.pagado).length} pagadas · {rows.filter(r => !r.pagado).length} pendientes
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: 'var(--border,#e8e8e8)' }}>
                      {['#', 'Mes', 'Capital', 'Ordinario', 'Adelanto ×1.25', 'Pagado'].map(h => <th key={h} style={th}>{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 8).map((r, i) => (
                      <tr key={i} style={{ background: r.pagado ? 'var(--success-bg,#f0fff4)' : undefined }}>
                        <td style={td}>{r.numero_cuota}</td>
                        <td style={td}>{r.mes}</td>
                        <td style={{ ...td, textAlign: 'right' }}>${fmt(r.capital)}</td>
                        <td style={{ ...td, textAlign: 'right' }}>{r.monto_ordinario ? `$${fmt(r.monto_ordinario)}` : '—'}</td>
                        <td style={{ ...td, textAlign: 'right', color: '#2563eb' }}>${fmt(r.capital * 1.25)}</td>
                        <td style={{ ...td, textAlign: 'center' }}>{r.pagado ? '✅' : '⏳'}</td>
                      </tr>
                    ))}
                    {rows.length > 8 && (
                      <tr><td colSpan={6} style={{ ...td, textAlign: 'center', color: '#888' }}>…y {rows.length - 8} filas más</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Resultado */}
          {result && (
            <div style={{ padding: '10px 14px', borderRadius: 8, marginBottom: 14, fontSize: 13, background: result.ok ? '#d1fae5' : '#fee2e2', color: result.ok ? '#065f46' : '#991b1b', border: `1px solid ${result.ok ? '#6ee7b7' : '#fca5a5'}` }}>
              {result.msg}
            </div>
          )}

          <button onClick={handleImport} disabled={importing || !rows.length || !nombre.trim()}
            style={{ padding: '10px 28px', borderRadius: 8, border: 'none', background: rows.length && nombre.trim() ? '#2563eb' : '#94a3b8', color: '#fff', fontWeight: 700, fontSize: 14, cursor: rows.length && nombre.trim() ? 'pointer' : 'not-allowed', opacity: importing ? 0.7 : 1 }}>
            {importing ? 'Importando…' : `Importar ${rows.length ? rows.length + ' cuotas' : ''}`}
          </button>
        </div>
      )}
    </div>
  )
}
