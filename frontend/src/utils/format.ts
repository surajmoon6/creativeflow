import type { QuoteStatus, Status } from '../types'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const inrPaise = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Amounts are integer paise. Whole rupees show without decimals; anything else shows both paise digits (₹532.80). */
export const money = (paise: number | null | undefined) => {
  const p = paise ?? 0
  return p % 100 === 0 ? inr.format(p / 100) : inrPaise.format(p / 100)
}
export const toPaise = (rupees: string | number) => Math.round(Number(rupees || 0) * 100)
export const toRupees = (paise: number | null | undefined) => (paise ?? 0) / 100

const asDate = (iso: string) => new Date(iso.length === 10 ? iso + 'T00:00:00' : iso)

export const date = (iso: string | null | undefined) =>
  iso ? asDate(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const shortDate = (iso: string | null | undefined) =>
  iso ? asDate(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'
export const time = (iso: string) => asDate(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
export const dateTime = (iso: string | null | undefined) => (iso ? `${shortDate(iso)}, ${time(iso)}` : '—')

export function relative(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = asDate(iso)
  const mins = Math.round((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min ago`
  const today = new Date(); today.setHours(0, 0, 0, 0)
  if (d >= today) return `Today, ${time(iso)}`
  const yest = new Date(today); yest.setDate(today.getDate() - 1)
  if (d >= yest) return 'Yesterday'
  return shortDate(iso)
}

export const bytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 ** 2 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1024 ** 2).toFixed(1)} MB`

export const STATUS_LABEL: Record<Status, string> = {
  brief_received: 'Brief received',
  in_design: 'In design',
  review: 'In review',
  revision_requested: 'Changes requested',
  approved: 'Approved',
  finalization: 'Finalization',
  payment_pending: 'Payment pending',
  paid: 'Paid',
  delivered: 'Delivered',
  completed: 'Completed',
}

export type Tone = 'neutral' | 'info' | 'warn' | 'ok' | 'bad' | 'brand'
export const STATUS_TONE: Record<Status, Tone> = {
  brief_received: 'neutral', in_design: 'neutral', review: 'info', revision_requested: 'warn',
  approved: 'brand', finalization: 'brand', payment_pending: 'warn', paid: 'ok', delivered: 'ok', completed: 'neutral',
}

/** Client-facing lifecycle (six steps). */
export const CLIENT_STEPS = ['Brief', 'Design', 'Review', 'Approval', 'Payment', 'Delivery'] as const
export function clientStepIndex(s: Status): number {
  // index of the step currently in progress; steps before it are done
  switch (s) {
    case 'brief_received': return 1
    case 'in_design': return 1
    case 'review': case 'revision_requested': return 2
    case 'approved': case 'finalization': case 'payment_pending': return 4
    case 'paid': case 'delivered': return 5
    case 'completed': return 6
  }
}

export const fileKind = (f: { name: string; mime: string }) => {
  const ext = f.name.split('.').pop()?.toUpperCase() || 'FILE'
  return ext === 'JPEG' ? 'JPG' : ext
}

export const QUOTE_LABEL: Record<QuoteStatus, string> = {
  draft: 'Draft', sent: 'Sent', accepted: 'Accepted', declined: 'Declined', expired: 'Expired',
}
export const QUOTE_TONE: Record<QuoteStatus, Tone> = {
  draft: 'neutral', sent: 'info', accepted: 'ok', declined: 'bad', expired: 'warn',
}

export const waHref = (number: string | null, message: string) =>
  `https://wa.me/${number ?? ''}?text=${encodeURIComponent(message)}`
