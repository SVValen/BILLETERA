/**
 * BilleteraMascot — Benteveo mascota animado para usar en:
 *   - Estados vacíos del dashboard
 *   - Onboarding y primer uso
 *   - Tarjetas de resumen con mensaje del bot
 *   - Notificaciones destacadas
 *
 * Modos: default | happy | alert | thinking
 * Tamaños: sm (60px) | md (90px) | lg (130px)
 */

import React from 'react'

type MascotMood = 'default' | 'happy' | 'alert' | 'thinking'
type MascotSize = 'sm' | 'md' | 'lg'

interface BilleteraMascotProps {
  mood?: MascotMood
  size?: MascotSize
  children?: React.ReactNode
  bubbleStyle?: React.CSSProperties
  style?: React.CSSProperties
  animate?: boolean
}

const sizeMap: Record<MascotSize, number> = {
  sm: 60,
  md: 90,
  lg: 130,
}

function Eyes({ mood }: { mood: MascotMood }) {
  if (mood === 'thinking') {
    return (
      <>
        <ellipse cx="33" cy="36" rx="4.5" ry="4.5" fill="white" />
        <ellipse cx="36" cy="36" rx="2.5" ry="2.5" fill="#1a1a2e" />
        <ellipse cx="37" cy="35" rx="0.8" ry="0.8" fill="white" />
        <ellipse cx="47" cy="36" rx="4.5" ry="4.5" fill="white" />
        <ellipse cx="50" cy="36" rx="2.5" ry="2.5" fill="#1a1a2e" />
        <ellipse cx="51" cy="35" rx="0.8" ry="0.8" fill="white" />
      </>
    )
  }
  return (
    <>
      <ellipse cx="33" cy="36" rx="4.5" ry="4.5" fill="white" />
      <ellipse cx="33" cy="36" rx="2.5" ry="2.5" fill="#1a1a2e" />
      <ellipse cx="34" cy="35" rx="0.8" ry="0.8" fill="white" />
      <ellipse cx="47" cy="36" rx="4.5" ry="4.5" fill="white" />
      <ellipse cx="47" cy="36" rx="2.5" ry="2.5" fill="#1a1a2e" />
      <ellipse cx="48" cy="35" rx="0.8" ry="0.8" fill="white" />
    </>
  )
}

function Brows({ mood }: { mood: MascotMood }) {
  if (mood === 'alert') {
    return (
      <>
        <path d="M29 31 Q33 28 37 30" stroke="#C0392B" strokeWidth="1.5" fill="none" strokeLinecap="round" />
        <path d="M43 30 Q47 28 51 31" stroke="#C0392B" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      </>
    )
  }
  return (
    <>
      <ellipse cx="33" cy="31.5" rx="3" ry="1.2" fill="none" stroke="#C0392B" strokeWidth="1.3" opacity="0.6" />
      <ellipse cx="47" cy="31.5" rx="3" ry="1.2" fill="none" stroke="#C0392B" strokeWidth="1.3" opacity="0.6" />
    </>
  )
}

function Mouth({ mood }: { mood: MascotMood }) {
  if (mood === 'happy') {
    return (
      <>
        <path d="M37 43 L40 47 L43 43" fill="#F0B428" />
        <path d="M34 43 L46 43" stroke="#C49A14" strokeWidth="1" fill="none" />
        <path d="M36 46 Q40 50 44 46" stroke="#C49A14" strokeWidth="1" fill="none" strokeLinecap="round" />
      </>
    )
  }
  return (
    <>
      <path d="M37 43 L40 47 L43 43" fill="#F0B428" />
      <path d="M34 43 L46 43" stroke="#C49A14" strokeWidth="1" fill="none" />
    </>
  )
}

