import { CircleCheck, Clock } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PreviewStage } from '../../components/preview'
import { Button, ErrorNote, Modal, Textarea, buttonCls, cx } from '../../components/ui'
import { api, ApiError } from '../../services/api'
import type { ClientView, Design, DesignStatus, Version } from '../../types'
import { date, money } from '../../utils/format'
import { usePortal } from './Portal'

const EXAMPLES = ['Change the date', 'Change the headline', 'Replace an image', 'Fix spelling', 'Change a color']

// Suggestion chips insert "Change the date: " for the client to finish; a stub left empty is not a request.
const cleanRequest = (text: string) =>
  text.split('\n').map((l) => l.trim()).filter((l) => !EXAMPLES.some((ex) => l === `${ex}:`)).join('\n').trim()

const VERSION_NOTE: Record<string, string> = {
  changes_requested: 'Changes requested',
  approved: 'Approved',
  superseded: 'Earlier version',
  review: 'Current',
}

const DESIGN_NOTE: Record<DesignStatus, [string, string]> = {
  review: ['Ready for you', 'text-brand'],
  changes_requested: ['Changes sent', 'text-warn'],
  approved: ['Approved', 'text-ok'],
  pending: ['In progress', 'text-muted'],
}

type DesignView = Design<Version>
const LOCKED = ['approved', 'finalization', 'payment_pending', 'paid', 'delivered', 'completed']

export default function Review() {
  const { view, token, setView } = usePortal()
  const designs = view.deliverables
  const multi = designs.length > 1
  const [pickedId, setPickedId] = useState<number | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null) // an older version being looked at
  const [modal, setModal] = useState<'changes' | 'approve' | null>(null)

  // Until the client chooses, open the first design that is waiting for them.
  const design = designs.find((d) => d.id === pickedId) ?? designs.find((d) => d.status === 'review') ?? designs[0]
  if (!design) {
    return <Notice icon={<Clock className="size-5" />} title="Your project is being set up">You'll see your designs here as soon as they are ready.</Notice>
  }
  const pick = (id: number) => { setPickedId(id); setSelectedId(null) }
  const latest = design.versions.find((v) => v.id === design.latest_version_id)
  const shown = design.versions.find((v) => v.id === selectedId) ?? latest

  const approvedCount = designs.filter((d) => d.status === 'approved').length
  const inReview = design.status === 'review' && !LOCKED.includes(view.status)
  const remaining = Math.max(0, view.revisions_included - design.revisions_used)
  const viewingOld = !!latest && !!shown && shown.id !== latest.id
  const pageUrl = (p: number) => `/api/r/${token}/versions/${shown?.id}/pages/${p}?r=${view.preview_rev}`

  // After answering one design, take the client to the next one that needs them.
  const afterAnswer = (next: ClientView, stay = false) => {
    setView(next)
    setModal(null)
    setSelectedId(null)
    if (!stay) setPickedId(next.deliverables.find((d) => d.status === 'review')?.id ?? design.id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div>
      <AdvanceBanner view={view} />
      {multi && <DesignPicker designs={designs} currentId={design.id} approved={approvedCount} onPick={pick} />}

      {!latest || !shown ? (
        <div>
          <StageHeadline view={view} design={design} multi={multi} approved={approvedCount} total={designs.length} />
          <div className="mt-5"><Notice icon={<Clock className="size-5" />} title={multi ? `${design.title} is in progress` : 'Your creative is being designed'}>
            You'll see it here, on this same link, as soon as it's ready for review.
          </Notice></div>
        </div>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-10">
          <div className="min-w-0">
            <StageHeadline view={view} design={design} multi={multi} approved={approvedCount} total={designs.length} />
            <div className="mt-5">
              <PreviewStage
                pageUrl={pageUrl}
                pages={shown.pages}
                alt={`${design.title}, version ${shown.number}`}
                watermarked={view.watermarked}
                caption={view.watermarked ? <span className="font-medium tracking-[0.02em] text-ink-2">Client review copy</span> : undefined}
              />
            </div>
            {viewingOld && (
              <p className="mt-3 text-[13px] text-warn">
                You're looking at version {shown.number}.{' '}
                <button className="font-medium underline underline-offset-2" onClick={() => setSelectedId(null)}>
                  Back to the latest version
                </button>
              </p>
            )}
          </div>

          <aside className="space-y-6">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm lg:grid-cols-1">
              {multi && <Meta label="Design">{design.title}</Meta>}
              <Meta label="Version">{shown.number}{!viewingOld && latest.number > 1 ? ' (latest)' : ''}</Meta>
              <Meta label="Uploaded">{date(shown.created_at)}</Meta>
              {view.format && !multi && <Meta label="Format">{view.format}</Meta>}
              {(design.status === 'review' || design.status === 'changes_requested') && (
                <Meta label={multi ? 'Revisions for this design' : 'Revisions'}>
                  {remaining > 0 ? `${remaining} of ${view.revisions_included} left` : view.extra_revision_price
                    ? `Included revisions used; additional changes are ${money(view.extra_revision_price)} each`
                    : 'Included revisions used'}
                </Meta>
              )}
            </dl>

            {shown.note && (
              <div className="rounded-lg border border-line bg-surface p-4 text-sm">
                <div className="mb-1 text-[13px] text-muted">Note from the studio</div>
                <p className="whitespace-pre-line text-ink-2">{shown.note}</p>
              </div>
            )}

            {design.versions.length > 1 && <History versions={design.versions} shownId={shown.id} onPick={(id) => setSelectedId(id === latest.id ? null : id)} />}
          </aside>
        </div>
      )}

      {inReview && latest && !viewingOld && (
        <div className="no-print fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:justify-end sm:px-6">
            <span className="mr-auto hidden min-w-0 truncate text-sm text-muted sm:block">{multi ? `${design.title}: ready for your review` : 'Ready for your review'}</span>
            <Button size="lg" className="flex-1 sm:flex-none" onClick={() => setModal('changes')}>Request changes</Button>
            <Button size="lg" variant="brand" className="flex-1 sm:flex-none" onClick={() => setModal('approve')}>{multi ? 'Approve this design' : 'Approve creative'}</Button>
          </div>
        </div>
      )}

      <RequestChanges open={modal === 'changes'} onClose={() => setModal(null)} token={token} design={design} multi={multi}
        extraPrice={remaining === 0 ? view.extra_revision_price : 0} onDone={(v) => afterAnswer(v, true)} />
      {latest && <ApproveDialog open={modal === 'approve'} onClose={() => setModal(null)} token={token} version={latest} design={design} multi={multi}
        onDone={(v) => afterAnswer(v)} />}
    </div>
  )
}

