'use client'

import { useState } from 'react'
import { createSupabaseBrowser } from '@/lib/supabase-browser'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [loadingEmail, setLoadingEmail] = useState(false)
  const [loadingGoogle, setLoadingGoogle] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGoogle() {
    setLoadingGoogle(true)
    setError(null)
    const supabase = createSupabaseBrowser()
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${location.origin}/auth/callback`,
      },
    })
    if (error) {
      setError(error.message)
      setLoadingGoogle(false)
    }
    // Si no hay error, el browser hace redirect — no resetear loading
  }

  async function handleEmail(e: React.FormEvent) {
    e.preventDefault()
    setLoadingEmail(true)
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
    setLoadingEmail(false)
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
            <p className="auth-sub">Ingresá para ver tus finanzas.</p>

            {/* Google */}
            <button
              onClick={handleGoogle}
              disabled={loadingGoogle || loadingEmail}
              className="auth-btn-google"
            >
              <GoogleIcon />
              {loadingGoogle ? 'Redirigiendo...' : 'Continuar con Google'}
            </button>

            <div className="auth-divider">
              <span>o</span>
            </div>

            {/* Email magic link */}
            <form onSubmit={handleEmail} className="auth-form">
              <input
                type="email"
                placeholder="tu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="auth-input"
              />
              <button
                type="submit"
                disabled={loadingEmail || loadingGoogle}
                className="auth-btn auth-btn-secondary"
              >
                {loadingEmail ? 'Enviando...' : 'Enviar link por email'}
              </button>
            </form>

            {error && <p className="auth-error">{error}</p>}
          </>
        )}
      </div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  )
}
