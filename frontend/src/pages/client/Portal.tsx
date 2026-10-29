import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom'
import { LifecycleRail } from '../../components/preview'
import { Spinner, cx } from '../../components/ui'
import { api, ApiError } from '../../services/api'
import type { Brand, ClientView } from '../../types'

export interface PortalCtx {
  view: ClientView
  token: string
  refresh: () => Promise<void>
  setView: (v: ClientView) => void
}
export const usePortal = () => useOutletContext<PortalCtx>()

export function useBrandColor(color?: string) {
  useEffect(() => {
    if (color) document.documentElement.style.setProperty('--brand', color)
  }, [color])
}

/** `large` is for the head of a document (quote, invoice); the default fits a navigation bar. */
export function BrandMark({ brand, large }: { brand: Brand; large?: boolean }) {
  const mark = brand.has_logo ? (
    <img src="/api/brand/logo" alt={brand.name} className={large ? 'h-16 w-auto max-w-[240px] object-contain' : 'h-7 w-auto max-w-[160px] object-contain'} />
  ) : (
    <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">{brand.name}</span>
  )
  // On a document, our software's name sits under the studio's own brand.
  return large && brand.name !== 'CreativeFlow Studio'
    ? <div>{mark}<div className="mt-1 text-xs text-muted">CreativeFlow Studio</div></div>
    : mark
}

export default function Portal() {
  const { token = '' } = useParams()
  const [view, setView] = useState<ClientView | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  // Only the first load counts as a view; later refreshes are quiet so the studio's view count stays honest.
  const load = useCallback(async (quiet: boolean) => {
    try {
      const next = await api.get<ClientView>(`/api/r/${token}${quiet ? '?quiet=1' : ''}`)
      setView((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
      setError(null)
    } catch (e) {
      // A failed background refresh must not replace a page the client is already looking at.
      if (!quiet) setError(e as ApiError)
    }
  }, [token])
  const refresh = useCallback(() => load(true), [load])

  useEffect(() => { load(false) }, [load])
  // Pick up a new version, an approval or a watermark change when the client comes back to this tab.
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisible)
    const t = window.setInterval(onVisible, 15000)
    return () => { document.removeEventListener('visibilitychange', onVisible); window.clearInterval(t) }
  }, [refresh])
  useBrandColor(view?.brand.color)
  useEffect(() => {
    if (view) document.title = `${view.name} — ${view.brand.name}`
  }, [view])

  if (error) return <LinkError error={error} />
  if (!view) return <Spinner />

  const tabs = [
    { to: '', label: view.deliverables.length > 1 ? 'Designs' : 'Creative', show: true },
    { to: 'advance', label: 'Advance', show: !!view.advance },
    { to: 'invoice', label: 'Invoice', show: !!view.invoice },
    { to: 'delivery', label: 'Final files', show: !!view.delivery },
  ].filter((t) => t.show)

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="no-print border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <BrandMark brand={view.brand} />
          <span className="text-[13px] text-muted tabular-nums">Project #{view.code}</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 pt-6 pb-32 sm:px-6 sm:pt-10">
        <div className="no-print">
          <p className="text-[13px] text-muted">{view.client_name}</p>
          <h1 className="mt-0.5 text-[26px] leading-[1.15] font-semibold tracking-[-0.02em] text-ink sm:text-[32px]">{view.name}</h1>
          <p className="mt-1 text-sm text-ink-2">
            {view.project_type}
            {view.width && view.height ? <span className="text-muted"> — {view.width} × {view.height}</span> : null}
          </p>
          <div className="mt-6 max-w-2xl"><LifecycleRail status={view.status} /></div>

          {tabs.length > 1 && (
            <nav className="mt-8 flex gap-1 border-b border-line" aria-label="Project sections">
              {tabs.map((t) => (
                <NavLink key={t.to} to={t.to} end
                  className={({ isActive }) => cx('-mb-px border-b-2 px-3 py-2.5 text-sm font-medium',
                    isActive ? 'border-ink text-ink' : 'border-transparent text-muted hover:text-ink')}>
                  {t.label}
                </NavLink>
              ))}
            </nav>
          )}
        </div>
        <div className={tabs.length > 1 ? 'mt-6' : 'mt-8'}>
          <Outlet context={{ view, token, refresh, setView } satisfies PortalCtx} />
        </div>
      </main>

      <footer className="no-print mx-auto max-w-5xl px-4 pb-10 text-xs text-muted sm:px-6">
        {view.brand.name}
        {view.brand.email && <> — <a className="underline-offset-2 hover:underline" href={`mailto:${view.brand.email}`}>{view.brand.email}</a></>}
        {view.brand.phone && <> — <a className="underline-offset-2 hover:underline" href={`tel:${view.brand.phone.replace(/\s/g, '')}`}>{view.brand.phone}</a></>}
      </footer>
    </div>
  )
}

export function LinkError({ error }: { error: ApiError }) {
  const [brand, setBrand] = useState<Brand | null>(null)
  useEffect(() => { api.get<Brand>('/api/brand').then(setBrand).catch(() => {}) }, [])
  useBrandColor(brand?.color)
  const title = error.code === 'expired' ? 'This link has expired'
    : error.code === 'revoked' ? 'This link is no longer active'
    : error.status === 404 ? 'Link not found' : 'Something went wrong'
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-5xl items-center px-4 sm:px-6">{brand && <BrandMark brand={brand} />}</div>
      </header>
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 pb-24">
        <div className="crop-stage mb-8 self-start">
          <span className="crop tl" /><span className="crop tr" /><span className="crop bl" /><span className="crop br" />
          <div className="size-14 bg-stage" />
        </div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">{title}</h1>
        <p className="mt-2 text-ink-2">{error.message}</p>
        {brand && (brand.email || brand.phone) && (
          <p className="mt-6 text-sm text-muted">
            Contact {brand.name}{' '}
            {brand.phone && <a className="text-ink underline underline-offset-2" href={`tel:${brand.phone.replace(/\s/g, '')}`}>{brand.phone}</a>}
            {brand.phone && brand.email && ' or '}
            {brand.email && <a className="text-ink underline underline-offset-2" href={`mailto:${brand.email}`}>{brand.email}</a>}
          </p>
        )}
      </main>
    </div>
  )
}
