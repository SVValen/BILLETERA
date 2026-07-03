/**
 * BilleteraAlert — Avisos contextuales del sistema de diseño Billetera.
 *
 * Variantes:
 *   success  — verde  (gasto registrado, cuota pagada, inversión confirmada)
 *   warning  — oro    (80% de presupuesto, vencimiento próximo, carry borderline)
 *   danger   — rojo   (presupuesto excedido, tope de tarjeta superado, carry negativo)
 *   info     — teal   (carry trade, datos de mercado, recordatorio de cuota)
 */

import React from 'react'

type AlertVariant = 'success' | 'warning' | 'danger' | 'info'

interface BilleteraAlertProps {
  variant?: AlertVariant
  title: string
  children?: React.ReactNode
  onClose?: () => void
  className?: string
  style?: React.CSSProperties
}

const config: Record<AlertVariant, {
  bg: string
  border: string
  iconBg: string
  iconColor: string
  icon: string
  titleColor: string
}> = {
  success: {
    bg: 'var(--b-green-bg)',
    border: 'var(--b-green)',
    iconBg: 'var(--b-green)',
    iconColor: '#fff',
    icon: '✓',
    titleColor: 'var(--b-green)',
  },
  warning: {
    bg: 'var(--b-gold-bg)',
    border: 'var(--b-gold-dk)',
    iconBg: 'var(--b-gold)',
    iconColor: 'var(--b-navy)',
    icon: '!',
    titleColor: 'var(--b-gold-dk)',
  },
  danger: {
    bg: 'var(--b-red-bg)',
    border: 'var(--b-red)',
    iconBg: 'var(--b-red)',
    iconColor: '#fff',
    icon: '×',
    titleColor: 'var(--b-red)',
  },
  info: {
    bg: 'var(--b-teal-bg)',
    border: 'var(--b-teal)',
    iconBg: 'var(--b-teal)',
    iconColor: '#fff',
    icon: 'i',
    titleColor: 'var(--b-teal)',
  },
}

export function BilleteraAlert({
  variant = 'info',
  title,
  children,
  onClose,
  className,
  style,
}: BilleteraAlertProps) {
  const c = config[variant]

  return (
    <div
      role="alert"
      className={className}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
        background: c.bg,
        borderLeft: `3px solid ${c.border}`,
        borderRadius: '10px',
        padding: '12px 14px',
        position: 'relative',
        ...style,
      }}
    >
      <div
        aria-hidden="true"
        style={{
          flexShrink: 0,
          width: '20px',
          height: '20px',
          borderRadius: '50%',
          background: c.iconBg,
          color: c.iconColor,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '10px',
          fontWeight: 700,
          fontFamily: 'var(--font-body)',
          marginTop: '1px',
        }}
      >
        {c.icon}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--font-body)',
            fontSize: '12px',
            fontWeight: 600,
            color: c.titleColor,
            marginBottom: children ? '3px' : 0,
          }}
        >
          {title}
        </p>
        {children && (
          <p
            style={{
              margin: 0,
              fontFamily: 'var(--font-body)',
              fontSize: '13px',
              color: 'var(--b-navy)',
              lineHeight: 1.5,
              opacity: 0.85,
            }}
          >
            {children}
          </p>
        )}
      </div>

      {onClose && (
        <button
          onClick={onClose}
          aria-label="Cerrar aviso"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--b-gray)',
            fontSize: '16px',
            lineHeight: 1,
            padding: '0 2px',
            flexShrink: 0,
          }}
        >
          ×
        </button>
      )}
    </div>
  )
}

/**
 * BilleteraAlertStack — Contenedor para múltiples alertas apiladas con gap.
 */
export function BilleteraAlertStack({
  children,
  style,
}: {
  children: React.ReactNode
  style?: React.CSSProperties
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', ...style }}>
      {children}
    </div>
  )
}

export default BilleteraAlert
