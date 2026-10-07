'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { createSupabaseBrowser } from '@/lib/supabase-browser'
import { BilleteraButton } from '@/app/components/design'
import InicioTab from './InicioTab'
import PlanillaTab from './PlanillaTab'
import FamiliaTab from './FamiliaTab'
import DetalleMensualTab from './DetalleMensualTab'
import PresupuestosTab from './PresupuestosTab'
import MovimientosTab from './MovimientosTab'
import PrestamosTab from './PrestamosTab'
import CategoriasTab from './CategoriasTab'

type Tab = 'inicio' | 'planilla' | 'familia' | 'detalle' | 'presupuestos' | 'movimientos' | 'prestamos' | 'categorias'

const TABS: { id: Tab; label: string }[] = [
  { id: 'inicio', label: 'Inicio' },
  { id: 'planilla', label: 'Planilla del mes' },
  { id: 'familia', label: 'Cuotas familia' },
  { id: 'detalle', label: 'Detalle mensual' },
  { id: 'presupuestos', label: 'Presupuestos' },
  { id: 'movimientos', label: 'Movimientos' },
  { id: 'categorias', label: 'Categorías' },
  { id: 'prestamos', label: '🏦 Préstamos' },
]

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>('inicio')
  const [mes, setMes] = useState(() => new Date().toISOString().slice(0, 7))
  const [telegramId, setTelegramId] = useState<string | null>(null)
  const [dark, setDark] = useState(false)
  const router = useRouter()

  // Auth
  useEffect(() => {
    async function checkAuth() {
      const supabase = createSupabaseBrowser()
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) { router.push('/login'); return }
      const { data: perfil } = await supabase
        .from('perfiles').select('telegram_id').eq('id', user.id).single()
      if (!perfil?.telegram_id) { router.push('/login'); return }
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

  const showMes = tab === 'inicio' || tab === 'planilla' || tab === 'familia' || tab === 'detalle' || tab === 'presupuestos' || tab === 'movimientos'


  return (
    <>
      {/* Nav */}
      <div className="nav">
        <span className="nav-title">BilleTero 💰</span>
        <div className="nav-user">
          <button className="btn-icon" onClick={toggleDark} title={dark ? 'Modo claro' : 'Modo oscuro'}>
            {dark ? '☀️' : '🌙'}
          </button>
          <span className="nav-email">{telegramId}</span>
          <BilleteraButton variant="ghost" size="sm" onClick={handleLogout}>Salir</BilleteraButton>
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
        {tab === 'inicio' && <InicioTab mes={mes} />}
        {tab === 'planilla' && <PlanillaTab mes={mes} />}
        {tab === 'familia' && <FamiliaTab mes={mes} />}
        {tab === 'detalle' && <DetalleMensualTab mes={mes} />}
        {tab === 'presupuestos' && <PresupuestosTab mes={mes} />}
        {tab === 'movimientos' && <MovimientosTab mes={mes} />}
        {tab === 'categorias' && <CategoriasTab />}
        {tab === 'prestamos' && <PrestamosTab />}
      </div>
    </>
  )
}
