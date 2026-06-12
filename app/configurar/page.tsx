'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { createSupabaseBrowser } from '@/lib/supabase-browser'

export default function ConfigurarPage() {
  const [telegramId, setTelegramId] = useState('')
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  useEffect(() => {
    async function check() {
      const supabase = createSupabaseBrowser()
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) { router.push('/login'); return }

      // Si ya tiene perfil, ir directo al dashboard
      const { data } = await supabase.from('perfiles').select('telegram_id').eq('id', user.id).single()
      if (data?.telegram_id) { router.push('/dashboard'); return }

      setChecking(false)
    }
    check()
  }, [router])

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
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) { router.push('/login'); return }

    const { error } = await supabase.from('perfiles').upsert({
      id: user.id,
      telegram_id: id,
      nombre: user.email,
    })

    if (error) {
      setError('No se pudo guardar. ¿Ya está en uso ese Telegram ID?')
    } else {
      router.push('/dashboard')
    }
    setLoading(false)
  }

  if (checking) return <div className="auth-page"><p style={{ color: '#aaa' }}>Verificando...</p></div>

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Vincular Telegram 📱</h1>
        <p className="auth-sub">
          Para ver tus movimientos, necesitás vincular tu cuenta de Telegram.<br /><br />
          Mandá el comando <code>/id</code> a tu bot de Telegram y pegá el número que te responde.
        </p>
        <form onSubmit={handleSubmit} className="auth-form">
          <input
            type="text"
            inputMode="numeric"
            placeholder="Ej: 123456789"
            value={telegramId}
            onChange={e => setTelegramId(e.target.value)}
            required
            className="auth-input"
            autoFocus
          />
          {error && <p className="auth-error">{error}</p>}
          <button type="submit" disabled={loading} className="auth-btn">
            {loading ? 'Guardando...' : 'Vincular y entrar'}
          </button>
        </form>
      </div>
    </div>
  )
}
