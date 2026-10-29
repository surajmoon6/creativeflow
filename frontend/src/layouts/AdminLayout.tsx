import { Activity, Bell, CalendarDays, CreditCard, FileText, Files, FolderKanban, LayoutDashboard, LogOut, Menu, Receipt, Settings, UserCog, Users, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Spinner, cx } from '../components/ui'
import { api, setCsrf } from '../services/api'
import type { Settings as SettingsT } from '../types'
import { relative } from '../utils/format'

interface Me { user: { id: number; name: string; email: string; role: 'admin' | 'staff' | 'client' }; csrf: string }
interface Notif { id: number; event: string; message: string; read: boolean; created_at: string; project_id: number | null; quote_id: number | null; client_id?: number | null }

const AdminCtx = createContext<{ settings: SettingsT | null; reloadSettings: () => void; bump: () => void; isStaff: boolean }>({
  settings: null, reloadSettings: () => {}, bump: () => {}, isStaff: false,
})
export const useAdmin = () => useContext(AdminCtx)

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/projects', label: 'Projects', icon: FolderKanban },
  { to: '/calendar', label: 'Calendar', icon: CalendarDays },
  { to: '/quotes', label: 'Quotes', icon: FileText },
  { to: '/clients', label: 'Clients', icon: Users },
  { to: '/invoices', label: 'Invoices', icon: Receipt },
  { to: '/payments', label: 'Payments', icon: CreditCard },
  { to: '/files', label: 'Files', icon: Files },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/team', label: 'Team', icon: UserCog },
  { to: '/settings', label: 'Settings', icon: Settings },
]
// An employee sees only the work on the clients assigned to them.
const STAFF_NAV = [{ to: '/projects', label: 'My work', icon: FolderKanban }, { to: '/calendar', label: 'Calendar', icon: CalendarDays }]

