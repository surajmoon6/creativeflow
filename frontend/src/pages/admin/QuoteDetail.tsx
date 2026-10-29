import { Copy as CopyIcon, ExternalLink, MessageCircle, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DownloadButtons, QuoteDocument } from '../../components/QuoteDocument'
import { Button, CopyButton, ErrorNote, Field, Input, Modal, Panel, QuotePill, Spinner, Textarea, buttonCls, useToast } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { QuoteDetail as QD } from '../../types'
import { date, dateTime, money, relative, waHref } from '../../utils/format'

export default function QuoteDetail() {
  const { id } = useParams()
  const { data: q, setData, error, loading } = useAsync(() => api.get<QD>(`/api/quotes/${id}`), [id], { poll: 8000 })
  const { bump } = useAdmin()
  if (loading) return <Spinner />
  if (error || !q) return <ErrorNote error={error?.message} />
  const update = (next: QD) => { setData(next); bump() }

  return (
    <>
      <Header q={q} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-6">
          <NextStep q={q} onChange={update} />
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[13px] font-semibold text-ink">The quote, as your client sees it</h2>
              <DownloadButtons base={`/api/quotes/${q.id}/download`} />
            </div>
            <QuoteDocument doc={q.document} />
          </div>
        </div>
        <div className="min-w-0 space-y-6">
          <Panel title="Details">
            <dl className="space-y-2.5 text-sm">
              <Row k="Client"><Link to={`/clients/${q.client.id}`} className="hover:underline">{q.client.name}</Link></Row>
              <Row k="Total">{money(q.total)}</Row>
              <Row k="Valid until">{date(q.valid_until)}</Row>
              <Row k="Opened">{q.views ? `${q.views} time${q.views === 1 ? '' : 's'}, last ${relative(q.last_viewed_at).toLowerCase()}` : 'Not yet'}</Row>
              {q.project && <Row k="Project"><Link to={`/projects/${q.project.id}`} className="font-medium underline underline-offset-2">{q.project.code}</Link></Row>}
            </dl>
          </Panel>
          <Panel title="Activity">
            <ol className="relative space-y-4 border-l border-line pl-5">
              {[...q.events].reverse().map((e, i) => (
                <li key={i} className="relative">
                  <span className="absolute top-1.5 -left-[23.5px] size-2 rounded-full bg-ink ring-4 ring-surface" />
                  <div className="text-sm text-ink">{e.text}</div>
                  <div className="text-xs text-muted">{dateTime(e.at)}</div>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </>
  )
}

const Row = ({ k, children }: { k: string; children: React.ReactNode }) => (
  <div className="grid grid-cols-[100px_1fr] gap-3"><dt className="text-muted">{k}</dt><dd className="min-w-0 break-words">{children}</dd></div>
)

function Header({ q }: { q: QD }) {
  const nav = useNavigate()
  const toast = useToast()
  const [menu, setMenu] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const locked = q.stored_status === 'accepted' || q.stored_status === 'declined'
  const duplicate = async () => {
    setBusy(true)
    try { const c = await api.post<QD>(`/api/quotes/${q.id}/duplicate`); toast(`Copied as ${c.number}`); nav(`/quotes/${c.id}`) }
    catch (e) { alert((e as ApiError).message) } finally { setBusy(false); setMenu(false) }
  }
  const remove = async () => {
    setBusy(true)
    try { await api.del(`/api/quotes/${q.id}`); nav('/quotes') } catch (e) { alert((e as ApiError).message); setBusy(false) }
  }
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
          <Link to="/quotes" className="hover:text-ink hover:underline">Quotations</Link>
          <span className="tabular-nums">{q.number}</span>
        </div>
        <h1 className="mt-1 text-[24px] leading-tight font-semibold tracking-[-0.02em]">{q.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <QuotePill status={q.status} />
          <span className="text-sm font-medium tabular-nums">{money(q.total)}</span>
          <span className="text-[13px] text-muted">for {q.client.name}</span>
        </div>
      </div>
      <div className="relative flex items-center gap-2">
        {!locked && <Link to={`/quotes/${q.id}/edit`} className={buttonCls('secondary')}><Pencil className="size-3.5" /> Edit</Link>}
        <Button onClick={() => setMenu(!menu)} aria-label="More actions"><MoreHorizontal className="size-4" /></Button>
        {menu && (
          <div className="absolute top-12 right-0 z-20 w-56 rounded-lg border border-line bg-surface p-1 shadow-lg sm:top-11">
            <MenuItem onClick={duplicate} disabled={busy}><CopyIcon className="size-3.5" /> Duplicate as new quote</MenuItem>
            {q.stored_status !== 'draft' && (
              <a href={q.share.link} target="_blank" rel="noreferrer" className="flex min-h-11 w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-canvas sm:min-h-0"><ExternalLink className="size-3.5" /> Open client view</a>
            )}
            {q.stored_status === 'draft' && <MenuItem onClick={() => { setMenu(false); setConfirm(true) }}><Trash2 className="size-3.5" /> Delete draft</MenuItem>}
          </div>
        )}
      </div>
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Delete this draft?"
        footer={<><Button onClick={() => setConfirm(false)}>Cancel</Button><Button variant="danger" loading={busy} onClick={remove}>Delete draft</Button></>}>
        <p className="text-ink-2">{q.number} has not been sent, so nothing is lost on the client's side. This can't be undone.</p>
      </Modal>
    </div>
  )
}

const MenuItem = ({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) => (
  <button onClick={onClick} disabled={disabled} className="flex min-h-11 w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-canvas disabled:opacity-50 sm:min-h-0">{children}</button>
)

function ShareButtons({ q, onChange, primary = true }: { q: QD; onChange: (q: QD) => void; primary?: boolean }) {
  // Sharing marks a draft as sent, so the client's link starts working the moment you send it.
  const markSent = () => { api.post<QD>(`/api/quotes/${q.id}/send`).then(onChange).catch(() => {}) }
  return (
    <>
      <a href={waHref(q.share.whatsapp_number, q.share.message)} target="_blank" rel="noreferrer" onClick={markSent}
        className={buttonCls(primary ? 'primary' : 'secondary')}>
        <MessageCircle className="size-4" /> {q.stored_status === 'draft' ? 'Send on WhatsApp' : 'Share again on WhatsApp'}
      </a>
      <CopyButton text={q.share.link} label="Copy link" copied="Link copied" size="md" onCopied={markSent} />
    </>
  )
}

function NextStep({ q, onChange }: { q: QD; onChange: (q: QD) => void }) {
  const nav = useNavigate()
  const [mode, setMode] = useState<'accept' | 'decline' | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try { await fn() } catch (e) { alert((e as ApiError).message) } finally { setBusy(false) }
  }
  const [convertOpen, setConvertOpen] = useState(false)
  const reopen = () => run(async () => onChange(await api.post<QD>(`/api/quotes/${q.id}/status`, { action: 'reopen' })))
  const startPlan = () => run(async () => onChange(await api.post<QD>(`/api/quotes/${q.id}/start-plan`)))

  let title = '', body: React.ReactNode = null, action: React.ReactNode = null
  switch (q.status) {
    case 'draft':
      title = 'Ready to send'
      body = 'Send it on WhatsApp or copy the link. Your client opens a page where they can accept or decline from their phone.'
      action = <ShareButtons q={q} onChange={onChange} />
      break
    case 'sent':
      title = q.views ? `${q.client.name} has opened the quote` : `Waiting for ${q.client.name} to open it`
      body = q.views
        ? `Viewed ${q.views} time${q.views === 1 ? '' : 's'}, last ${relative(q.last_viewed_at).toLowerCase()}. Valid until ${date(q.valid_until)}.`
        : `Sent ${relative(q.sent_at).toLowerCase()}. Valid until ${date(q.valid_until)}.`
      action = <>
        <ShareButtons q={q} onChange={onChange} primary={false} />
        <Button onClick={() => setMode('accept')}>Mark as accepted</Button>
        <Button onClick={() => setMode('decline')}>Mark as declined</Button>
      </>
      break
    case 'accepted':
      title = q.project ? 'Accepted. Project started' : 'Accepted. Start the project'
      body = <>
        {q.responded_at && <>Accepted {relative(q.responded_at).toLowerCase()}. </>}
        {q.response_note && <q className="block border-l-2 border-ok pl-3 text-ink italic">{q.response_note}</q>}
        {q.project && <>Project <Link to={`/projects/${q.project.id}`} className="font-medium underline underline-offset-2">{q.project.code}</Link> was created from this quote.</>}
      </>
      if (q.document.billing === 'monthly') {
        title = q.has_plan ? 'Accepted. Monthly plan started' : 'Accepted. Start the monthly plan'
        body = <>
          {q.responded_at && <>Accepted {relative(q.responded_at).toLowerCase()}. </>}
          {q.has_plan
            ? <>The plan is running. Add sign-ins for their team from the client's page, then plan their posts in the calendar.</>
            : <>This starts {q.client.name}'s monthly plan at {money(q.total)} a month with the deliverables from this quote. Then you can give them a sign-in.</>}
        </>
        action = q.has_plan
          ? <><Link to={`/clients/${q.client_id}`} className={buttonCls('primary')}>Add client sign-ins</Link><Link to={`/calendar?client=${q.client_id}`} className={buttonCls('secondary')}>Open the calendar</Link></>
          : <Button variant="primary" loading={busy} onClick={startPlan}>Start the monthly plan</Button>
        break
      }
      action = q.project
        ? <Link to={`/projects/${q.project.id}`} className={buttonCls('primary')}>Open project {q.project.code}</Link>
        : <Button variant="primary" onClick={() => setConvertOpen(true)}>Create project from this quote</Button>
      break
    case 'declined':
      title = 'Declined'
      body = <>{q.response_note ? <q className="block border-l-2 border-bad pl-3 text-ink italic">{q.response_note}</q> : 'No reason was given.'}</>
      action = <Button loading={busy} onClick={reopen}>Reopen quote</Button>
      break
    case 'expired':
      title = `Expired on ${date(q.valid_until)}`
      body = 'The client can no longer accept it. Edit the quote to extend the date, and the same link works again.'
      action = <Link to={`/quotes/${q.id}/edit`} className={buttonCls('primary')}>Extend the date</Link>
      break
  }
  return (
    <section className={`rounded-xl border bg-surface p-5 ${q.status === 'accepted' && !q.project ? 'border-ok/40' : 'border-line'}`}>
      <h2 className="font-semibold">{title}</h2>
      {body && <div className="mt-1.5 max-w-[68ch] text-sm text-ink-2">{body}</div>}
      {action && <div className="mt-4 flex flex-wrap gap-2">{action}</div>}
      <Record q={q} mode={mode} onClose={() => setMode(null)} onDone={(next) => { onChange(next); setMode(null) }} />
      <ConvertDialog q={q} open={convertOpen} onClose={() => setConvertOpen(false)} onDone={(next, projectId) => { onChange(next); nav(`/projects/${projectId}`) }} />
    </section>
  )
}

function Record({ q, mode, onClose, onDone }: { q: QD; mode: 'accept' | 'decline' | null; onClose: () => void; onDone: (q: QD) => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const go = async () => {
    setBusy(true); setErr(null)
    try { onDone(await api.post<QD>(`/api/quotes/${q.id}/status`, { action: mode, note })); setNote('') }
    catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const accept = mode === 'accept'
  return (
    <Modal open={mode !== null} onClose={onClose} title={accept ? 'Record that it was accepted?' : 'Record that it was declined?'}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={go}>{accept ? 'Mark as accepted' : 'Mark as declined'}</Button></>}>
      <p className="text-ink-2">Use this when {q.client.name} answers by phone or WhatsApp instead of on the quote page.</p>
      <div className="mt-3"><Field label="Note (optional)"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} placeholder={accept ? 'Confirmed on call' : 'Went with another studio'} /></Field></div>
      <div className="mt-3"><ErrorNote error={err} /></div>
    </Modal>
  )
}


/** One design per thing on the quote (several of the same item become "Post (1 of 3)"), mirrored from the server. */
const designTitles = (q: QD) => q.document.items.flatMap((i) =>
  i.quantity > 1 && i.quantity <= 12 ? Array.from({ length: i.quantity }, (_, n) => `${i.description} (${n + 1} of ${i.quantity})`) : [i.description])

function ConvertDialog({ q, open, onClose, onDone }: { q: QD; open: boolean; onClose: () => void; onDone: (q: QD, projectId: number) => void }) {
  const [revisions, setRevisions] = useState(String(q.document.revisions_included))
  const [advance, setAdvance] = useState(String(q.document.advance_percent))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const titles = designTitles(q)
  const pct = Math.min(100, Math.max(0, Number(advance) || 0))
  const go = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.post<{ quote: QD; project_id: number }>(`/api/quotes/${q.id}/convert`, { revisions_included: Number(revisions) || 0, advance_percent: pct })
      onDone(r.quote, r.project_id)
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Start the project" wide
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={go}>Create project</Button></>}>
      <p className="text-ink-2">One project, one link for {q.client.name}. Each design below gets its own preview, revisions and approval.</p>
      <ul className="mt-3 divide-y divide-line-soft rounded-lg border border-line-soft text-sm">
        {titles.map((t, i) => <li key={i} className="px-3 py-2">{t}</li>)}
      </ul>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Revisions for each design"><Input type="number" min={0} max={50} inputMode="numeric" value={revisions} onChange={(e) => setRevisions(e.target.value)} /></Field>
        <Field label="Advance to ask for (%)" hint={pct > 0 ? `${money(Math.round((q.document.totals.total * pct) / 100))} of ${money(q.document.totals.total)}. The client gets a QR to pay it.` : 'No advance will be asked for.'}>
          <Input type="number" min={0} max={100} inputMode="numeric" value={advance} onChange={(e) => setAdvance(e.target.value)} />
        </Field>
      </div>
      <div className="mt-3"><ErrorNote error={err} /></div>
    </Modal>
  )
}
