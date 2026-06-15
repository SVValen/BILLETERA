'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { createSupabaseBrowser } from '@/lib/supabase-browser'
import ResumenTab from './ResumenTab'
import PresupuestosTab from './PresupuestosTab'
import ObjetivosTab from './ObjetivosTab'
import MovimientosTab from './MovimientosTab'

type Tab = 'resumen' | 'presupuestos' | 'objetivos' | 'movimientos'

const TABS: { id: Tab; label: string }[] = [
  { id: 'resumen', label: 'Resumen' },
  { id: 'presupuestos', label: 'Presupuestos' },
  { id: 'objetivos', label: 'Objetivos' },
  { id: 'movimientos', label: 'Movimientos' },
]

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>('resumen')
  const [mes, setMes] = useState(() => new Date().toISOString().slice(0, 7))
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [telegramId, setTelegramId] = useState<string | null>(null)
  const [dark, setDark] = useState(false)
  const router = useRouter()

  // Auth
  useEffect(() => {
    async function checkAuth() {
      const supabase = createSupabaseBrowser()
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) { router.push('/login'); return }
      setUserEmail(user.email ?? null)
      const { data: perfil } = await supabase
        .from('perfiles').select('telegram_id').eq('id', user.id).single()
      if (!perfil?.telegram_id) { router.push('/configurar'); return }
      setTelegramId(perfil.telegram_id)
    }
    checkAuth()
  }, [router])

  // Dark mode
  useEffect(() => {
    const saved = localStorage.getItem('dark') === '1'
    setDark(saved)
    document.documentElement.classList.toggle('dark', saved)
  }, [])

  function toggleDark() {
    const next = !dark
    setDark(next)
    localStorage.setItem('dark', next ? '1' : '0')
    document.documentElement.classList.toggle('dark', next)
  }

  async function handleLogout() {
    const supabase = createSupabaseBrowser()
    await supabase.auth.signOut()
    router.push('/login')
  }

  if (!telegramId) {
    return <div className="auth-page"><p style={{ color: '#aaa' }}>Verificando sesión...</p></div>
  }

  const showMes = tab === 'resumen' || tab === 'presupuestos' || tab === 'movimientos'

  return (
    <>
      {/* Nav */}
      <div className="nav">
        <span className="nav-title">Billetera 💰</span>
        <div className="nav-user">
          <button className="btn-icon" onClick={toggleDark} title={dark ? 'Modo claro' : 'Modo oscuro'}>
            {dark ? '☀️' : '🌙'}
          </button>
          <span className="nav-email">{userEmail}</span>
          <button className="nav-logout" onClick={handleLogout}>Salir</button>
        </div>
      </div>

      {/* Tabs + mes selector */}
      <div className="tabs-bar">
        <div className="tabs">
          {TABS.map(t => (
            <button key={t.id} className={`tab-btn ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        {showMes && (
          <input
            type="month"
            value={mes}
            onChange={e => setMes(e.target.value)}
            className="month-input"
          />
        )}
      </div>

      <div className="page">
        {tab === 'resumen' && <ResumenTab mes={mes} />}
        {tab === 'presupuestos' && <PresupuestosTab mes={mes} />}
        {tab === 'objetivos' && <ObjetivosTab />}
        {tab === 'movimientos' && <MovimientosTab mes={mes} />}
      </div>
    </>
  )
}