function AdvanceBanner({ view }: { view: ClientView }) {
  const a = view.advance
  if (!a || a.status === 'paid' || a.status === 'none') return null
  return (
    <div className="mb-6 rounded-xl border border-warn/40 bg-warn-soft p-4">
      <h2 className="font-semibold text-ink">{a.status === 'submitted' ? 'Advance payment received for checking' : 'Advance payment needed'}</h2>
      <p className="mt-1 text-sm text-ink-2">
        {a.status === 'submitted'
          ? 'Thank you. The studio will confirm it shortly and your work carries on.'
          : 'Please pay the advance so the studio can keep your work moving. It takes a minute by UPI.'}
      </p>
      {a.status === 'requested' && <Link to="advance" className={buttonCls('brand', 'md', 'mt-3')}>Pay advance</Link>}
    </div>
  )
}

function DesignPicker({ designs, currentId, approved, onPick }:
  { designs: DesignView[]; currentId: number; approved: number; onPick: (id: number) => void }) {
  return (
    <div className="mb-7">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h2 className="text-[13px] font-semibold text-ink">Your designs</h2>
        <span className="text-[13px] text-muted">{approved} of {designs.length} approved</span>
      </div>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
        {designs.map((d) => {
          const [label, tone] = DESIGN_NOTE[d.status]
          return (
            <button key={d.id} type="button" onClick={() => onPick(d.id)} aria-current={d.id === currentId}
              className={cx('min-w-[9.5rem] shrink-0 rounded-lg border bg-surface px-3 py-2.5 text-left',
                d.id === currentId ? 'border-ink' : 'border-line hover:border-faint')}>
              <span className="block max-w-[14rem] truncate text-sm font-medium text-ink">{d.title}</span>
              <span className={cx('mt-0.5 flex items-center gap-1 text-xs font-medium', tone)}>
                {d.status === 'approved' && <CircleCheck className="size-3.5" aria-hidden />}{label}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function StageHeadline({ view, design, multi, approved, total }:
  { view: ClientView; design: DesignView; multi: boolean; approved: number; total: number }) {
  const lastRequest = design.versions.flatMap((v) => v.comments).at(-1)
  switch (view.status) {
    case 'approved':
    case 'finalization':
      return (
        <Headline done title={multi ? 'All designs approved' : 'Creative approved'}>
          Your approved project is being prepared for final delivery. The studio will share the invoice here shortly.
        </Headline>
      )
    case 'payment_pending':
      return (
        <Headline done title={multi ? 'All designs approved' : 'Creative approved'}>
          Your approved project is ready for final delivery.{' '}
          {view.payment?.pending
            ? 'Your payment details were received; the studio will confirm shortly.'
            : 'Next step: complete the project payment.'}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Link to="invoice" className={buttonCls('brand', 'lg')}>{view.payment?.pending ? 'View invoice' : 'View invoice and pay'}</Link>
            {view.invoice && <span className="text-sm text-muted">Invoice {view.invoice.number}, {money(view.invoice.amount_due)} due</span>}
          </div>
        </Headline>
      )
    case 'paid':
    case 'delivered':
    case 'completed':
      return (
        <Headline done title="Payment received. Your final files are ready.">
          <div className="mt-4"><Link to="delivery" className={buttonCls('brand', 'lg')}>Download deliverables</Link></div>
        </Headline>
      )
  }
  switch (design.status) {
    case 'pending':
      return <Headline title={multi ? `We're working on ${design.title}` : 'The studio is preparing your next version'}>You'll see it here on this same link as soon as it's ready.</Headline>
    case 'review':
      return <Headline title={multi ? `${design.title} is ready for review` : 'Your creative is ready for review'}>Take a look, then approve it or tell us what to change.</Headline>
    case 'changes_requested':
      return (
        <Headline title="Your changes are with the studio">
          You'll get the next version on this same link.
          {lastRequest && <q className="mt-3 block border-l-2 border-line pl-3 whitespace-pre-line text-ink-2 italic">{lastRequest.body}</q>}
        </Headline>
      )
    case 'approved':
      return (
        <Headline done title={`${multi ? design.title : 'This design'} is approved`}>
          {multi ? `${approved} of ${total} designs approved. Pick the next one above to continue.` : 'Thank you!'}
        </Headline>
      )
  }
}

function Headline({ title, children, done }: { title: string; children?: React.ReactNode; done?: boolean }) {
  return (
    <div>
      <h2 className="flex items-center gap-2 text-lg font-semibold tracking-[-0.01em] text-ink">
        {done && <CircleCheck className="size-5 text-ok" aria-hidden />}
        {title}
      </h2>
      {children && <div className="mt-1 max-w-[62ch] text-[15px] text-ink-2">{children}</div>}
    </div>
  )
}

function Notice({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-6">
      <div className="flex items-center gap-2 font-semibold text-ink">{icon}{title}</div>
      <p className="mt-1 text-ink-2">{children}</p>
    </div>
  )
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="mt-0.5 text-ink">{children}</dd>
    </div>
  )
}

function History({ versions, shownId, onPick }: { versions: Version[]; shownId: number; onPick: (id: number) => void }) {
  return (
    <div>
      <h3 className="mb-2 text-[13px] text-muted">Version history</h3>
      <ol className="divide-y divide-line-soft rounded-lg border border-line bg-surface">
        {[...versions].reverse().map((v) => (
          <li key={v.id}>
            <button onClick={() => onPick(v.id)}
              className={cx('flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-canvas',
                v.id === shownId && 'bg-canvas')}>
              <span>
                <span className="block text-sm font-medium text-ink">Version {v.number}</span>
                <span className="block text-xs text-muted">{date(v.created_at)}</span>
                {v.comments.map((c) => (
                  <span key={c.id} className="mt-1 line-clamp-2 block text-xs text-ink-2">“{c.body}”</span>
                ))}
              </span>
              <span className={cx('shrink-0 text-xs', v.status === 'approved' ? 'font-medium text-ok' : 'text-muted')}>
                {VERSION_NOTE[v.status] ?? v.status}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

function RequestChanges({ open, onClose, token, design, multi, extraPrice, onDone }:
  { open: boolean; onClose: () => void; token: string; design: DesignView; multi: boolean; extraPrice: number; onDone: (v: ClientView) => void }) {
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const request = cleanRequest(body)
  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      onDone(await api.post<ClientView>(`/api/r/${token}/revisions`, { body: request, deliverable_id: design.id }))
      setBody('')
    } catch (e) {
      setErr((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={multi ? `What would you like changed in ${design.title}?` : 'What would you like changed?'} wide
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={request.length < 3} onClick={submit}>Send revision request</Button>
      </>}>
      <Textarea rows={10} value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000}
        placeholder="Describe the changes — for example, “Please make the date larger.”" aria-label="Your changes" />
      <div className="mt-3 flex flex-wrap gap-1.5">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" onClick={() => setBody((b) => (b ? `${b.trimEnd()}\n${ex}: ` : `${ex}: `))}
            className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-faint">
            {ex}
          </button>
        ))}
      </div>
      {body.trim() && request.length < 3 && (
        <p className="mt-3 text-[13px] text-muted">Add a few words after each suggestion to say what should change.</p>
      )}
      {extraPrice > 0 && (
        <p className="mt-4 rounded-md bg-warn-soft px-3 py-2 text-[13px] text-warn">
          Your included revisions are used. This request is an additional revision ({money(extraPrice)}), added to the final invoice.
        </p>
      )}
      <div className="mt-3"><ErrorNote error={err} /></div>
    </Modal>
  )
}

function ApproveDialog({ open, onClose, token, version, design, multi, onDone }:
  { open: boolean; onClose: () => void; token: string; version: Version; design: DesignView; multi: boolean; onDone: (v: ClientView) => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const approve = async () => {
    setBusy(true); setErr(null)
    try {
      onDone(await api.post<ClientView>(`/api/r/${token}/approve`, { version_id: version.id }))
    } catch (e) {
      setErr((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={multi ? `Approve ${design.title}?` : 'Approve this creative?'}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="brand" loading={busy} onClick={approve} data-autofocus>{multi ? 'Approve this design' : 'Approve creative'}</Button>
      </>}>
      <p className="text-ink-2">By approving, you confirm that version {version.number}{multi ? ` of ${design.title}` : ''} is ready for final delivery.</p>
      <p className="mt-2 text-sm text-muted">{multi ? 'Your other designs are reviewed separately.' : 'You can still contact the studio about any delivery issues.'}</p>
      <div className="mt-3"><ErrorNote error={err} /></div>
    </Modal>
  )
}
