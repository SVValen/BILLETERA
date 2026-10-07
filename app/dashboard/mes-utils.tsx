// Utilidades compartidas por las pestañas Mes, Próximos meses y En qué gasto.

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

export function fmt(n: number) {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 }).format(n)
}

export function nombreMes(mes: string) {
  const [y, m] = mes.split('-')
  const n = MESES[Number(m) - 1] ?? mes
  return `${n.charAt(0).toUpperCase()}${n.slice(1)} ${y}`
}

export function mesCorto(mes: string) {
  return MESES[Number(mes.split('-')[1]) - 1] ?? mes
}

export function sumarMeses(mes: string, n: number) {
  const [y, m] = mes.split('-').map(Number)
  const d = new Date(y, m - 1 + n, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** '1.522.876' / '1522876' / '1.522.876,50' / '1522876.5' → número; null si no es válido */
export function parseMonto(raw: string): number | null {
  const t = raw.replace(/\$/g, '').trim()
  if (!t) return null
  const n = t.includes(',')
    ? Number(t.replace(/\./g, '').replace(',', '.'))
    : Number(/\.\d{3}(\.|$)/.test(t) ? t.replace(/\./g, '') : t)
  return Number.isFinite(n) && n > 0 ? n : null
}

export function Check() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  )
}

export function Chevron({ dir }: { dir: 'left' | 'right' | 'down' }) {
  const d = dir === 'left' ? 'M15 18l-6-6 6-6' : dir === 'right' ? 'M9 18l6-6-6-6' : 'M6 9l6 6 6-6'
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}
