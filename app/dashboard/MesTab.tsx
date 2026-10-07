'use client'

import { useCallback, useEffect, useState } from 'react'
import { fetchWithAuth } from '@/lib/fetch-with-auth'
import { BilleteraAlert } from '@/app/components/design'
import { fmt, nombreMes, mesCorto, sumarMeses, parseMonto, Check, Chevron } from './mes-utils'

interface Item {
  id: number
  descripcion: string
  monto: number
  cuota_nro: number | null
  cuota_total: number | null
  moneda: 'ARS' | 'USD'
  monto_original: number | null
  debito_automatico: boolean
  estimado: boolean
  pagado: boolean
  concepto: string | null
  rubro: string | null
  cuota_id?: number
}

interface GrupoEntra { grupo: string; total: number; items: Item[] }

interface GrupoSale {
  grupo: string
  nombre: string
  tipo: 'tarjeta' | 'prestamo' | 'alquiler' | 'otro'
  tarjeta_id?: number
  total: number
  cargado: number
  estado: 'pagado' | 'pendiente' | 'parcial'
  monto_pagado?: number | null
  fecha_pago?: string | null
  sin_detallar?: number
  falta?: number
  pagado_monto: number
  items: Item[]
}

interface ResumenMes {
  mes: string
  entra: number
  sale: number
  te_queda: number
  ya_pagado: number
  falta_pagar: number
  pendientes: number
  hay_estimados: boolean
  entra_grupos: GrupoEntra[]
  sale_grupos: GrupoSale[]
}

interface Proximo { mes: string; entra: number; sale: number; te_queda: number }

const CONCEPTO: Record<string, string> = {
  alquiler: 'Alquiler', expensas: 'Expensas', agua: 'Agua', gas: 'Gas', luz: 'Luz',
}

function detalleItem(i: Item, grupo: GrupoSale | null) {
  const partes: string[] = []
  if (i.cuota_nro != null && i.cuota_total != null && i.cuota_total > 1) {
    partes.push(`cuota ${i.cuota_nro} de ${i.cuota_total}${i.cuota_nro === i.cuota_total ? ', la última' : ''}`)
  }
  if (i.moneda === 'USD' && i.monto_original != null) partes.push(`USD ${i.monto_original.toLocaleString('es-AR')}`)
  if (i.debito_automatico) partes.push('débito automático')
  if (grupo?.tipo === 'alquiler' && i.concepto === 'expensas') partes.push('liquidación del mes anterior')
  return partes.join(' · ')
}

function Chip({ estado, plural }: { estado: GrupoSale['estado']; plural?: boolean }) {
  if (estado === 'pagado') {
    return <span className="mes-chip mes-chip-ok"><Check />{plural ? 'Pagados' : 'Pagada'}</span>
  }
  if (estado === 'parcial') return <span className="mes-chip mes-chip-pend">Falta una parte</span>
  return <span className="mes-chip mes-chip-pend">Falta pagar</span>
}