export default function AdminLayout() {
  const nav = useNavigate()
  const loc = useLocation()
  const [me, setMe] = useState<Me | null>(null)
  const [settings, setSettings] = useState<SettingsT | null>(null)
  const [toConfirm, setToConfirm] = useState(0)
  const [calAttention, setCalAttention] = useState(0)
  const [notifs, setNotifs] = useState<{ unread: number; items: Notif[] }>({ unread: 0, items: [] })
  const [menu, setMenu] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    api.get<Me>('/api/auth/me').then((m) => { setCsrf(m.csrf); if (m.user.role === 'client') nav('/c', { replace: true }); else setMe(m) })
      .catch(() => nav('/login', { replace: true, state: { from: loc.pathname } }))
    const out = () => nav('/login', { replace: true })
    window.addEventListener('cf:logout', out)
    return () => window.removeEventListener('cf:logout', out)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isStaff = me?.user.role === 'staff'
  const reloadSettings = useCallback(() => {
    // Employees can't read the settings (prices, UPI); they only get the public brand.
    const url = isStaff ? '/api/brand' : '/api/settings'
    api.get<Record<string, unknown>>(url).then((s) => {
      const color = String(s.brand_color ?? s.color)
      setSettings(isStaff ? { brand_name: s.name, brand_color: color } as SettingsT : s as SettingsT)
      document.documentElement.style.setProperty('--brand', color)
    }).catch(() => {})
  }, [isStaff])

  useEffect(() => {
    if (!me) return
    reloadSettings()
  }, [me, reloadSettings])

  // Employees never land on owner pages, even by typing the address.
  useEffect(() => {
    if (isStaff && !loc.pathname.startsWith('/projects') && !loc.pathname.startsWith('/calendar')) nav('/projects', { replace: true })
    if (isStaff && /^\/projects\/(new|\d+\/edit)/.test(loc.pathname)) nav('/projects', { replace: true })
  }, [isStaff, loc.pathname, nav])

  useEffect(() => {
    if (!me || isStaff) return
    const load = () => {
      api.get<unknown[]>('/api/payments?status=submitted').then((p) => setToConfirm(p.length)).catch(() => {})
      api.get<typeof notifs>('/api/notifications').then(setNotifs).catch(() => {})
    }
    load()
    const t = window.setInterval(load, 12000)
    return () => window.clearInterval(t)
  }, [me, isStaff, tick, loc.pathname])

  // The team (owner and employees) sees how many clients are waiting on them, on the Calendar link.
  useEffect(() => {
    if (!me) return
    const load = () => api.get<{ count: number }>('/api/calendar/attention').then((a) => setCalAttention(a.count)).catch(() => {})
    load()
    const t = window.setInterval(load, 15000)
    return () => window.clearInterval(t)
  }, [me, loc.pathname])

  useEffect(() => setMenu(false), [loc.pathname])

  if (!me) return <Spinner />

  const logout = async () => {
    await api.post('/api/auth/logout').catch(() => {})
    nav('/login', { replace: true })
  }

  const sidebar = (
    <div className="flex h-full flex-col">
      <Link to="/" className="flex h-14 items-center gap-2.5 px-5">
        <svg viewBox="0 0 32 32" className="size-6" aria-hidden><rect width="32" height="32" rx="8" fill="#15171C" /><path d="M9 9h4M9 9v4M23 9h-4M23 9v4M9 23h4M9 23v-4M23 23h-4M23 23v-4" stroke="#fff" strokeWidth="2" strokeLinecap="round" /></svg>
        <span className="font-semibold tracking-[-0.01em]">CreativeFlow</span>
      </Link>
      <nav className="flex-1 space-y-0.5 px-3 py-2" aria-label="Main">
        {(isStaff ? STAFF_NAV : NAV).map(({ to, label, icon: Icon, end }: { to: string; label: string; icon: typeof Bell; end?: boolean }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) => cx('flex h-11 items-center lg:h-9 gap-2.5 rounded-md px-2.5 text-sm',
              isActive ? 'bg-line-soft font-medium text-ink' : 'text-ink-2 hover:bg-line-soft/60 hover:text-ink')}>
            <Icon className="size-4 text-muted" aria-hidden />
            <span className="flex-1">{label}</span>
            {to === '/calendar' && calAttention > 0 && (
              <span className="rounded-full bg-info px-1.5 text-xs font-medium text-white tabular-nums" title="Clients are waiting on your team">{calAttention}</span>
            )}
            {to === '/payments' && toConfirm > 0 && (
              <span className="rounded-full bg-warn-soft px-1.5 text-xs font-medium text-warn tabular-nums" title="Payments to confirm">{toConfirm}</span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-line-soft p-3">
        <div className="px-2.5 pb-2">
          <div className="truncate text-[13px] font-medium">{settings?.brand_name ?? ''}</div>
          <div className="truncate text-xs text-muted">{me.user.email}</div>
        </div>
        <button onClick={logout} className="flex h-9 w-full items-center gap-2.5 rounded-md px-2.5 text-sm text-ink-2 hover:bg-line-soft">
          <LogOut className="size-4 text-muted" aria-hidden /> Sign out
        </button>
      </div>
    </div>
  )

  return (
    <AdminCtx.Provider value={{ settings, reloadSettings, bump: () => setTick((t) => t + 1), isStaff }}>
      <div className="min-h-dvh lg:pl-60">
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 border-r border-line bg-surface lg:block">{sidebar}</aside>
        {menu && (
          <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setMenu(false)}>
            <div className="absolute inset-0 bg-ink/30" />
            <aside className="absolute inset-y-0 left-0 w-64 bg-surface shadow-xl" onClick={(e) => e.stopPropagation()}>{sidebar}</aside>
          </div>
        )}
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur sm:px-8">
          <button className="-ml-2 rounded-md p-2.5 hover:bg-line-soft lg:hidden" onClick={() => setMenu(true)} aria-label="Open menu">
            {menu ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
          <div className="flex-1" />
          {!isStaff && <Notifications data={notifs} onRead={() => api.post('/api/notifications/read').then(() => setTick((t) => t + 1))} />}
        </header>
        <main className="mx-auto max-w-[1180px] px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </main>
      </div>
    </AdminCtx.Provider>
  )
}

function Notifications({ data, onRead }: { data: { unread: number; items: Notif[] }; onRead: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => { setOpen(!open); if (!open && data.unread) onRead() }}
        className="relative -mr-1 rounded-md p-2.5 text-ink-2 hover:bg-line-soft" aria-label={`Notifications${data.unread ? `, ${data.unread} unread` : ''}`}>
        <Bell className="size-[18px]" />
        {data.unread > 0 && <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-brand ring-2 ring-canvas" />}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-[min(92vw,360px)] overflow-hidden rounded-xl border border-line bg-surface shadow-xl">
          <div className="border-b border-line-soft px-4 py-3 text-[13px] font-semibold">Notifications</div>
          {data.items.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted">Client activity will show up here.</p>
          ) : (
            <ul className="max-h-96 divide-y divide-line-soft overflow-auto">
              {data.items.map((n) => (
                <li key={n.id}>
                  <Link to={(n.event === 'client_message' || n.event === 'brief_sent') && n.client_id ? `/calendar?client=${n.client_id}` : n.event === 'payment_claimed' && n.client_id ? `/clients/${n.client_id}` : n.project_id ? `/projects/${n.project_id}` : n.quote_id ? `/quotes/${n.quote_id}` : '/'} onClick={() => setOpen(false)}
                    className="flex gap-3 px-4 py-3 hover:bg-canvas">
                    <span className={cx('mt-1.5 size-1.5 shrink-0 rounded-full', n.read ? 'bg-transparent' : 'bg-brand')} />
                    <span className="min-w-0">
                      <span className="block text-sm text-ink">{n.message}</span>
                      <span className="block text-xs text-muted">{relative(n.created_at)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
