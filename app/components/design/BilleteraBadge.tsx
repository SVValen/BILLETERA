/**
 * BilleteraBadge — Etiquetas de estado y contexto.
 *
 * Variantes:
 *   teal    — tarjeta de crédito, categoría, tipo de activo
 *   gold    — advertencia suave, 80% presupuesto
 *   navy    — info neutral, n° de cuota, efectivo
 *   green   — pagado, éxito, carry positivo
 *   red     — excedido, vencido, carry negativo
 *   gray    — estado deshabilitado, archivado
 */

import React from 'react'

type BadgeVariant = 'teal' | 'gold' | 'navy' | 'green' | 'red' | 'gray'

interface BilleteraBadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
  style?: React.CSSProperties
}

const badgeStyles: Record<BadgeVariant, React.CSSProperties> = {
  teal:  { background: 'var(--b-teal-bg)',  color: '#0D6E6E' },
  gold:  { background: 'var(--b-gold-bg)',  color: 'var(--b-gold-dk)' },
  navy:  { background: '#E0EAF0',           color: 'var(--b-navy)' },
  green: { background: 'var(--b-green-bg)', color: 'var(--b-green)' },
  red:   { background: 'var(--b-red-bg)',   color: 'var(--b-red)' },
  gray:  { background: '#F0F0F0',           color: 'var(--b-gray)' },
}

export function BilleteraBadge({
  variant = 'navy',
  children,
  style,
}: BilleteraBadgeProps) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontFamily: 'var(--font-body)',
        fontSize: 'var(--text-tiny)',
        fontWeight: 500,
        padding: '3px 9px',
        borderRadius: 'var(--radius-pill)',
        lineHeight: 1.4,
        whiteSpace: 'nowrap',
        ...badgeStyles[variant],
        ...style,
      }}
    >
      {children}
    </span>
  )
}

export default BilleteraBadge
