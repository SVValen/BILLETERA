'use client'

import { useRef, useState } from 'react'
import * as XLSX from 'xlsx'
import { fetchWithAuth } from '@/lib/fetch-with-auth'

// ── Tipos ────────────────────────────────────────────────────────────────────

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

interface ParseError {
  row: number
  mensaje: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 }).format(n)
}

function parseNum(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const s = String(v).replace(/[$\s.]/g, '').replace(',', '.')
  const n = parseFloat(s)
  return isNaN(n) ? null : n
}

function parseBool(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  const s = String(v ?? '').toLowerCase().trim()
  return s === 'true' || s === '1' || s === 'si' || s === 'sí' || s === 'yes'
}

function parseFecha(v: unknown): string | null {
  if (!v) return null
  if (typeof v === 'number') {
    // Excel serial date
    const d = XLSX.SSF.parse_date_code(v)
    if (!d) return null
    const mm = String(d.m).padStart(2, '0')
    const dd = String(d.d).padStart(2, '0')
    return `${d.y}-${mm}-${dd}`
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

const COLUMN_MAP: Record<string, string> = {
  // numero_cuota
  'numero_cuota': 'numero_cuota', 'nro': 'numero_cuota', 'nro.': 'numero_cuota',
  'cuota': 'numero_cuota', 'n°': 'numero_cuota', 'numero': 'numero_cuota',
  // mes
  'mes': 'mes', 'mes_previsto': 'mes', 'mes previsto': 'mes', 'fecha': 'mes',
  // capital
  'capital': 'capital',
  // monto_ordinario
  'monto_ordinario': 'monto_ordinario', 'monto ordinario': 'monto_ordinario',
  'monto': 'monto_ordinario', 'total': 'monto_ordinario', 'cuota monto': 'monto_ordinario',
  // pagado
  'pagado': 'pagado', 'estado': 'pagado',
  // tipo_pago
  'tipo_pago': 'tipo_pago', 'tipo pago': 'tipo_pago', 'tipo': 'tipo_pago',
  // monto_pagado
  'monto_pagado': 'monto_pagado', 'monto pagado': 'monto_pagado',
  // fecha_pago
  'fecha_pago': 'fecha_pago', 'fecha pago': 'fecha_pago', 'fecha de pago': 'fecha_pago',
}

function mapHeaders(raw: string[]): Record<string, number> {
  const map: Record<string, number> = {}
  raw.forEach((h, i) => {
    const key = COLUMN_MAP[h.toLowerCase().trim()]
    if (key && !(key in map)) map[key] = i
  })
  return map
}

function parseSheet(ws: XLSX.WorkSheet): { rows: CuotaRow[]; errors: ParseError[] } {
  const data = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, defval: '' }) as unknown[][]
  if (data.length < 2) return { rows: [], errors: [{ row: 0, mensaje: 'Hoja vacía o sin datos' }] }

  const headers = (data[0] as unknown[]).map(String)
  const colIdx = mapHeaders(headers)
  const errors: ParseError[] = []
  const rows: CuotaRow[] = []

  for (let i = 1; i < data.length; i++) {
    const r = data[i] as unknown[]
    // Skip completely empty rows
    if (r.every(c => c === '' || c === null || c === undefined)) continue

    const rowNum = i + 1
    const getCol = (key: string) => colIdx[key] !== undefined ? r[colIdx[key]] : undefined

    const nCuota = parseNum(getCol('numero_cuota'))
    if (!nCuota) { errors.push({ row: rowNum, mensaje: 'numero_cuota vacío o inválido' }); continue }

    const mes = parseMes(getCol('mes'))
    if (!mes) { errors.push({ row: rowNum, mensaje: `Cuota ${nCuota}: mes inválido` }); continue }

    const capital = parseNum(getCol('capital'))
    if (!capital) { errors.push({ row: rowNum, mensaje: `Cuota ${nCuota}: capital inválido` }); continue }

    rows.push({
      numero_cuota: nCuota,
      mes,
      capital,
      monto_ordinario: parseNum(getCol('monto_ordinario')),
      pagado: parseBool(getCol('pagado')),
      tipo_pago: getCol('tipo_pago') ? String(getCol('tipo_pago')).toLowerCase().trim() || null : null,
      monto_pagado: parseNum(getCol('monto_pagado')),
      fecha_pago: parseFecha(getCol('fecha_pago')),
    })
  }

  return { rows, errors }
}

// ── Componente ───────────────────────────────────────────────────────────────