export default function MesTab({ mes, onMes, onIr }: { mes: string; onMes: (m: string) => void; onIr: (tab: 'proximos') => void }) {
  const [data, setData] = useState<ResumenMes | null>(null)
  const [siguiente, setSiguiente] = useState<Proximo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [abiertos, setAbiertos] = useState<Record<string, boolean>>({})
  const [montos, setMontos] = useState<Record<string, string>>({})
  const [corrigiendo, setCorrigiendo] = useState<Record<string, boolean>>({})
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [editIngreso, setEditIngreso] = useState<{ id: number; monto: string } | null>(null)
  const [nuevoIngreso, setNuevoIngreso] = useState<{ descripcion: string; monto: string; grupo: string } | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancel = false
    setLoading(true)
    setError(null)
    Promise.all([
      fetchWithAuth(`/api/stats?mes=${mes}&resource=mes`).then(r => r.json()),
      fetchWithAuth(`/api/stats?mes=${sumarMeses(mes, 1)}&resource=proximos&n=1`).then(r => r.json()).catch(() => null),
    ])
      .then(([d, p]) => {
        if (cancel) return
        if (d?.error) { setError(d.error); return }
        setData(d)
        setSiguiente(p?.meses?.[0] ?? null)
      })
      .catch(e => { if (!cancel) setError(e instanceof Error ? e.message : 'No se pudo cargar el mes') })
      .finally(() => { if (!cancel) setLoading(false) })
    return () => { cancel = true }
  }, [mes, reload])

  const accion = useCallback(async (clave: string, url: string, method: string, body: unknown) => {
    setOcupado(clave)
    try {
      const r = await fetchWithAuth(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (!r.ok) {
        const t = await r.text()
        let msg = t
        try { msg = JSON.parse(t).error ?? t } catch { /* texto plano */ }
        setError(msg || 'No se pudo guardar')
        return
      }
      setReload(k => k + 1)
    } finally {
      setOcupado(null)
    }
  }, [])

  const pagarTarjeta = (g: GrupoSale) => {
    const raw = montos[g.grupo]
    const monto = raw == null || raw.trim() === '' ? (g.monto_pagado ?? g.cargado) : parseMonto(raw)
    if (monto == null) return
    setCorrigiendo(c => ({ ...c, [g.grupo]: false }))
    accion(`g-${g.grupo}`, '/api/stats', 'PUT', { resource: 'pagar_tarjeta', tarjeta_id: g.tarjeta_id, mes, monto })
  }

  const toggle = (k: string) => setAbiertos(a => ({ ...a, [k]: !a[k] }))

  if (loading && !data) return <p className="loading">Cargando...</p>
  if (!data) return <BilleteraAlert variant="danger" title="No se pudo cargar el mes">{error}</BilleteraAlert>

  const pctPagado = data.sale > 0 ? Math.min(100, Math.max(0, (data.ya_pagado / data.sale) * 100)) : 0

  return (
    <div className="mes">
      <div className="mes-nav">
        <button type="button" className="mes-flecha" aria-label="Mes anterior" onClick={() => onMes(sumarMeses(mes, -1))}>
          <Chevron dir="left" />
        </button>
        <h2 className="mes-titulo">{nombreMes(mes)}</h2>
        <button type="button" className="mes-flecha" aria-label="Mes siguiente" onClick={() => onMes(sumarMeses(mes, 1))}>
          <Chevron dir="right" />
        </button>
      </div>

      {error && <BilleteraAlert variant="danger" title="Algo no salió">{error}</BilleteraAlert>}

      <section className="mes-card mes-hero" aria-label="Resumen del mes">
        <div className="mes-cuenta">
          <div>
            <div className="mes-label">Entra</div>
            <div className="mes-num mes-num-entra">{fmt(data.entra)}</div>
          </div>
          <div className="mes-op" aria-hidden="true">−</div>
          <div>
            <div className="mes-label">Sale</div>
            <div className="mes-num">{fmt(data.sale)}</div>
          </div>
          <div className="mes-op" aria-hidden="true">=</div>
          <div className={`mes-queda ${data.te_queda < 0 ? 'negativo' : ''}`}>
            <div className="mes-label">Te queda</div>
            <div className="mes-num-queda">{fmt(data.te_queda)}</div>
          </div>
        </div>
        {data.sale > 0 && (
          <div className="mes-progreso">
            <div className="mes-progreso-txt">
              <span><strong>{fmt(data.ya_pagado)}</strong> ya pagado</span>
              <span>
                {data.falta_pagar > 0.5
                  ? <><strong>{fmt(data.falta_pagar)}</strong> falta pagar · {data.pendientes} {data.pendientes === 1 ? 'cosa' : 'cosas'}</>
                  : 'Todo pagado'}
              </span>
            </div>
            <div className="mes-barra" role="img" aria-label={`${Math.round(pctPagado)}% de lo que sale ya está pagado`}>
              <div style={{ width: `${pctPagado}%` }} />
            </div>
          </div>
        )}
        {data.hay_estimados && <p className="mes-nota">Hay montos estimados: se ajustan cuando llega el dato real.</p>}
      </section>

      <div className="mes-cols">
        <section className="mes-card mes-entra" aria-labelledby="mes-entra-t">
          <div className="mes-card-head">
            <h3 id="mes-entra-t">Entra</h3>
            <span className="mes-num-chico mes-num-entra">{fmt(data.entra)}</span>
          </div>
          {data.entra_grupos.length === 0 && <p className="mes-vacio">Todavía no hay ingresos cargados.</p>}
          {data.entra_grupos.map(g => (
            <div key={g.grupo}>
              <div className="mes-row"><span className="mes-row-nombre">{g.grupo}</span><span className="mes-monto">{fmt(g.total)}</span></div>
              {g.items.map(i => (
                <div className="mes-sub" key={i.id}>
                  <span>{i.descripcion}{i.estimado && <span className="mes-est"> · estimado</span>}</span>
                  {editIngreso?.id === i.id ? (
                    <span className="mes-inline">
                      <label className="sr-only" htmlFor={`ing-${i.id}`}>Monto de {i.descripcion}</label>
                      <input id={`ing-${i.id}`} className="mes-input" inputMode="decimal" autoFocus value={editIngreso.monto}
                        onChange={e => setEditIngreso({ id: i.id, monto: e.target.value })}
                        onKeyDown={e => { if (e.key === 'Escape') setEditIngreso(null) }} />
                      <button type="button" className="mes-btn mes-btn-pri" disabled={ocupado === `ing-${i.id}`}
                        onClick={() => {
                          const m = parseMonto(editIngreso.monto)
                          if (m == null) return
                          setEditIngreso(null)
                          accion(`ing-${i.id}`, `/api/movements?id=${i.id}`, 'PATCH', { monto: m })
                        }}>Guardar</button>
                    </span>
                  ) : (
                    <button type="button" className="mes-monto-btn" title="Editar monto"
                      onClick={() => setEditIngreso({ id: i.id, monto: String(Math.round(i.monto)) })}>
                      {fmt(i.monto)}
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
          <div className="mes-pie">
            {nuevoIngreso ? (
              <div className="mes-form">
                <label>Descripción
                  <input className="mes-input" value={nuevoIngreso.descripcion} autoFocus
                    onChange={e => setNuevoIngreso({ ...nuevoIngreso, descripcion: e.target.value })} />
                </label>
                <label>Monto
                  <input className="mes-input" inputMode="decimal" value={nuevoIngreso.monto}
                    onChange={e => setNuevoIngreso({ ...nuevoIngreso, monto: e.target.value })} />
                </label>
                <label>Tipo
                  <select className="mes-input" value={nuevoIngreso.grupo}
                    onChange={e => setNuevoIngreso({ ...nuevoIngreso, grupo: e.target.value })}>
                    <option value="Sueldo">Sueldo</option>
                    <option value="Cuotas familia">Cuotas familia</option>
                    <option value="Otros ingresos">Otro ingreso</option>
                  </select>
                </label>
                <div className="mes-form-btns">
                  <button type="button" className="mes-btn mes-btn-sec" onClick={() => setNuevoIngreso(null)}>Cancelar</button>
                  <button type="button" className="mes-btn mes-btn-pri" disabled={ocupado === 'ing-nuevo'}
                    onClick={() => {
                      const m = parseMonto(nuevoIngreso.monto)
                      if (m == null || !nuevoIngreso.descripcion.trim()) return
                      const body = { tipo: 'ingreso', descripcion: nuevoIngreso.descripcion.trim(), monto: m, mes, grupo: nuevoIngreso.grupo }
                      setNuevoIngreso(null)
                      accion('ing-nuevo', '/api/movements', 'POST', body)
                    }}>Agregar</button>
                </div>
              </div>
            ) : (
              <button type="button" className="mes-btn mes-btn-sec mes-btn-ancho"
                onClick={() => setNuevoIngreso({ descripcion: '', monto: '', grupo: 'Sueldo' })}>+ Agregar ingreso</button>
            )}
          </div>
        </section>

        <section className="mes-card mes-sale" aria-labelledby="mes-sale-t">
          <div className="mes-card-head">
            <h3 id="mes-sale-t">Sale</h3>
            <span className="mes-num-chico">{fmt(data.sale)}</span>
          </div>
          {data.sale_grupos.length === 0 && <p className="mes-vacio">Nada para pagar este mes.</p>}
          {data.sale_grupos.map(g => {
            const abierto = !!abiertos[g.grupo]
            const plural = g.tipo === 'prestamo'
            const mostrarPago = g.tipo === 'tarjeta' && (g.estado !== 'pagado' || corrigiendo[g.grupo])
            const subt = g.tipo === 'tarjeta'
              ? (g.estado === 'pagado'
                ? `Pagaste ${fmt(g.monto_pagado ?? g.total)}${g.fecha_pago ? ` el ${g.fecha_pago.slice(8, 10)}/${g.fecha_pago.slice(5, 7)}` : ''}`
                : `Cargado: ${g.items.length} ${g.items.length === 1 ? 'consumo' : 'consumos'}`)
              : g.tipo === 'alquiler' ? 'Se paga del 1 al 10'
              : g.tipo === 'prestamo' ? 'Débito automático'
              : ''
            return (
              <div key={g.grupo} className={abierto ? 'mes-grupo abierto' : 'mes-grupo'}>
                <button type="button" className="mes-row mes-row-btn" aria-expanded={abierto} onClick={() => toggle(g.grupo)}>
                  <Chevron dir={abierto ? 'down' : 'right'} />
                  <span className="mes-row-nombre">
                    {g.nombre}
                    {subt && <span className="mes-row-sub">{subt}</span>}
                  </span>
                  <Chip estado={g.estado} plural={plural} />
                  <span className="mes-monto">{fmt(g.total)}</span>
                </button>

                {mostrarPago && (
                  <div className="mes-pagar">
                    <label htmlFor={`pago-${g.grupo}`}>¿Cuánto pagaste?</label>
                    <div className="mes-inline">
                      <input id={`pago-${g.grupo}`} className="mes-input" inputMode="decimal"
                        placeholder={String(Math.round(g.monto_pagado ?? g.cargado))}
                        value={montos[g.grupo] ?? ''}
                        onChange={e => setMontos(m => ({ ...m, [g.grupo]: e.target.value }))} />
                      <button type="button" className="mes-btn mes-btn-pri" disabled={ocupado === `g-${g.grupo}`}
                        onClick={() => pagarTarjeta(g)}>
                        {g.estado === 'pagado' ? 'Guardar' : 'Marcar pagada'}
                      </button>
                    </div>
                  </div>
                )}

                {g.tipo === 'alquiler' && g.estado !== 'pagado' && (
                  <div className="mes-pagar">
                    <button type="button" className="mes-btn mes-btn-pri" disabled={ocupado === `g-${g.grupo}`}
                      onClick={() => accion(`g-${g.grupo}`, '/api/alquiler', 'POST', { resource: 'pagar_mes', mes })}>
                      Marcar todo pagado ({fmt(g.falta ?? 0)})
                    </button>
                  </div>
                )}

                {abierto && (
                  <div className="mes-detalle">
                    {g.items.map(i => {
                      const det = detalleItem(i, g)
                      const pendienteItem = g.tipo !== 'tarjeta' && !i.pagado && i.concepto !== 'descuento'
                      return (
                        <div className="mes-sub" key={i.id}>
                          <span>
                            {g.tipo === 'alquiler' && i.concepto ? (CONCEPTO[i.concepto] ?? i.descripcion) : i.descripcion}
                            {det && <span className="mes-det"> · {det}</span>}
                            {i.estimado && <span className="mes-chip mes-chip-pend mes-chip-mini">estimado</span>}
                          </span>
                          <span className="mes-inline">
                            {pendienteItem && (g.tipo === 'prestamo' ? i.cuota_id != null : true) && (
                              <button type="button" className="mes-btn mes-btn-sec mes-btn-chico" disabled={ocupado === `i-${i.id}`}
                                onClick={() => g.tipo === 'prestamo'
                                  ? accion(`i-${i.id}`, '/api/prestamos', 'POST', { resource: 'pagar_cuota', cuota_id: i.cuota_id })
                                  : accion(`i-${i.id}`, '/api/alquiler', 'POST', { resource: 'pagar', id: i.id })}>
                                Pagada
                              </button>
                            )}
                            {g.tipo !== 'tarjeta' && i.pagado && i.concepto !== 'descuento' && g.estado === 'parcial' && (
                              <span className="mes-ok-mini" aria-label="pagado"><Check /></span>
                            )}
                            <span className="mes-monto-sub">{fmt(i.monto)}</span>
                          </span>
                        </div>
                      )
                    })}
                    {g.tipo === 'tarjeta' && (g.sin_detallar ?? 0) > 0 && (
                      <div className="mes-sub mes-sin-detallar">
                        <span>Sin detallar <span className="mes-det">· pagaste más de lo cargado (compras que no llegaron por mail o a mano)</span></span>
                        <span className="mes-monto-sub">{fmt(g.sin_detallar ?? 0)}</span>
                      </div>
                    )}
                    {g.tipo === 'tarjeta' && (g.sin_detallar ?? 0) < 0 && (
                      <div className="mes-sub mes-sin-detallar">
                        <span>Pagaste menos que lo cargado <span className="mes-det">· el resto pasa como financiación o saldo</span></span>
                        <span className="mes-monto-sub">{fmt(-(g.sin_detallar ?? 0))}</span>
                      </div>
                    )}
                    {g.tipo === 'tarjeta' && g.estado === 'pagado' && !corrigiendo[g.grupo] && (
                      <div className="mes-sub">
                        <button type="button" className="mes-link" onClick={() => setCorrigiendo(c => ({ ...c, [g.grupo]: true }))}>
                          Corregir lo que pagué
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </section>
      </div>

      {siguiente && (
        <section className="mes-card mes-adelante" aria-label={`Mirando adelante: ${nombreMes(siguiente.mes)}`}>
          <div>
            <div className="mes-label">Mirando adelante · {nombreMes(siguiente.mes)}</div>
            <p>
              Entran <strong>{fmt(siguiente.entra)}</strong> y ya tenés comprometidos <strong>{fmt(siguiente.sale)}</strong>
              {' '}(cuotas, préstamo, alquiler): te quedarían <strong>{fmt(siguiente.te_queda)}</strong> sin contar lo que gastes de acá a {mesCorto(siguiente.mes)}.
            </p>
          </div>
          <button type="button" className="mes-link" onClick={() => onIr('proximos')}>Ver próximos meses</button>
        </section>
      )}
    </div>
  )
}
