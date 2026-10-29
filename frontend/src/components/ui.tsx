import { Check, Copy, LoaderCircle, X } from 'lucide-react'
import { createPortal } from 'react-dom'
import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
  type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import type { QuoteStatus, Status } from '../types'
import { QUOTE_LABEL, QUOTE_TONE, STATUS_LABEL, STATUS_TONE, type Tone } from '../utils/format'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

type Variant = 'primary' | 'brand' | 'secondary' | 'ghost' | 'danger'
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-ink text-white hover:bg-ink-2 disabled:bg-faint',
  brand: 'bg-brand text-white hover:brightness-110 disabled:opacity-50',
  secondary: 'bg-surface text-ink border border-line hover:border-faint disabled:text-faint',
  ghost: 'text-ink-2 hover:bg-line-soft disabled:text-faint',
  danger: 'bg-surface text-bad border border-line hover:border-bad disabled:opacity-50',
}
const SIZES = { sm: 'h-9 px-3 text-[13px] gap-1.5 sm:h-8', md: 'h-11 px-4 text-sm gap-2 sm:h-9 sm:px-3.5', lg: 'h-12 px-5 text-[15px] gap-2' }

export const buttonCls = (variant: Variant = 'secondary', size: keyof typeof SIZES = 'md', extra?: string) =>
  cx('inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap transition-colors',
    VARIANTS[variant], SIZES[size], extra)

export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof SIZES; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={buttonCls(variant, size, className)}
    >
      {loading && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

const inputCls = 'w-full rounded-md border border-line bg-surface px-3 text-base text-ink placeholder:text-faint sm:text-sm ' +
  'hover:border-faint focus:border-brand focus:outline-none focus:ring-3 focus:ring-brand/15 disabled:bg-canvas'

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputCls, 'h-11 sm:h-9', props.className)} />
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(inputCls, 'py-2 leading-relaxed', props.className)} />
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(inputCls, 'h-11 pr-8 sm:h-9', props.className)} />
}

export function Switch({ checked, onChange, label, disabled }:
  { checked: boolean; onChange: (on: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx('relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50',
        checked ? 'bg-brand' : 'bg-faint')}>
      <span className={cx('inline-block size-4 rounded-full bg-white shadow transition-transform',
        checked ? 'translate-x-[18px]' : 'translate-x-0.5')} />
    </button>
  )
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx('block', className)}>
      <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

const TONES: Record<Tone, string> = {
  neutral: 'bg-line-soft text-ink-2 [--dot:var(--color-faint)]',
  info: 'bg-info-soft text-info [--dot:var(--color-info)]',
  warn: 'bg-warn-soft text-warn [--dot:var(--color-warn)]',
  ok: 'bg-ok-soft text-ok [--dot:var(--color-ok)]',
  bad: 'bg-bad-soft text-bad [--dot:var(--color-bad)]',
  brand: 'bg-brand-soft text-brand [--dot:var(--color-brand)]',
}

export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap', TONES[tone])}>
      <span className="size-1.5 rounded-full bg-(--dot)" aria-hidden />
      {children}
    </span>
  )
}

/** For an employee the billing stages are just "with the studio": they work on designs, not on payment. */
export const StatusPill = ({ status, staff }: { status: Status; staff?: boolean }) =>
  staff && ['payment_pending', 'paid', 'delivered'].includes(status)
    ? <Pill tone="neutral">With the studio</Pill>
    : <Pill tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Pill>
export const QuotePill = ({ status }: { status: QuoteStatus }) => <Pill tone={QUOTE_TONE[status]}>{QUOTE_LABEL[status]}</Pill>

export function Panel({ title, actions, children, className, pad = true }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={cx('rounded-xl border border-line bg-surface', className)}>
      {(title || actions) && (
        <header className="flex min-h-12 flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line-soft px-4 py-2.5 sm:px-5">
          <h2 className="text-[13px] font-semibold text-ink">{title}</h2>
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={pad ? 'p-5' : ''}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] leading-tight font-semibold tracking-[-0.015em] text-ink">{title}</h1>
        {sub && <div className="mt-1 text-sm text-muted">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted" role="status">
      <LoaderCircle className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  )
}

export function ErrorNote({ error }: { error: string | null | undefined }) {
  if (!error) return null
  return <p className="rounded-md bg-bad-soft px-3 py-2 text-[13px] text-bad" role="alert">{error}</p>
}

/** Dialog on desktop, bottom sheet on phones. */
export function Modal({ open, onClose, title, children, footer, wide }:
  { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.querySelector<HTMLElement>('textarea:not([data-noautofocus]), input, select, button[data-autofocus]')?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 sm:items-center sm:p-6" onMouseDown={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
        className={cx('sheet-in max-h-[92dvh] w-full overflow-auto rounded-t-2xl bg-surface shadow-2xl sm:rounded-xl',
          wide ? 'sm:max-w-2xl' : 'sm:max-w-md')}
      >
        <div className="flex items-start justify-between gap-4 px-5 pt-5 sm:px-6">
          <h2 className="text-[17px] font-semibold tracking-[-0.01em]">{title}</h2>
          <button onClick={onClose} className="-m-2 rounded-md p-2 text-muted hover:bg-line-soft" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        <div className="px-5 pt-3 pb-5 sm:px-6">{children}</div>
        {footer && (
          <div className="flex flex-col-reverse gap-2 border-t border-line-soft px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:flex-row sm:justify-end sm:px-6">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

// ---------- toasts ----------

const ToastCtx = createContext<(msg: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const show = useCallback((m: string) => {
    setMsg(m)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setMsg(null), 2600)
  }, [])
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-6 z-[60] flex justify-center px-4">
        {msg && (
          <div className="sheet-in flex items-center gap-2 rounded-lg bg-ink px-4 py-2.5 text-sm text-white shadow-lg">
            <Check className="size-4 text-ok-soft" aria-hidden /> {msg}
          </div>
        )}
      </div>
    </ToastCtx.Provider>
  )
}

export function CopyButton({ text, label = 'Copy', copied = 'Copied', size = 'sm', variant = 'secondary', className, onCopied }:
  { text: string; label?: string; copied?: string; size?: 'sm' | 'md'; variant?: Variant; className?: string; onCopied?: () => void }) {
  const toast = useToast()
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const t = document.createElement('textarea')
      t.value = text
      document.body.appendChild(t)
      t.select()
      document.execCommand('copy')
      t.remove()
    }
    toast(copied)
    onCopied?.()
  }
  return (
    <Button size={size} variant={variant} onClick={copy} className={className}>
      <Copy className="size-3.5" aria-hidden /> {label}
    </Button>
  )
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0 px-5 py-4">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-1 text-[22px] leading-tight font-semibold tracking-[-0.02em] tabular-nums text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  )
}