export default function PrestamosTab() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [nombre, setNombre] = useState('')
  const [rows, setRows] = useState<CuotaRow[]>([])
  const [errors, setErrors] = useState<ParseError[]>([])
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)

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

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  async function handleImport() {
    if (!nombre.trim()) { alert('Escribí el nombre del préstamo.'); return }
    if (!rows.length) { alert('No hay filas válidas para importar.'); return }
    setLoading(true)
    setResult(null)
    try {
      const res = await fetchWithAuth('/api/inversiones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resource: 'importar_prestamo', nombre: nombre.trim(), cuotas: rows }),
      })
      const json = await res.json()
      if (res.ok && json.ok) {
        setResult({ ok: true, msg: `✅ Importado: ${json.cuotas} cuotas del préstamo "${nombre.trim()}" (ID ${json.prestamo_id}).` })
        setRows([])
        setErrors([])
        setFileName('')
        setNombre('')
      } else {
        setResult({ ok: false, msg: `❌ Error: ${json.error || 'desconocido'}` })
      }
    } catch {
      setResult({ ok: false, msg: '❌ Error de red al importar.' })
    } finally {
      setLoading(false)
    }
  }

  const pagadas = rows.filter(r => r.pagado).length
  const pendientes = rows.filter(r => !r.pagado).length

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '24px 16px' }}>

      {/* ── Título ── */}
      <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>🏦 Importar cronograma de préstamo</h2>
      <p style={{ color: 'var(--text-muted, #888)', marginBottom: 24, fontSize: 14 }}>
        Cargá la tabla de cuotas desde Excel para que el bot pueda guiarte en los pagos y adelantos.
      </p>

      {/* ── Formato esperado ── */}
      <details open style={{ marginBottom: 24, background: 'var(--card-bg, #f8f9fa)', border: '1px solid var(--border, #e0e0e0)', borderRadius: 8, padding: '12px 16px' }}>
        <summary style={{ fontWeight: 600, cursor: 'pointer', fontSize: 14, marginBottom: 8 }}>
          📋 Formato esperado del archivo
        </summary>
        <div style={{ marginTop: 12, fontSize: 13 }}>
          <p style={{ marginBottom: 8 }}>
            <strong>Extensiones admitidas:</strong>{' '}
            <code style={codeStyle}>.xlsx</code>{' '}
            <code style={codeStyle}>.xls</code>{' '}
            <code style={codeStyle}>.csv</code>
          </p>
          <p style={{ marginBottom: 10 }}>
            El archivo debe tener una <strong>fila de encabezados</strong> en la primera fila. Las columnas se detectan automáticamente por nombre (no importa el orden). Columnas reconocidas:
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--border, #e8e8e8)' }}>
                <th style={th}>Columna</th>
                <th style={th}>Tipo</th>
                <th style={th}>Requerida</th>
                <th style={th}>Descripción</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['numero_cuota', 'Número', '✅', 'Número de cuota (1, 2, 3…)'],
                ['mes', 'Texto / Fecha', '✅', 'Mes previsto de pago. Formatos: YYYY-MM, MM/YYYY o fecha Excel'],
                ['capital', 'Número', '✅', 'Capital de la cuota (sin interés)'],
                ['monto_ordinario', 'Número', '—', 'Monto total a pagar en fecha (capital + interés + IVA)'],
                ['pagado', 'Booleano', '—', 'true/false, SI/NO, 1/0. Cuotas ya abonadas'],
                ['tipo_pago', 'Texto', '—', '"ordinaria" o "adelanto"'],
                ['monto_pagado', 'Número', '—', 'Monto efectivamente pagado'],
                ['fecha_pago', 'Fecha', '—', 'Fecha en que se abonó (DD/MM/YYYY o YYYY-MM-DD)'],
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
          <p style={{ marginTop: 10, color: '#888' }}>
            💡 El sistema calcula automáticamente el monto de adelanto como <strong>capital × 1,25</strong>.
            Las cuotas con <code style={codeStyle}>pagado = true</code> quedan registradas como historial; las demás quedan pendientes.
          </p>
        </div>
      </details>

      {/* ── Nombre del préstamo ── */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
          Nombre del préstamo
        </label>
        <input
          type="text"
          value={nombre}
          onChange={e => setNombre(e.target.value)}
          placeholder="Ej: Préstamo auto"
          style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border, #ccc)', fontSize: 14, boxSizing: 'border-box' }}
        />
      </div>

      {/* ── Zona de drop ── */}
      <div
        onDrop={handleDrop}
        onDragOver={e => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        style={{
          border: '2px dashed var(--border, #ccc)',
          borderRadius: 10,
          padding: '36px 24px',
          textAlign: 'center',
          cursor: 'pointer',
          marginBottom: 20,
          transition: 'border-color 0.2s',
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 8 }}>📂</div>
        <p style={{ fontWeight: 600, marginBottom: 4 }}>
          {fileName || 'Arrastrá el archivo acá o hacé clic para seleccionar'}
        </p>
        <p style={{ fontSize: 12, color: '#888' }}>
          Admite <strong>.xlsx</strong>, <strong>.xls</strong>, <strong>.csv</strong>
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
        />
      </div>

      {/* ── Errores de parseo ── */}
      {errors.length > 0 && (
        <div style={{ background: '#fff3cd', border: '1px solid #ffc107', borderRadius: 8, padding: '12px 16px', marginBottom: 16, fontSize: 13 }}>
          <strong>⚠️ {errors.length} fila{errors.length > 1 ? 's' : ''} con problemas (se omitirán):</strong>
          <ul style={{ marginTop: 6, paddingLeft: 20 }}>
            {errors.slice(0, 8).map((e, i) => <li key={i}>Fila {e.row}: {e.mensaje}</li>)}
            {errors.length > 8 && <li>…y {errors.length - 8} más</li>}
          </ul>
        </div>
      )}

      {/* ── Preview ── */}
      {rows.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>
              Vista previa — {rows.length} cuotas detectadas
            </span>
            <span style={{ fontSize: 12, color: '#888' }}>
              {pagadas} pagadas · {pendientes} pendientes
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'var(--border, #e8e8e8)' }}>
                  {['#', 'Mes', 'Capital', 'Ordinario', 'Adelanto (×1.25)', 'Pagado', 'Monto pag.', 'Fecha pag.'].map(h => (
                    <th key={h} style={th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 10).map((r, i) => (
                  <tr key={i} style={{ background: r.pagado ? 'var(--success-bg, #f0fff4)' : undefined }}>
                    <td style={td}>{r.numero_cuota}</td>
                    <td style={td}>{r.mes}</td>
                    <td style={{ ...td, textAlign: 'right' }}>${fmt(r.capital)}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{r.monto_ordinario ? `$${fmt(r.monto_ordinario)}` : '—'}</td>
                    <td style={{ ...td, textAlign: 'right', color: '#2563eb' }}>${fmt(r.capital * 1.25)}</td>
                    <td style={{ ...td, textAlign: 'center' }}>{r.pagado ? '✅' : '⏳'}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{r.monto_pagado ? `$${fmt(r.monto_pagado)}` : '—'}</td>
                    <td style={td}>{r.fecha_pago || '—'}</td>
                  </tr>
                ))}
                {rows.length > 10 && (
                  <tr>
                    <td colSpan={8} style={{ ...td, textAlign: 'center', color: '#888' }}>
                      …y {rows.length - 10} filas más
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Resultado ── */}
      {result && (
        <div style={{
          padding: '12px 16px', borderRadius: 8, marginBottom: 16, fontSize: 14,
          background: result.ok ? '#d1fae5' : '#fee2e2',
          color: result.ok ? '#065f46' : '#991b1b',
          border: `1px solid ${result.ok ? '#6ee7b7' : '#fca5a5'}`,
        }}>
          {result.msg}
        </div>
      )}

      {/* ── Botón importar ── */}
      <button
        onClick={handleImport}
        disabled={loading || !rows.length || !nombre.trim()}
        style={{
          padding: '10px 28px',
          borderRadius: 8,
          border: 'none',
          background: rows.length && nombre.trim() ? '#2563eb' : '#94a3b8',
          color: '#fff',
          fontWeight: 700,
          fontSize: 14,
          cursor: rows.length && nombre.trim() ? 'pointer' : 'not-allowed',
          opacity: loading ? 0.7 : 1,
        }}
      >
        {loading ? 'Importando…' : `Importar ${rows.length ? rows.length + ' cuotas' : ''}`}
      </button>
    </div>
  )
}

// ── Estilos inline compartidos ────────────────────────────────────────────────
const th: React.CSSProperties = {
  padding: '6px 10px', textAlign: 'left', fontWeight: 600,
  border: '1px solid var(--border, #e0e0e0)',
}
const td: React.CSSProperties = {
  padding: '5px 10px',
  border: '1px solid var(--border, #e0e0e0)',
}
const codeStyle: React.CSSProperties = {
  background: 'var(--border, #eee)', padding: '1px 5px', borderRadius: 3,
  fontFamily: 'monospace', fontSize: 11,
}
