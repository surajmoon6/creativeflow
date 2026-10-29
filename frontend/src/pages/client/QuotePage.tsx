import { CircleCheck, CircleX, Clock, Printer } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { DownloadButtons, QuoteDocument } from '../../components/QuoteDocument'
import { Button, ErrorNote, Modal, Spinner, Textarea } from '../../components/ui'
import { api, ApiError } from '../../services/api'
import type { ClientQuote } from '../../types'
import { date, money } from '../../utils/format'
import { BrandMark, LinkError, useBrandColor } from './Portal'

/** The client's private quotation page: read it, then accept or decline. Built for phones first. */
export default function QuotePage() {
  const { token = '' } = useParams()
  const [q, setQ] = useState<ClientQuote | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [modal, setModal] = useState<'accept' | 'decline' | null>(null)

  // Only the first load counts as a view; later refreshes are quiet.
  const load = useCallback(async (quiet: boolean) => {
    try {
      const next = await api.get<ClientQuote>(`/api/q/${token}${quiet ? '?quiet=1' : ''}`)
      setQ((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
      setError(null)
    } catch (e) {
      if (!quiet) setError(e as ApiError)
    }
  }, [token])
  useEffect(() => { load(false) }, [load])
  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') load(true) }
    document.addEventListener('visibilitychange', onVisible)
    const t = window.setInterval(onVisible, 20000)
    return () => { document.removeEventListener('visibilitychange', onVisible); window.clearInterval(t) }
  }, [load])

  useBrandColor(q?.document.brand.color)
  useEffect(() => { if (q) document.title = `Quotation ${q.document.number} — ${q.document.brand.name}` }, [q])

  if (error) return <LinkError error={error} />
  if (!q) return <Spinner />
  const doc = q.document
  const b = doc.brand

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="no-print border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between gap-4 px-4 sm:px-6">
          <BrandMark brand={b} />
          <span className="text-[13px] text-muted tabular-nums">Quotation #{doc.number}</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pt-6 pb-36 sm:px-6 sm:pt-10">
        <div className="no-print">
          <p className="text-[13px] text-muted">For {q.client_name}</p>
          <h1 className="mt-0.5 text-[26px] leading-[1.15] font-semibold tracking-[-0.02em] text-ink sm:text-[32px]">{doc.title}</h1>
          <p className="mt-1 text-sm text-ink-2">Total <b className="font-semibold text-ink">{money(doc.totals.total)}</b>, valid until {date(doc.valid_until)}</p>
          <Banner q={q} />
        </div>

        <div className="mt-6"><QuoteDocument doc={doc} /></div>

        <div className="no-print mt-4 flex flex-wrap items-center justify-end gap-2">
          <DownloadButtons base={`/api/q/${token}/download`} />
          <Button size="sm" variant="ghost" onClick={() => window.print()}><Printer className="size-3.5" /> Print</Button>
        </div>
      </main>

      {q.can_respond && (
        <div className="no-print fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:justify-end sm:px-6">
            <span className="mr-auto hidden text-sm text-muted sm:block">Happy with this quote?</span>
            <Button size="lg" className="flex-1 sm:flex-none" onClick={() => setModal('decline')}>Decline</Button>
            <Button size="lg" variant="brand" className="flex-1 sm:flex-none" onClick={() => setModal('accept')}>Accept quote</Button>
          </div>
        </div>
      )}

      <footer className="no-print mx-auto max-w-3xl px-4 pb-10 text-xs text-muted sm:px-6">
        {b.name}
        {b.email && <> — <a className="underline-offset-2 hover:underline" href={`mailto:${b.email}`}>{b.email}</a></>}
        {b.phone && <> — <a className="underline-offset-2 hover:underline" href={`tel:${b.phone.replace(/\s/g, '')}`}>{b.phone}</a></>}
      </footer>

      <Reply mode={modal} token={token} total={doc.totals.total} onClose={() => setModal(null)}
        onDone={(next) => { setQ(next); setModal(null); window.scrollTo({ top: 0, behavior: 'smooth' }) }} />
    </div>
  )
}

function Banner({ q }: { q: ClientQuote }) {
  const note = q.response_note && <q className="mt-1 block text-ink-2 italic">{q.response_note}</q>
  if (q.status === 'accepted') {
    return (
      <Box tone="ok" icon={<CircleCheck className="size-5 text-ok" aria-hidden />} title="Quote accepted">
        Thank you. {q.document.brand.name} will get in touch to start the work.{note}
      </Box>
    )
  }
  if (q.status === 'declined') {
    return <Box tone="bad" icon={<CircleX className="size-5 text-bad" aria-hidden />} title="Quote declined">
      If you change your mind, just contact {q.document.brand.name}.{note}</Box>
  }
  if (q.status === 'expired') {
    return <Box tone="warn" icon={<Clock className="size-5 text-warn" aria-hidden />} title="This quote has expired">
      It was valid until {date(q.document.valid_until)}. Please contact {q.document.brand.name} for an updated quote.</Box>
  }
  return null
}

function Box({ icon, title, children, tone }: { icon: React.ReactNode; title: string; children: React.ReactNode; tone: 'ok' | 'bad' | 'warn' }) {
  const bg = tone === 'ok' ? 'bg-ok-soft' : tone === 'bad' ? 'bg-bad-soft' : 'bg-warn-soft'
  return (
    <div className={`mt-5 rounded-xl p-4 ${bg}`}>
      <h2 className="flex items-center gap-2 font-semibold text-ink">{icon}{title}</h2>
      <div className="mt-1 text-sm text-ink-2">{children}</div>
    </div>
  )
}

function Reply({ mode, token, total, onClose, onDone }:
  { mode: 'accept' | 'decline' | null; token: string; total: number; onClose: () => void; onDone: (q: ClientQuote) => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const accept = mode === 'accept'
  const send = async () => {
    if (!mode) return
    setBusy(true); setErr(null)
    try {
      onDone(await api.post<ClientQuote>(`/api/q/${token}/${mode}`, { note }))
      setNote('')
    } catch (e) {
      setErr((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={mode !== null} onClose={onClose} title={accept ? 'Accept this quote?' : 'Decline this quote?'}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant={accept ? 'brand' : 'primary'} loading={busy} onClick={send}>{accept ? `Accept ${money(total)}` : 'Decline quote'}</Button>
      </>}>
      <p className="text-ink-2">
        {accept ? 'By accepting, you agree to the prices and terms on this quote. The studio will contact you to start.'
          : 'The studio will be told. You can add a reason if you like.'}
      </p>
      <div className="mt-3">
        <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000}
          placeholder={accept ? 'Message to the studio (optional)' : 'Reason (optional)'} aria-label="Message" />
      </div>
      <div className="mt-3"><ErrorNote error={err} /></div>
    </Modal>
  )
}
