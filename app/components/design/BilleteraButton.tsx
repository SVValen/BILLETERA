/**
 * BilleteraButton — Botón base del sistema de diseño Billetera.
 *
 * Variantes:
 *   primary   — teal  (acción principal: "Registrar gasto", "Guardar")
 *   gold      — oro   (CTA destacado: "Ver presupuesto", "Pagar tarjeta")
 *   secondary — navy  (acción secundaria: "Invertir", "Configurar")
 *   outline   — teal border transparente (acción terciaria: "Ver detalle")
 *   ghost     — crema (acción suave: "Exportar", "Cancelar")
 *   danger    — rojo  (acción destructiva: "Anular", "Eliminar")
 */

import React from 'react'

type Variant = 'primary' | 'gold' | 'secondary' | 'outline' | 'ghost' | 'danger'
type Size    = 'sm' | 'md' | 'lg'

interface BilleteraButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: React.ReactNode
  loading?: boolean
  fullWidth?: boolean
  children: React.ReactNode
}

const styles: Record<Variant, React.CSSProperties> = {
  primary: {
    background: 'var(--b-teal)',
    color: '#fff',
    border: 'none',
  },
  gold: {
    background: 'var(--b-gold)',
    color: 'var(--b-navy)',
    border: 'none',
    fontWeight: 600,
  },
  secondary: {
    background: 'var(--b-navy)',
    color: '#fff',
    border: 'none',
  },
  outline: {
    background: 'transparent',
    color: 'var(--b-teal)',
    border: '1.5px solid var(--b-teal)',
  },
  ghost: {
    background: 'var(--b-cream)',
    color: 'var(--b-navy)',
    border: '0.5px solid var(--b-cream-dk)',
  },
  danger: {
    background: 'var(--b-red)',
    color: '#fff',
    border: 'none',
  },
}

const sizes: Record<Size, React.CSSProperties> = {
  sm: { fontSize: '12px', padding: '6px 12px', borderRadius: '6px' },
  md: { fontSize: '13px', padding: '8px 16px', borderRadius: '8px' },
  lg: { fontSize: '15px', padding: '12px 24px', borderRadius: '10px' },
}

export function BilleteraButton({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  fullWidth = false,
  children,
  style,
  disabled,
  ...props
}: BilleteraButtonProps) {
  const isDisabled = disabled || loading

  const base: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    fontFamily: 'var(--font-body)',
    fontWeight: 500,
    lineHeight: 1,
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    opacity: isDisabled ? 0.55 : 1,
    transition: 'transform 100ms ease, opacity 150ms ease',
    width: fullWidth ? '100%' : undefined,
    whiteSpace: 'nowrap',
    textDecoration: 'none',
    userSelect: 'none',
    ...styles[variant],
    ...sizes[size],
    ...style,
  }

  return (
    <button
      {...props}
      disabled={isDisabled}
      style={base}
      onMouseEnter={e => {
        if (!isDisabled) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85'
      }}
      onMouseLeave={e => {
        if (!isDisabled) (e.currentTarget as HTMLButtonElement).style.opacity = '1'
      }}
      onMouseDown={e => {
        if (!isDisabled) (e.currentTarget as HTMLButtonElement).style.transform = 'scale(0.97)'
      }}
      onMouseUp={e => {
        if (!isDisabled) (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)'
      }}
    >
      {loading ? (
        <span style={{ display: 'inline-block', animation: 'b-spin 0.7s linear infinite' }}>⏳</span>
      ) : icon ? (
        <span aria-hidden="true">{icon}</span>
      ) : null}
      {children}
      <style>{`@keyframes b-spin { to { transform: rotate(360deg); } }`}</style>
    </button>
  )
}

export default BilleteraButton
