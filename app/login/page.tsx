'use client'

import { useState } from 'react'
import { createSupabaseBrowser } from '@/lib/supabase-browser'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleEmail(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    const supabase = createSupabaseBrowser()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${location.origin}/auth/callback` },
    })
    if (error) {
      setError(error.message)
    } else {
      setSent(true)
    }
    setLoading(false)
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Billetera 💰</h1>

        {sent ? (
          <div className="auth-success">
            <p>📬 Revisá tu email</p>
            <p className="auth-sub">
              Te mandamos un link a <strong>{email}</strong>.<br />
              Hacé click en él para ingresar.
            </p>
          </div>
        ) : (
          <>
            <p className="auth-sub">Ingresá con tu email — te mandamos un link mágico.</p>
            <form onSubmit={handleEmail} className="auth-form">
              <input
                type="email"
                placeholder="tu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="auth-input"
                autoFocus
              />
              {error && <p className="auth-error">{error}</p>}
              <button type="submit" disabled={loading} className="auth-btn">
                {loading ? 'Enviando...' : 'Enviar link'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
