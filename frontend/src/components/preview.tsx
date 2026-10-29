import { ChevronLeft, ChevronRight, Maximize2, X, ZoomIn, ZoomOut } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { CLIENT_STEPS, clientStepIndex } from '../utils/format'
import type { Status } from '../types'
import { buttonCls, cx } from './ui'

/** Brief → Design → Review → Approval → Payment → Delivery */
export function LifecycleRail({ status }: { status: Status }) {
  const current = clientStepIndex(status)
  return (
    <ol className="grid grid-cols-6 gap-1.5" aria-label="Project progress">
      {CLIENT_STEPS.map((step, i) => {
        const done = i < current
        const active = i === current
        return (
          <li key={step} className="min-w-0" aria-current={active ? 'step' : undefined}>
            <div className={cx('h-1 rounded-full', done ? 'bg-ink' : active ? 'bg-brand' : 'bg-line')} />
            <div className={cx('mt-2 truncate text-[11px] sm:text-xs',
              done ? 'text-ink-2' : active ? 'font-semibold text-ink' : 'text-faint')}>
              {step}
              <span className="sr-only">{done ? ' (done)' : active ? ' (current)' : ''}</span>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

const stop = (e: React.SyntheticEvent) => e.preventDefault()

/** The creative on a neutral mat with printer's crop marks. Click to open the zoom viewer. */
export function PreviewStage({ pageUrl, pages, alt, caption, watermarked = true }:
  { pageUrl: (page: number) => string; pages: number; alt: string; caption?: React.ReactNode; watermarked?: boolean }) {
  const [page, setPage] = useState(1)
  const [zoom, setZoom] = useState(false)
  // "Loaded" and "failed" belong to one exact URL, so there is no reset step for a cached load to race with.
  const [loadedSrc, setLoadedSrc] = useState('')
  const [failedSrc, setFailedSrc] = useState('')
  const [attempt, setAttempt] = useState(0)
  const first = pageUrl(1) // callers pass a new function every render; the URL string is the stable identity
  useEffect(() => { setPage(1) }, [first])
  const base = pageUrl(page)
  const src = attempt ? `${base}${base.includes('?') ? '&' : '?'}t=${attempt}` : base
  const loaded = loadedSrc === src
  return (
    <figure className="m-0">
      <div className="flex justify-center rounded-xl bg-stage px-5 py-6 sm:px-14 sm:py-14">
        <div className="crop-stage">
          <span className="crop tl" /><span className="crop tr" /><span className="crop bl" /><span className="crop br" />
          {failedSrc === src ? (
            <div className="flex min-h-60 min-w-50 flex-col items-center justify-center gap-3 px-6 text-center text-sm text-ink-2">
              <span>The preview couldn't load.</span>
              <button type="button" onClick={() => setAttempt((a) => a + 1)} className={buttonCls('secondary', 'sm')}>Try again</button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setZoom(true)}
              className="group relative block cursor-zoom-in"
              aria-label="Open preview full screen"
            >
              <img
                src={src}
                alt={pages > 1 ? `${alt}, page ${page} of ${pages}` : alt}
                onLoad={() => setLoadedSrc(src)}
                onError={() => setFailedSrc(src)}
                onContextMenu={stop}
                onDragStart={stop}
                draggable={false}
                className={cx('no-save block max-h-[62dvh] w-auto max-w-full bg-surface shadow-[0_1px_2px_rgba(21,23,28,.08),0_12px_32px_-12px_rgba(21,23,28,.28)] transition-opacity',
                  loaded ? 'opacity-100' : 'opacity-0')}
                style={{ minHeight: loaded ? undefined : 240, minWidth: loaded ? undefined : 200 }}
              />
              <span className="absolute right-2 bottom-2 rounded-md bg-ink/70 p-1.5 text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                <Maximize2 className="size-4" aria-hidden />
              </span>
            </button>
          )}
        </div>
      </div>
      {(pages > 1 || caption) && (
        <figcaption className="mt-3 flex items-center justify-between gap-3">
          <div className="min-w-0 text-[13px] text-muted">{caption}</div>
          {pages > 1 && <Pager page={page} pages={pages} setPage={setPage} />}
        </figcaption>
      )}
      {zoom && <ZoomViewer src={base} alt={alt} watermarked={watermarked} onClose={() => setZoom(false)}
        pager={pages > 1 ? <Pager page={page} pages={pages} setPage={setPage} dark /> : null} />}
    </figure>
  )
}

function Pager({ page, pages, setPage, dark }: { page: number; pages: number; setPage: (n: number) => void; dark?: boolean }) {
  const btn = cx('rounded-md p-2.5 disabled:opacity-30 sm:p-1.5', dark ? 'text-white hover:bg-white/10' : 'text-ink-2 hover:bg-line-soft')
  return (
    <div className={cx('flex shrink-0 items-center gap-1 text-[13px] tabular-nums', dark ? 'text-white' : 'text-ink-2')}>
      <button className={btn} disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft className="size-4" /></button>
      <span>Page {page} of {pages}</span>
      <button className={btn} disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight className="size-4" /></button>
    </div>
  )
}

function ZoomViewer({ src, alt, onClose, pager, watermarked }: { src: string; alt: string; onClose: () => void; pager: React.ReactNode; watermarked: boolean }) {
  const [scale, setScale] = useState(1)
  const [fit, setFit] = useState<{ w: number } | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const img = useRef<HTMLImageElement>(null)

  const measure = useCallback(() => {
    const b = box.current, i = img.current
    if (!b || !i || !i.naturalWidth) return
    const ratio = i.naturalWidth / i.naturalHeight
    setFit({ w: Math.min(b.clientWidth - 32, (b.clientHeight - 32) * ratio) })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === '+' || e.key === '=') setScale((s) => Math.min(4, s + 0.5))
      if (e.key === '-') setScale((s) => Math.max(1, s - 0.5))
    }
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', measure)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', measure)
      document.body.style.overflow = prev
    }
  }, [onClose, measure])
  useEffect(() => { setScale(1) }, [src])

  const ctrl = 'flex size-11 items-center justify-center rounded-md text-white hover:bg-white/10 disabled:opacity-30'
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#101114]" role="dialog" aria-modal="true" aria-label="Preview">
      <div className="flex items-center justify-between gap-2 px-3 py-2 text-white">
        <div className="flex items-center gap-1">
          <button className={ctrl} onClick={() => setScale((s) => Math.max(1, s - 0.5))} disabled={scale <= 1} aria-label="Zoom out"><ZoomOut className="size-5" /></button>
          <span className="w-12 text-center text-[13px] tabular-nums">{Math.round(scale * 100)}%</span>
          <button className={ctrl} onClick={() => setScale((s) => Math.min(4, s + 0.5))} disabled={scale >= 4} aria-label="Zoom in"><ZoomIn className="size-5" /></button>
        </div>
        {pager}
        <button className={ctrl} onClick={onClose} aria-label="Close preview"><X className="size-5" /></button>
      </div>
      <div ref={box} className="relative flex-1 overflow-auto" style={{ touchAction: 'pan-x pan-y pinch-zoom' }}>
        <div className="flex min-h-full min-w-full items-center justify-center p-4" style={{ width: fit ? fit.w * scale + 32 : undefined }}>
          <img
            ref={img}
            src={src}
            alt={alt}
            onLoad={measure}
            onContextMenu={stop}
            onDragStart={stop}
            draggable={false}
            onDoubleClick={() => setScale((s) => (s > 1 ? 1 : 2))}
            className="no-save m-auto block max-w-none"
            style={{ width: fit ? fit.w * scale : undefined, visibility: fit ? 'visible' : 'hidden' }}
          />
        </div>
      </div>
      {watermarked && <p className="px-4 py-2 text-center text-xs text-white/50">Client review copy</p>}
    </div>
  )
}
