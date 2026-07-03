/**
 * BilleteraCardResumen — Card de resumen mensual de tarjeta de crédito.
 */

import React from 'react'
import { BilleteraBadge } from './BilleteraBadge'
import { BilleteraButton } from './BilleteraButton'
import { BilleteraAlert } from './BilleteraAlert'

interface BilleteraCardResumenProps {
  tarjeta: string
  mes: string
  totalAPagar: number
  cuotasFijas: number
  topeVariable: number
  gastoVariableActual: number
  montoColchon: number
  onPagar?: () => void
  onAjustar?: () => void
  style?: React.CSSProperties
}

function formatARS(n: number): string {
  return n.toLocaleString('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 })
}

export function BilleteraCardResumen({
  tarjeta,
  mes,
  totalAPagar,
  cuotasFijas,
  topeVariable,
  gastoVariableActual,
  montoColchon,
  onPagar,
  onAjustar,
  style,
}: BilleteraCardResumenProps) {
  const necesario = cuotasFijas + topeVariable
  const cubierto = montoColchon >= necesario
  const pctColchon = Math.min(100, Math.round((montoColchon / necesario) * 100))
  const exceso = gastoVariableActual > topeVariable
    ? gastoVariableActual - topeVariable
    : 0

  const barColor = cubierto
    ? 'var(--b-teal)'
    : pctColchon >= 80
    ? 'var(--b-gold)'
    : 'var(--b-red)'

  return (
    <div
      style={{
        background: 'var(--b-white, #fff)',
        border: '0.5px solid var(--b-gray-lt, #E8E8E8)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        ...style,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontWeight: 600,
            fontSize: '13px',
            color: 'var(--b-navy)',
          }}
        >
          Resumen {mes} · {tarjeta}
        </span>
        <BilleteraBadge variant="teal">💳 TC</BilleteraBadge>
      </div>

      <div>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 800,
            fontSize: '26px',
            color: 'var(--b-navy)',
            lineHeight: 1.1,
          }}
        >
          {formatARS(totalAPagar)}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '11px',
            color: 'var(--b-gray)',
            marginTop: '3px',
          }}
        >
          Cuotas fijas {formatARS(cuotasFijas)} · Tope variable {formatARS(topeVariable)}
        </div>
      </div>

      <div>
        <div
          style={{
            height: '6px',
            background: 'var(--b-gray-lt)',
            borderRadius: '10px',
            overflow: 'hidden',
            marginBottom: '6px',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${pctColchon}%`,
              background: barColor,
              borderRadius: '10px',
              transition: 'width 0.4s ease',
            }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-body)',
            fontSize: '11px',
            color: 'var(--b-gray)',
          }}
        >
          <span>
            Colchón: {formatARS(montoColchon)} ({pctColchon}%)
            {cubierto ? ' ✓' : ''}
          </span>
          {!cubierto && (
            <span>Faltan: {formatARS(necesario - montoColchon)}</span>
          )}
        </div>
      </div>

      {exceso > 0 && (
        <BilleteraAlert
          variant="danger"
          title={`Te pasaste ${formatARS(exceso)} del tope variable`}
          onClose={onAjustar}
        >
          Gastaste {formatARS(gastoVariableActual)} de {formatARS(topeVariable)} en variable con TC.
        </BilleteraAlert>
      )}

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <BilleteraButton variant="gold" onClick={onPagar}>
          Pagar tarjeta
        </BilleteraButton>
        {exceso > 0 && (
          <BilleteraButton variant="outline" onClick={onAjustar}>
            Ajustar colchón +{formatARS(exceso)}
          </BilleteraButton>
        )}
      </div>
    </div>
  )
}

export default BilleteraCardResumen
