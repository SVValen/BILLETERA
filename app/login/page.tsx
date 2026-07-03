'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createSupabaseBrowser } from '@/lib/supabase-browser'

function telegramIdToEmail(telegramId: string) {
  return `${telegramId}@telegram.local`
}

export default function LoginPage() {
  const [telegramId, setTelegramId] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    const id = telegramId.trim()
    if (!/^\d+$/.test(id)) {
      setError('El ID de Telegram solo contiene números')
      setLoading(false)
      return
    }

    const supabase = createSupabaseBrowser()
    const email = telegramIdToEmail(id)

    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password })

    if (signInError) {
      const { data: signUpData, error: signUpError } = await supabase.auth.signUp({ email, password })
      if (signUpError) {
        setError(signUpError.message.includes('already registered') ? 'Contraseña incorrecta' : signUpError.message)
        setLoading(false)
        return
      }
      if (!signUpData.user || !signUpData.session) {
        setError('No se pudo iniciar sesión tras crear la cuenta.')
        setLoading(false)
        return
      }
      await supabase.from('perfiles').upsert({ id: signUpData.user.id, telegram_id: id, nombre: id })
      router.push('/dashboard')
      return
    }

    await supabase.from('perfiles').upsert({ id: data.user.id, telegram_id: id, nombre: id })
    router.push('/dashboard')
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Billetera 💰</h1>
        <p className="auth-sub">
          Ingresá con tu ID de Telegram y contraseña.<br />
          Si es tu primera vez, se crea la cuenta automáticamente.
        </p>
        <form onSubmit={handleSubmit} className="auth-form">
          <input
            type="text"
            inputMode="numeric"
            placeholder="ID de Telegram (ej: 123456789)"
            value={telegramId}
            onChange={e => setTelegramId(e.target.value)}
            required
            className="auth-input"
            autoFocus
          />
          <input
            type="password"
            placeholder="Contraseña"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={6}
            className="auth-input"
          />
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" disabled={loading} className="auth-btn">
            {loading ? 'Ingresando...' : 'Ingresar'}
          </button>
        </form>
      </div>
    </div>
  )
}
