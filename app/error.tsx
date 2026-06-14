'use client'

import { useEffect } from 'react'

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h2 className="auth-title">Algo salió mal</h2>
        <p className="auth-sub">{error.message || 'Error inesperado. Intentá de nuevo.'}</p>
        <button className="auth-btn" onClick={reset}>Reintentar</button>
      </div>
    </div>
  )
}
