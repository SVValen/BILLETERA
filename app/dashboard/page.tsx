'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { createSupabaseBrowser } from '@/lib/supabase-browser'
import { BilleteraButton } from '@/app/components/design'
import MesTab from './MesTab'
import ProximosTab from './ProximosTab'
import GastosTab from './GastosTab'
import PlanillaTab from './PlanillaTab'
import FamiliaTab from './FamiliaTab'
import PresupuestosTab from './PresupuestosTab'
import MovimientosTab from './MovimientosTab'
import PrestamosTab from './PrestamosTab'
import CategoriasTab from './CategoriasTab'

type Tab = 'mes' | 'proximos' | 'gastos' | 'familia' | 'movimientos' | 'ajustes'
type Ajuste = 'prestamos' | 'presupuestos' | 'categorias'
type VistaMov = 'lista' | 'planilla'

const TABS: { id: Tab; label: string }[] = [
  { id: 'mes', label: 'Mes' },
  { id: 'proximos', label: 'Próximos meses' },
  { id: 'gastos', label: 'En qué gasto' },
  { id: 'familia', label: 'Cuotas familia' },
  { id: 'movimientos', label: 'Movimientos' },
  { id: 'ajustes', label: 'Ajustes' },
]

const AJUSTES: { id: Ajuste; label: string }[] = [
  { id: 'prestamos', label: 'Préstamos' },
  { id: 'presupuestos', label: 'Presupuestos' },
  { id: 'categorias', label: 'Categorías' },
]

export default function Dashboard() {
  const [tab, setTab] = useState<Tab>('mes')
  const [ajuste, setAjuste] = useState<Ajuste>('prestamos')
  const [vistaMov, setVistaMov] = useState<VistaMov>('lista')
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

  const showMes = tab === 'gastos' || tab === 'familia' || tab === 'movimientos'


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
        {tab === 'mes' && <MesTab mes={mes} onMes={setMes} onIr={t => setTab(t)} />}
        {tab === 'proximos' && <ProximosTab desde={mes} onAbrirMes={m => { setMes(m); setTab('mes') }} />}
        {tab === 'gastos' && <GastosTab mes={mes} />}
        {tab === 'familia' && <FamiliaTab mes={mes} />}
        {tab === 'movimientos' && (
          <>
            <div className="subtabs" role="tablist" aria-label="Vista de movimientos">
              <button type="button" role="tab" aria-selected={vistaMov === 'lista'} className={vistaMov === 'lista' ? 'active' : ''} onClick={() => setVistaMov('lista')}>Lista</button>
              <button type="button" role="tab" aria-selected={vistaMov === 'planilla'} className={vistaMov === 'planilla' ? 'active' : ''} onClick={() => setVistaMov('planilla')}>Como la planilla</button>
            </div>
            {vistaMov === 'lista' ? <MovimientosTab mes={mes} /> : <PlanillaTab mes={mes} />}
          </>
        )}
        {tab === 'ajustes' && (
          <>
            <div className="subtabs" role="tablist" aria-label="Ajustes">
              {AJUSTES.map(a => (
                <button key={a.id} type="button" role="tab" aria-selected={ajuste === a.id} className={ajuste === a.id ? 'active' : ''} onClick={() => setAjuste(a.id)}>{a.label}</button>
              ))}
            </div>
            {ajuste === 'prestamos' && <PrestamosTab />}
            {ajuste === 'presupuestos' && <PresupuestosTab mes={mes} />}
            {ajuste === 'categorias' && <CategoriasTab />}
          </>
        )}
      </div>
    </>
  )
}