export function BilleteraMascot({
  mood = 'default',
  size = 'md',
  children,
  bubbleStyle,
  style,
  animate = true,
}: BilleteraMascotProps) {
  const dim = sizeMap[size]

  const floatKeyframes = `
    @keyframes b-float {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-6px); }
    }
    @keyframes b-blink {
      0%, 90%, 100% { transform: scaleY(1); }
      95% { transform: scaleY(0.1); }
    }
    @keyframes b-glow {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }
  `

  const svgStyle: React.CSSProperties = animate
    ? { animation: 'b-float 3s ease-in-out infinite' }
    : {}

  const eyeGroupStyle: React.CSSProperties = animate
    ? { animation: 'b-blink 4s ease-in-out infinite', transformOrigin: 'center' }
    : {}

  const coinStyle: React.CSSProperties = animate
    ? { animation: 'b-glow 2s ease-in-out infinite' }
    : {}

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: size === 'sm' ? '8px' : '14px',
        ...style,
      }}
    >
      <style>{floatKeyframes}</style>

      <div style={{ flexShrink: 0, ...svgStyle }}>
        <svg
          width={dim}
          height={dim * 1.25}
          viewBox="0 0 80 100"
          xmlns="http://www.w3.org/2000/svg"
          aria-label="Billetero, el asistente financiero"
          role="img"
        >
          <ellipse cx="40" cy="55" rx="22" ry="26" fill="#9E9E9E" />
          <ellipse cx="40" cy="55" rx="16" ry="20" fill="#E0E0E0" />
          <ellipse cx="40" cy="38" rx="18" ry="16" fill="#9E9E9E" />
          <path d="M30 32 Q40 24 50 32" fill="#1a1a2e" />
          <path d="M33 28 Q40 22 47 28 Q44 18 40 16 Q36 18 33 28Z" fill="#333" />
          <g style={eyeGroupStyle}>
            <Eyes mood={mood} />
          </g>
          <Brows mood={mood} />
          <Mouth mood={mood} />
          <rect x="22" y="50" width="36" height="28" rx="6" fill="#286450" />
          <rect x="25" y="52" width="30" height="24" rx="4" fill="#2E7A5C" />
          <line x1="28" y1="58" x2="35" y2="58" stroke="#3CA0A0" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="28" y1="62" x2="40" y2="62" stroke="#3CA0A0" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="28" y1="66" x2="37" y2="66" stroke="#3CA0A0" strokeWidth="1.5" strokeLinecap="round" />
          <g style={coinStyle}>
            <ellipse cx="57" cy="48" rx="10" ry="10" fill="#F0C83C" />
            <ellipse cx="57" cy="48" rx="8" ry="8" fill="none" stroke="#C49A14" strokeWidth="1" />
            <text
              x="57" y="52"
              textAnchor="middle"
              fontSize="9"
              fontWeight="700"
              fill="#8A6000"
              fontFamily="sans-serif"
            >
              $AR
            </text>
          </g>
          <path d="M18 72 Q12 80 14 88 L20 85 Q22 90 18 72Z" fill="#9E9E9E" />
          <path d="M62 72 Q68 80 66 88 L60 85 Q58 90 62 72Z" fill="#9E9E9E" />
          <path d="M30 78 L26 92" stroke="#C49A14" strokeWidth="3" strokeLinecap="round" />
          <path d="M50 78 L54 92" stroke="#C49A14" strokeWidth="3" strokeLinecap="round" />
          <ellipse cx="26" cy="93" rx="4" ry="2.5" fill="#C49A14" />
          <ellipse cx="54" cy="93" rx="4" ry="2.5" fill="#C49A14" />
        </svg>
      </div>

      {children && (
        <div
          style={{
            background: 'var(--b-white, #fff)',
            border: '0.5px solid var(--b-gray-lt, #E8E8E8)',
            borderRadius: size === 'sm' ? '8px 8px 8px 2px' : '12px 12px 12px 2px',
            padding: size === 'sm' ? '8px 12px' : '12px 16px',
            maxWidth: size === 'lg' ? '360px' : '280px',
            fontFamily: 'var(--font-body, Inter, sans-serif)',
            fontSize: size === 'sm' ? '12px' : '13px',
            lineHeight: 1.5,
            color: 'var(--b-navy, #0D2B3E)',
            ...bubbleStyle,
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}

export default BilleteraMascot
