import { Check, Download, ExternalLink, Link2, MessageCircle, MoreHorizontal, Pencil, Plus, RotateCcw, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import FileDrop from '../../components/FileDrop'
import { PreviewStage } from '../../components/preview'
import {
  Button, CopyButton, Empty, ErrorNote, Field, Input, Modal, Pill, Panel, Select, Spinner, StatusPill, Switch, Textarea,
  buttonCls, cx, useToast,
} from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { Design, DesignStatus, Payment, ProjectDetail as PD, ShareItem } from '../../types'
import { bytes, date, dateTime, fileKind, money, relative, toPaise, toRupees, waHref } from '../../utils/format'

export default function ProjectDetail() {
  const { id } = useParams()
  const { data: p, setData, error, loading } = useAsync(() => api.get<PD>(`/api/projects/${id}`), [id], { poll: 8000 })
  const { bump, isStaff } = useAdmin()
  const uploadError = (useLocation().state as { uploadError?: string } | null)?.uploadError
  if (loading) return <Spinner />
  if (error || !p) return <ErrorNote error={error?.message} />
  const update = (next: PD) => { setData(next); bump() }

  return (
    <>
      {uploadError && p.versions.length === 0 && <div className="mb-4"><ErrorNote error={uploadError} /></div>}
      <Header p={p} onChange={update} staff={isStaff} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-6">
          {!isStaff && <AdvanceCard p={p} onChange={update} />}
          <NextStep p={p} onChange={update} staff={isStaff} />
          <DesignsPanel p={p} onChange={update} staff={isStaff} />
          {['approved', 'finalization', 'payment_pending', 'paid', 'delivered', 'completed'].includes(p.status) && <FinalsPanel p={p} onChange={update} />}
          {!isStaff && p.invoice && <InvoicePanel p={p} />}
        </div>
        <div className="min-w-0 space-y-6">
          {!isStaff && <SharePanel p={p} onChange={update} />}
          <DetailsPanel p={p} staff={isStaff} />
          {!isStaff && p.payments.length > 0 && <PaymentsPanel payments={p.payments} />}
          {!isStaff && p.downloads.length > 0 && (
            <Panel title="Downloads" pad={false}>
              <ul className="divide-y divide-line-soft text-sm">
                {p.downloads.map((d) => (
                  <li key={d.id} className="flex justify-between gap-3 px-5 py-2.5"><span className="truncate">{d.file}</span><span className="shrink-0 text-muted">{dateTime(d.created_at)}</span></li>
                ))}
              </ul>
            </Panel>
          )}
          <Timeline p={p} />
        </div>
      </div>
    </>
  )
}

// ---------- header ----------

function Header({ p, onChange, staff }: { p: PD; onChange: (p: PD) => void; staff?: boolean }) {
  const [menu, setMenu] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<string | null>(null)
  const act = async (a: string) => {
    setBusy(a)
    try { onChange(await api.post<PD>(`/api/projects/${p.id}/actions/${a}`)) } catch (e) { alert((e as ApiError).message) }
    setBusy(null); setConfirm(null); setMenu(false)
  }
  const canReopen = ['approved', 'finalization', 'payment_pending'].includes(p.status)
  const canAdvance = p.advance.status !== 'paid' && !['paid', 'delivered', 'completed'].includes(p.status)
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
          <span className="tabular-nums">Project #{p.code}</span>
          {staff ? <span>{p.client.display_name}</span> : <Link to={`/clients/${p.client.id}`} className="hover:text-ink hover:underline">{p.client.display_name}</Link>}
        </div>
        <h1 className="mt-1 text-[24px] leading-tight font-semibold tracking-[-0.02em]">{p.name}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <StatusPill status={p.status} staff={staff} />
          {!staff && <span className="text-sm font-medium tabular-nums">{money(p.total)}</span>}
          {p.due_date && <span className="text-[13px] text-muted">Due {date(p.due_date)}</span>}
        </div>
      </div>
      {!staff && <div className="relative flex items-center gap-2">
        <Link to={`/projects/${p.id}/edit`} className={buttonCls('secondary')}><Pencil className="size-3.5" /> Edit</Link>
        <Button onClick={() => setMenu(!menu)} aria-label="More actions"><MoreHorizontal className="size-4" /></Button>
        {menu && (
          <div className="absolute top-11 right-0 z-20 w-56 rounded-lg border border-line bg-surface p-1 shadow-lg">
            {p.status === 'brief_received' && <MenuItem onClick={() => act('start_design')}>Mark as in design</MenuItem>}
            {canReopen && <MenuItem onClick={() => setConfirm('reopen')}><RotateCcw className="size-3.5" /> Reopen for changes</MenuItem>}
            {canAdvance && <MenuItem onClick={() => { setMenu(false); setConfirm('advance') }}>{p.advance.status === 'none' ? 'Ask for an advance' : 'Change the advance'}</MenuItem>}
            {['paid', 'delivered'].includes(p.status) && <MenuItem onClick={() => act('complete')}><Check className="size-3.5" /> Mark complete</MenuItem>}
            {p.active_link && <a href={p.active_link.url} target="_blank" rel="noreferrer" className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-canvas"><ExternalLink className="size-3.5" /> Open client view</a>}
          </div>
        )}
      </div>}
      <AdvanceModals key={p.advance.amount} p={p} modal={confirm === 'advance' ? 'amount' : null} onClose={() => setConfirm(null)} onChange={onChange} />
      <Modal open={confirm === 'reopen'} onClose={() => setConfirm(null)} title="Reopen this project?"
        footer={<><Button onClick={() => setConfirm(null)}>Cancel</Button><Button variant="primary" loading={busy === 'reopen'} onClick={() => act('reopen')}>Reopen</Button></>}>
        <p className="text-ink-2">The approval is cleared{p.invoice ? ' and the unpaid invoice is voided' : ''}. Upload a new version and the client reviews it on the same link.</p>
      </Modal>
    </div>
  )
}

const MenuItem = ({ children, onClick }: { children: React.ReactNode; onClick: () => void }) => (
  <button onClick={onClick} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-canvas">{children}</button>
)

// ---------- next step ----------

function NextStep({ p, onChange, staff }: { p: PD; onChange: (p: PD) => void; staff?: boolean }) {
  const ds = p.deliverables
  const multi = ds.length > 1
  const pending = p.payments.find((x) => x.status === 'submitted')
  const versionsOf = (d: Design) => p.versions.filter((v) => v.deliverable_id === d.id)
  const openRequest = (d: Design) => versionsOf(d).flatMap((v) => v.comments).filter((c) => c.status === 'open').at(-1)
  const waiting = ds.filter((d) => d.status === 'pending')
  const changes = ds.filter((d) => d.status === 'changes_requested')
  const inReview = ds.filter((d) => d.status === 'review')
  const approvedN = ds.filter((d) => d.status === 'approved').length
  const progress = `${approvedN} of ${ds.length} designs approved.`
  let title = '', body: React.ReactNode = null, action: React.ReactNode = null

  switch (p.status) {
    case 'brief_received':
    case 'in_design': {
      const d = waiting[0]
      title = multi ? (d ? `Upload ${d.title}` : 'Waiting for the client') : (p.versions.length ? 'Upload the next version' : 'Upload the first version')
      body = multi
        ? `${progress} ${waiting.length} still to upload. Each design gets its own preview and its own approval, all on one client link.`
        : `A ${p.watermark ? 'watermarked' : 'clean (no watermark)'}, reduced-resolution preview is generated automatically and a review link is created.`
      action = d && <UploadVersion p={p} design={d} onChange={onChange} primary label={multi ? `Upload ${d.title}` : undefined} />
      break
    }
    case 'review':
      title = multi ? `Waiting for ${p.client.display_name} to review ${inReview.length} design${inReview.length === 1 ? '' : 's'}`
        : `Waiting for ${p.client.display_name} to review version ${p.versions.at(-1)?.number}`
      body = <>
        {multi && <span className="block">{progress}{waiting.length > 0 && ` Still to upload: ${waiting.map((d) => d.title).join(', ')}.`}</span>}
        <span className="block">{p.active_link?.last_viewed_at ? `Last viewed ${relative(p.active_link.last_viewed_at)}.` : 'The client hasn\'t opened the link yet.'}</span>
      </>
      action = <>
        {p.share.review.link && <ShareButtons item={p.share.review} number={p.share.whatsapp_number} label="review" />}
        {waiting[0] && <UploadVersion p={p} design={waiting[0]} onChange={onChange} label={`Upload ${waiting[0].title}`} />}
      </>
      break
    case 'revision_requested':
      title = multi ? `Changes requested on ${changes.length} design${changes.length === 1 ? '' : 's'}` : 'Changes requested'
      body = (
        <div className="space-y-3">
          {changes.map((d) => {
            const r = openRequest(d)
            return (
              <div key={d.id}>
                {multi && <div className="font-medium text-ink">{d.title}</div>}
                {r && <q className="block border-l-2 border-warn pl-3 whitespace-pre-line text-ink">{r.body}</q>}
                {r && <span className="mt-1 block text-[13px] text-muted">{relative(r.created_at)}{r.is_extra ? (staff ? ', additional revision' : ', additional revision (added to the invoice)') : ''}</span>}
              </div>
            )
          })}
        </div>
      )
      action = <>{changes.map((d, i) => <UploadVersion key={d.id} p={p} design={d} onChange={onChange} primary={i === 0}
        label={multi ? `Upload ${d.title}` : `Upload version ${versionsOf(d).length + 1}`} />)}</>
      break
    case 'approved':
      title = multi ? 'All designs approved. Add the final files' : 'Creative approved. Add the final files'
      body = 'Upload the production files the client will receive after payment, or, if the files you uploaded for review are already the high-resolution finals, create the invoice with those. They stay private until payment.'
      action = <IssueInvoice p={p} onChange={onChange} useApproved />
      break
    case 'finalization':
      title = 'Ready to issue the invoice'
      body = 'Issuing the invoice moves the project to Payment pending and shows the invoice on the client\'s link.'
      action = <IssueInvoice p={p} onChange={onChange} />
      break
    case 'payment_pending':
      if (pending) {
        title = 'Confirm the payment'
        body = <PendingPayment pay={pending} />
        action = <ConfirmPayment pay={pending} p={p} onChange={onChange} />
      } else {
        title = 'Waiting for payment'
        body = `Invoice ${p.invoice?.number} for ${money(p.invoice?.amount_due)}${p.invoice?.advance_paid ? ` (the ${money(p.invoice.advance_paid)} advance is already taken off)` : ''} is on the client's link. Files unlock only after you confirm the payment.`
        action = p.share.payment.link && <ShareButtons item={p.share.payment} number={p.share.whatsapp_number} label="payment" />
      }
      break
    case 'paid':
      title = 'Paid. Final files released'
      body = 'The client can now download the final files from their link.'
      action = p.share.delivery.link && <ShareButtons item={p.share.delivery} number={p.share.whatsapp_number} label="delivery" />
      break
    case 'delivered':
      title = 'Delivered'
      body = `The client downloaded the files ${relative(p.delivered_at)}. Mark the project complete when you're done.`
      break
    case 'completed':
      title = 'Completed'
      body = 'Nothing left to do on this project.'
      break
  }

  // Billing, payment and delivery belong to the studio owner.
  if (staff && ['approved', 'finalization', 'payment_pending', 'paid', 'delivered', 'completed'].includes(p.status)) {
    title = p.status === 'approved' || p.status === 'finalization' ? 'Approved by the client' : 'Handled by the studio owner'
    body = p.status === 'approved' || p.status === 'finalization'
      ? 'The creative is approved. You can add the final production files below. The studio owner takes it from here.'
      : 'This project has moved on to billing and delivery. There is nothing for you to do here.'
    action = null
  }
  return (
    <section className={cx('rounded-xl border bg-surface p-5', p.status === 'revision_requested' || pending ? 'border-warn/40' : 'border-line')}>
      <h2 className="font-semibold">{title}</h2>
      {body && <div className="mt-1.5 max-w-[68ch] text-sm text-ink-2">{body}</div>}
      {action && <div className="mt-4 flex flex-wrap gap-2">{action}</div>}
    </section>
  )
}

function PendingPayment({ pay }: { pay: Payment }) {
  return (
    <div>
      The client says they paid <b className="font-semibold text-ink">{money(pay.amount)}</b>
      {pay.reference ? <> with UPI reference <b className="font-semibold text-ink tabular-nums">{pay.reference}</b></> : ' and sent a screenshot'} ({relative(pay.submitted_at)}).
      Check your bank or UPI app before confirming.
      {pay.proof_file_id && (
        <a href={`/api/admin/files/${pay.proof_file_id}?inline=1`} target="_blank" rel="noreferrer" className="mt-2 flex items-center gap-1 font-medium text-ink underline underline-offset-2">
          View payment screenshot <ExternalLink className="size-3.5" />
        </a>
      )}
    </div>
  )
}

function ConfirmPayment({ pay, p, onChange }: { pay: Payment; p: PD; onChange: (p: PD) => void }) {
  const [mode, setMode] = useState<'confirm' | 'reject' | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const toast = useToast()
  const go = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/api/${pay.kind === 'advance' ? 'advances' : 'payments'}/${pay.id}/${mode}`, mode === 'reject' ? { note } : {})
      onChange(await api.get<PD>(`/api/projects/${p.id}`))
      toast(mode === 'confirm' ? (pay.kind === 'advance' ? 'Advance confirmed.' : 'Payment confirmed. Files released.') : 'Client asked to check the reference')
      setMode(null)
    } catch (e) {
      setErr((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button variant="primary" onClick={() => setMode('confirm')}><Check className="size-4" /> {pay.kind === 'advance' ? 'Confirm advance received' : 'Confirm payment received'}</Button>
      <Button onClick={() => setMode('reject')}>Can't find it</Button>
      <Modal open={mode !== null} onClose={() => setMode(null)} title={mode === 'confirm' ? 'Confirm this payment?' : 'Payment not found'}
        footer={<><Button onClick={() => setMode(null)}>Cancel</Button>
          <Button variant={mode === 'confirm' ? 'primary' : 'danger'} loading={busy} onClick={go}>{mode === 'confirm' ? (pay.kind === 'advance' ? 'Confirm advance' : 'Confirm and release files') : 'Ask client to check'}</Button></>}>
        {mode === 'confirm' ? (
          <p className="text-ink-2">Only confirm once you've seen <b>{money(pay.amount)}</b> {pay.reference ? <>with reference <b className="tabular-nums">{pay.reference}</b> </> : null}in your account. {pay.kind === 'advance' ? 'It will be taken off the final invoice.' : 'The client gets access to the final files immediately.'}</p>
        ) : (
          <Field label="Message to the client (optional)">
            <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="The amount received was different from the invoice." maxLength={255} />
          </Field>
        )}
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
    </>
  )
}

function IssueInvoice({ p, onChange, useApproved }: { p: PD; onChange: (p: PD) => void; useApproved?: boolean }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [includeExtra, setIncludeExtra] = useState(true)
  const { data: prev } = useAsync(() => api.get<{ items: { description: string; quantity: number; amount: number; note: string | null }[]; subtotal: number; discount: number; tax: number; total: number }>(`/api/projects/${p.id}/invoice-preview`), [p.id, p.status])
  const extra = prev?.items.find((i) => i.description === 'Additional revisions')
  const issue = async () => {
    setBusy(true); setErr(null)
    try { onChange(await api.post<PD>(`/api/projects/${p.id}/invoice`, { include_extra: includeExtra, use_approved_files: !!useApproved })); setOpen(false) }
    catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>{useApproved ? 'Create invoice with the approved files' : 'Review and issue invoice'}</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Issue invoice" wide
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={issue}>Issue invoice</Button></>}>
        {!prev ? <Spinner /> : (
          <>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line-soft">
                {prev.items.filter((i) => includeExtra || i !== extra).map((i) => (
                  <tr key={i.description}><td className="py-2">{i.description}{i.quantity > 1 ? ` × ${i.quantity}` : ''}</td><td className="py-2 text-right tabular-nums">{i.note ?? money(i.amount)}</td></tr>
                ))}
              </tbody>
            </table>
            {extra && (
              <label className="mt-3 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={includeExtra} onChange={(e) => setIncludeExtra(e.target.checked)} className="size-4 accent-[var(--brand)]" />
                Charge for {extra.quantity} additional revision{extra.quantity > 1 ? 's' : ''}
              </label>
            )}
            {useApproved && (
              <div className="mt-4 rounded-lg bg-canvas p-3 text-sm">
                <p className="font-medium text-ink">Final files the client will receive after payment</p>
                <ul className="mt-1.5 space-y-0.5 text-ink-2">
                  {p.deliverables.map((d) => {
                    const v = p.versions.filter((x) => x.deliverable_id === d.id && x.status === 'approved').at(-1)
                    return v ? <li key={d.id} className="flex justify-between gap-3"><span className="truncate">{d.title}</span><span className="shrink-0 text-muted">{v.master?.name}{v.master ? `, ${bytes(v.master.size)}` : ''}</span></li> : null
                  })}
                </ul>
                <p className="mt-2 text-[13px] text-muted">These are the approved files exactly as you uploaded them, full resolution. The client only ever sees watermarked previews until they pay.</p>
              </div>
            )}
            <p className="mt-4 text-[13px] text-muted">Totals with discount and GST are calculated on the server when you issue it.</p>
          </>
        )}
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
    </>
  )
}

// ---------- creative ----------



function UploadVersion({ p, design, onChange, primary, label }:
  { p: PD; design?: Design; onChange: (p: PD) => void; primary?: boolean; label?: string }) {
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const mine = design ? p.versions.filter((v) => v.deliverable_id === design.id) : p.versions
  const next = (mine.at(-1)?.number ?? 0) + 1
  const multi = p.deliverables.length > 1
  const upload = async () => {
    const f = file.current?.files?.[0]
    if (!f) { setErr('Choose a file to upload.'); return }
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.set('file', f); fd.set('note', note)
    if (design) fd.set('deliverable_id', String(design.id))
    try { onChange(await api.post<PD>(`/api/projects/${p.id}/versions`, fd)); setOpen(false); setNote(''); toast(`${multi && design ? design.title + ': ' : ''}version ${next} uploaded`) }
    catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const what = multi && design ? design.title : null
  return (
    <>
      <Button variant={primary ? 'primary' : 'secondary'} onClick={() => setOpen(true)}><Upload className="size-4" /> {label ?? `Upload version ${next}`}</Button>
      <Modal open={open} onClose={() => setOpen(false)} title={what ? `Upload version ${next} of ${what}` : `Upload version ${next}`}
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={upload}>Upload and generate preview</Button></>}>
        <div className="space-y-4">
          <Field label="Design file" hint={`PNG, JPG, WEBP or PDF. The client only ever sees the ${p.watermark ? 'watermarked' : 'reduced-size'} preview.`}>
            <FileDrop inputRef={file} accept=".png,.jpg,.jpeg,.webp,.pdf" title="Drag and drop the design here" hint="or click to browse. PNG, JPG, WEBP or PDF" />
          </Field>
          <Field label="Note to the client (optional)"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Date enlarged as requested." /></Field>
          <ErrorNote error={err} />
        </div>
      </Modal>
    </>
  )
}

const VSTATUS: Record<string, [string, 'neutral' | 'warn' | 'ok' | 'info']> = {
  review: ['In review', 'info'], changes_requested: ['Changes requested', 'warn'], approved: ['Approved', 'ok'], superseded: ['Superseded', 'neutral'],
}
const DSTATUS: Record<DesignStatus, [string, 'neutral' | 'warn' | 'ok' | 'info']> = {
  pending: ['Not started', 'neutral'], review: ['In review', 'info'], changes_requested: ['Changes requested', 'warn'], approved: ['Approved', 'ok'],
}

/** Every design in the project: its own preview, versions and approval, all on one client link. */
function DesignsPanel({ p, onChange, staff }: { p: PD; onChange: (p: PD) => void; staff?: boolean }) {
  const ds = p.deliverables
  const multi = ds.length > 1
  const todo = ds.find((x) => x.status === 'changes_requested') ?? ds.find((x) => x.status === 'pending') ?? ds.find((x) => x.status === 'review') ?? ds[0]
  const [sel, setSel] = useState<number | null>(null)
  const d = ds.find((x) => x.id === sel) ?? todo
  const [vid, setVid] = useState<number | null>(null)
  const [modal, setModal] = useState<'add' | 'rename' | 'reopen' | 'remove' | 'approve' | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => setVid(null), [d?.id, p.versions.length])
  const toast = useToast()

  const versions = p.versions.filter((v) => v.deliverable_id === d?.id)
  const shown = versions.find((v) => v.id === vid) ?? versions.at(-1)
  const editable = ['brief_received', 'in_design', 'review', 'revision_requested', 'approved'].includes(p.status)
  const canUpload = editable && p.status !== 'approved' && !!d && d.status !== 'approved'

  const run = async (fn: () => Promise<PD>, done?: string) => {
    setBusy(true); setErr(null)
    try { onChange(await fn()); setModal(null); if (done) toast(done) } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const open = (m: typeof modal, initial = '') => { setName(initial); setErr(null); setModal(m) }

  return (
    <Panel title={multi ? `Designs (${ds.filter((x) => x.status === 'approved').length} of ${ds.length} approved)` : 'Creative'} pad={false} actions={<>
      {!staff && <WatermarkToggle p={p} onChange={onChange} />}
      {editable && <Button onClick={() => open('add')}><Plus className="size-4" /> Add design</Button>}
    </>}>
      {multi && (
        <div className="flex gap-2 overflow-x-auto border-b border-line-soft px-5 py-3">
          {ds.map((x) => (
            <button key={x.id} type="button" onClick={() => setSel(x.id)} aria-current={x.id === d?.id}
              className={cx('min-w-[9rem] shrink-0 rounded-lg border px-3 py-2 text-left', x.id === d?.id ? 'border-ink bg-canvas' : 'border-line hover:border-faint')}>
              <span className="block max-w-[14rem] truncate text-sm font-medium">{x.title}</span>
              <span className="mt-1 block"><Pill tone={DSTATUS[x.status][1]}>{DSTATUS[x.status][0]}</Pill></span>
            </button>
          ))}
        </div>
      )}

      {d && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line-soft px-5 py-3">
          <div className="mr-auto flex min-w-0 items-center gap-2">
            <span className="truncate font-medium">{d.title}</span>
            {!multi && <Pill tone={DSTATUS[d.status][1]}>{DSTATUS[d.status][0]}</Pill>}
            {editable && <button type="button" onClick={() => open('rename', d.title)} aria-label="Rename design" className="rounded-md p-1.5 text-muted hover:bg-line-soft hover:text-ink"><Pencil className="size-3.5" /></button>}
          </div>
          {canUpload && <UploadVersion p={p} design={d} onChange={onChange} primary={d.status !== 'review'}
            label={versions.length ? undefined : 'Upload first version'} />}
          {!staff && canUpload && versions.length > 0 && (d.status === 'review' || d.status === 'changes_requested') && <Button onClick={() => open('approve')}><Check className="size-3.5" /> Approve for client</Button>}
          {!staff && d.status === 'approved' && !['paid', 'delivered', 'completed'].includes(p.status) && <Button onClick={() => open('reopen')}><RotateCcw className="size-3.5" /> Reopen</Button>}
          {editable && multi && versions.length === 0 && <Button variant="ghost" onClick={() => open('remove')} aria-label="Remove design"><Trash2 className="size-4" /></Button>}
        </div>
      )}

      {!shown ? (
        <Empty title="No version yet">{d ? `Upload the first version of ${d.title}. The first upload creates the review link.` : 'Add a design to begin.'}</Empty>
      ) : (
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="p-5">
            <PreviewStage pageUrl={(n) => `/api/admin/versions/${shown.id}/pages/${n}?r=${p.preview_rev}`} pages={shown.pages}
              alt={`${d?.title} version ${shown.number}`} watermarked={p.watermark}
              caption={`Version ${shown.number}: the ${p.watermark ? 'watermarked' : 'clean, un-watermarked'} preview your client sees`} />
          </div>
          <ol className="divide-y divide-line-soft border-t border-line-soft lg:border-t-0 lg:border-l">
            {[...versions].reverse().map((v) => (
              <li key={v.id}>
                <button onClick={() => setVid(v.id)} className={cx('w-full px-4 py-3 text-left hover:bg-canvas', v.id === shown.id && 'bg-canvas')}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">Version {v.number}</span>
                    <Pill tone={VSTATUS[v.status]?.[1]}>{VSTATUS[v.status]?.[0] ?? v.status}</Pill>
                  </div>
                  <div className="text-xs text-muted">{dateTime(v.created_at)}</div>
                  {v.comments.map((c) => <p key={c.id} className="mt-1.5 line-clamp-3 text-xs text-ink-2">“{c.body}”</p>)}
                  {v.master && (
                    <a href={`/api/admin/files/${v.master.id}`} onClick={(e) => e.stopPropagation()} className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted hover:text-ink">
                      <Download className="size-3" /> Original {fileKind(v.master)}
                    </a>
                  )}
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}

      <Modal open={modal === 'add' || modal === 'rename'} onClose={() => setModal(null)} title={modal === 'add' ? 'Add a design' : 'Rename design'}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={!name.trim()} onClick={() => run(() => modal === 'add'
            ? api.post<PD>(`/api/projects/${p.id}/deliverables`, { title: name })
            : api.put<PD>(`/api/deliverables/${d!.id}`, { title: name }), modal === 'add' ? 'Design added' : 'Renamed')}>
            {modal === 'add' ? 'Add design' : 'Save'}</Button></>}>
        <Field label="Name" hint="For example: Event banner, Roll-up standee, Instagram post.">
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} placeholder="Event banner 10 × 4 ft" />
        </Field>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
      <Modal open={modal === 'approve'} onClose={() => setModal(null)} title={`Approve ${d?.title ?? 'this design'} for the client?`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => run(() => api.post<PD>(`/api/deliverables/${d!.id}/approve`), 'Approved')}>Approve</Button></>}>
        <p className="text-ink-2">Use this when the client already said yes outside the tool, for example on a call or WhatsApp. The design is marked approved just as if they had pressed the button.</p>
        <p className="mt-2 text-ink-2">The client isn't notified and their page doesn't say the studio did it. Only your private activity log records it.</p>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
      <Modal open={modal === 'reopen'} onClose={() => setModal(null)} title={`Reopen ${d?.title ?? 'this design'}?`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => run(() => api.post<PD>(`/api/deliverables/${d!.id}/reopen`), 'Reopened')}>Reopen</Button></>}>
        <p className="text-ink-2">The approval is cleared{p.invoice && p.invoice.status !== 'void' ? ' and the unpaid invoice is voided' : ''}. Upload a new version and the client reviews it on the same link.{multi ? ' Your other designs stay approved.' : ''}</p>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
      <Modal open={modal === 'remove'} onClose={() => setModal(null)} title={`Remove ${d?.title ?? 'this design'}?`}
        footer={<><Button onClick={() => setModal(null)}>Cancel</Button>
          <Button variant="danger" loading={busy} onClick={() => run(() => api.del<PD>(`/api/deliverables/${d!.id}`), 'Design removed')}>Remove design</Button></>}>
        <p className="text-ink-2">It has no versions yet, so nothing is lost.</p>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
    </Panel>
  )
}

// ---------- advance payment ----------

/** The advance the client owes before the work carries on: reminders, recording it, confirming it. */
function AdvanceCard({ p, onChange }: { p: PD; onChange: (p: PD) => void }) {
  const a = p.advance
  const [modal, setModal] = useState<'amount' | 'received' | null>(null)
  if (a.status === 'none' || a.status === 'paid') return null
  const submitted = a.payments.find((x) => x.status === 'submitted')
  const remind = () => { api.post<PD>(`/api/projects/${p.id}/advance/remind`).then(onChange).catch(() => {}) }

  return (
    <section className="rounded-xl border border-warn/40 bg-surface p-5">
      {submitted ? (
        <>
          <h2 className="font-semibold">Confirm the advance</h2>
          <div className="mt-1.5 max-w-[68ch] text-sm text-ink-2"><PendingPayment pay={submitted} /></div>
          <div className="mt-4 flex flex-wrap gap-2"><ConfirmPayment pay={submitted} p={p} onChange={onChange} /></div>
        </>
      ) : (
        <>
          <h2 className="font-semibold">Advance of {money(a.amount - a.paid)} not paid yet</h2>
          <p className="mt-1.5 max-w-[68ch] text-sm text-ink-2">
            Asked {relative(a.requested_at)}.{a.reminded_at ? ` Last reminder ${relative(a.reminded_at).toLowerCase()}.` : ' No reminder sent yet.'} Your client sees the amount and a UPI QR on their link.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {p.share.advance.link && (
              <a href={waHref(p.share.whatsapp_number, p.share.advance.message!)} target="_blank" rel="noreferrer" onClick={remind} className={buttonCls('primary')}>
                <MessageCircle className="size-4" /> Remind on WhatsApp
              </a>
            )}
            <Button onClick={() => setModal('received')}><Check className="size-4" /> Mark as received</Button>
            <Button onClick={() => setModal('amount')}>Change amount</Button>
          </div>
        </>
      )}
      <AdvanceModals key={p.advance.amount} p={p} modal={modal} onClose={() => setModal(null)} onChange={onChange} />
    </section>
  )
}

function AdvanceModals({ p, modal, onClose, onChange }: { p: PD; modal: 'amount' | 'received' | null; onClose: () => void; onChange: (p: PD) => void }) {
  const [amount, setAmount] = useState(String(toRupees(Math.max(p.advance.amount, 0))))
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const toast = useToast()
  const run = async (fn: () => Promise<PD>, done: string) => {
    setBusy(true); setErr(null)
    try { onChange(await fn()); onClose(); toast(done) } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const pct = (n: number) => String(Math.round(toRupees(p.total) * n) / 100)
  return (
    <>
      <Modal open={modal === 'amount'} onClose={onClose} title={p.advance.status === 'none' ? 'Ask for an advance' : 'Change the advance'}
        footer={<>
          {p.advance.status !== 'none' && <Button variant="danger" className="sm:mr-auto" loading={busy} onClick={() => run(() => api.post<PD>(`/api/projects/${p.id}/advance`, { amount: 0 }), 'Advance removed')}>Remove advance</Button>}
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => run(() => api.post<PD>(`/api/projects/${p.id}/advance`, { amount: toPaise(amount) }), 'Advance saved')}>Save</Button>
        </>}>
        <Field label="Advance (₹)" hint={`The project total is ${money(p.total)}. The advance is taken off the final invoice.`}>
          <Input type="number" min={0} step="0.01" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {[25, 50, 100].map((n) => (
            <button key={n} type="button" onClick={() => setAmount(pct(n))} className="rounded-full border border-line px-3 py-1.5 text-[13px] text-ink-2 hover:border-faint">{n}% = {money(toPaise(pct(n)))}</button>
          ))}
        </div>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
      <Modal open={modal === 'received'} onClose={onClose} title="Mark the advance as received?"
        footer={<><Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => run(() => api.post<PD>(`/api/projects/${p.id}/advance/received`, { note }), 'Advance recorded')}>Mark as received</Button></>}>
        <p className="text-ink-2">Use this when {p.client.display_name} paid by cash, a transfer or a call and you have seen the money. The advance is taken off the final invoice.</p>
        <div className="mt-3"><Field label="Note (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Paid in cash" maxLength={30} /></Field></div>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
    </>
  )
}

function WatermarkToggle({ p, onChange }: { p: PD; onChange: (p: PD) => void }) {
  const [confirmOff, setConfirmOff] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const toast = useToast()
  const apply = async (enabled: boolean) => {
    setBusy(true); setErr(null)
    try {
      onChange(await api.post<PD>(`/api/projects/${p.id}/watermark`, { enabled }))
      setConfirmOff(false)
      toast(enabled ? 'Watermark is back on' : 'Watermark removed. The client now sees a clean preview.')
    } catch (e) {
      if (enabled) alert((e as ApiError).message); else setErr((e as ApiError).message)
    } finally { setBusy(false) }
  }
  return (
    <>
      <label className="flex items-center gap-2 text-[13px] text-ink-2">
        Watermark
        <Switch checked={p.watermark} disabled={busy} label="Watermark on the client's preview"
          onChange={(on) => (on ? apply(true) : setConfirmOff(true))} />
      </label>
      <Modal open={confirmOff} onClose={() => setConfirmOff(false)} title="Remove the watermark?"
        footer={<><Button onClick={() => setConfirmOff(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => apply(false)}>Remove watermark</Button></>}>
        <p className="text-ink-2">{p.client.display_name} will see a clean preview of every version on their link. Your original and the final files stay private until payment is confirmed.</p>
        <p className="mt-2 text-sm text-muted">The preview is still reduced in size, but anyone with the link can save it, so turn the watermark back on when they've seen it.</p>
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
    </>
  )
}

function FinalsPanel({ p, onChange }: { p: PD; onChange: (p: PD) => void }) {
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [dropKey, setDropKey] = useState(0)
  const file = useRef<HTMLInputElement>(null)
  const upload = async (e: React.FormEvent) => {
    e.preventDefault()
    const f = file.current?.files?.[0]
    if (!f) { setErr('Choose a file.'); return }
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.set('file', f); fd.set('label', label)
    try { onChange(await api.post<PD>(`/api/projects/${p.id}/finals`, fd)); setLabel(''); setDropKey((k) => k + 1) }
    catch (e2) { setErr((e2 as ApiError).message) } finally { setBusy(false) }
  }
  const remove = async (fid: number) => {
    if (!confirm('Remove this final file?')) return
    try { onChange(await api.del<PD>(`/api/files/${fid}`)) } catch (e) { alert((e as ApiError).message) }
  }
  return (
    <Panel title="Final files" pad={false} actions={<span className="text-xs text-muted">Private until payment is confirmed</span>}>
      {p.finals.length > 0 && (
        <ul className="divide-y divide-line-soft">
          {p.finals.map((f) => (
            <li key={f.id} className="flex items-center gap-3 px-5 py-3">
              <span className="w-10 shrink-0 rounded bg-canvas py-1 text-center text-[11px] font-medium text-ink-2">{fileKind(f)}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{f.label || f.name}</div>
                <div className="text-xs text-muted">{f.name}{f.width ? `, ${f.width} × ${f.height}` : ''}, {bytes(f.size)}</div>
              </div>
              <a href={`/api/admin/files/${f.id}`} className="rounded-md p-1.5 text-muted hover:bg-line-soft hover:text-ink" aria-label="Download"><Download className="size-4" /></a>
              {!['paid', 'delivered', 'completed'].includes(p.status) && (
                <button onClick={() => remove(f.id)} className="rounded-md p-1.5 text-muted hover:bg-bad-soft hover:text-bad" aria-label="Remove"><Trash2 className="size-4" /></button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={upload} className="flex flex-wrap items-end gap-3 border-t border-line-soft p-5 first:border-t-0">
        <Field label="Label" className="w-full sm:w-48"><Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Instagram Poster PNG" /></Field>
        <Field label="File" className="min-w-0 basis-full"><FileDrop key={dropKey} inputRef={file} accept="*/*" title="Drag and drop the final file here" hint="or click to browse. Any format: PNG, PDF, ZIP, PSD…" /></Field>
        <Button type="submit" variant={p.finals.length ? 'secondary' : 'primary'} loading={busy}><Upload className="size-4" /> Add final file</Button>
        {err && <div className="w-full"><ErrorNote error={err} /></div>}
      </form>
    </Panel>
  )
}

function InvoicePanel({ p }: { p: PD }) {
  const inv = p.invoice!
  return (
    <Panel title={`Invoice ${inv.number}`} actions={<Pill tone={inv.status === 'paid' ? 'ok' : inv.status === 'void' ? 'neutral' : 'warn'}>{inv.status === 'issued' ? 'Payment pending' : inv.status === 'paid' ? 'Paid' : 'Void'}</Pill>}>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-line-soft">
          {inv.items.map((i, n) => (
            <tr key={n}><td className="py-2">{i.description}{i.quantity > 1 ? ` × ${i.quantity}` : ''}</td><td className="py-2 text-right tabular-nums">{i.note ?? money(i.amount)}</td></tr>
          ))}
        </tbody>
      </table>
      <dl className="mt-3 ml-auto max-w-xs space-y-1 text-sm tabular-nums">
        <div className="flex justify-between text-ink-2"><dt>Subtotal</dt><dd>{money(inv.subtotal)}</dd></div>
        {inv.discount > 0 && <div className="flex justify-between text-ink-2"><dt>Discount</dt><dd>− {money(inv.discount)}</dd></div>}
        {inv.tax_rate_bp > 0 && <div className="flex justify-between text-ink-2"><dt>GST {inv.tax_rate_bp / 100}%</dt><dd>{money(inv.tax)}</dd></div>}
        <div className="flex justify-between border-t border-line pt-2 font-semibold"><dt>Total</dt><dd>{money(inv.total)}</dd></div>
        {inv.advance_paid > 0 && (
          <>
            <div className="flex justify-between text-ink-2"><dt>Advance received</dt><dd>− {money(inv.advance_paid)}</dd></div>
            <div className="flex justify-between font-semibold"><dt>{inv.status === 'paid' ? 'Paid' : 'Balance due'}</dt><dd>{money(inv.amount_due)}</dd></div>
          </>
        )}
      </dl>
      <p className="mt-3 text-xs text-muted">Issued {date(inv.issued_at)}{inv.paid_at ? `, paid ${date(inv.paid_at)}` : ''}</p>
    </Panel>
  )
}

// ---------- sidebar ----------

function ShareButtons({ item, number, label }: { item: ShareItem; number: string | null; label: string }) {
  return (
    <>
      <a href={waHref(number, item.message!)} target="_blank" rel="noreferrer" className={buttonCls('primary')}>
        <MessageCircle className="size-4" /> Share {label} link on WhatsApp
      </a>
      <CopyButton text={item.link!} label={`Copy ${label} link`} copied="Link copied" size="md" />
    </>
  )
}

function SharePanel({ p, onChange }: { p: PD; onChange: (p: PD) => void }) {
  const link = p.active_link
  const [open, setOpen] = useState(false)
  const [expiry, setExpiry] = useState('never')
  const [custom, setCustom] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const create = async () => {
    if (expiry === 'custom' && !custom) { setErr('Choose an expiry date and time.'); return }
    setBusy(true); setErr(null)
    try {
      const body = expiry === 'custom' ? { expires_at: new Date(custom).toISOString() } : { expiry }
      onChange(await api.post<PD>(`/api/projects/${p.id}/review-links`, body)); setOpen(false)
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const revoke = async () => {
    if (!link || !confirm('Revoke this link? The client will see "This review link is no longer active."')) return
    onChange(await api.post<PD>(`/api/review-links/${link.id}/revoke`))
  }
  const rows: [string, ShareItem][] = [['Review', p.share.review], ...(p.advance.status !== 'none' ? [['Advance', p.share.advance] as [string, ShareItem]] : []), ['Payment', p.share.payment], ['Delivery', p.share.delivery]]
  return (
    <Panel title="Client link" actions={link && <button onClick={revoke} className="text-[13px] text-muted hover:text-bad">Revoke</button>}>
      {!link ? (
        <div className="text-sm text-ink-2">
          <p>{p.versions.length ? 'No active link. Create one to share the project.' : 'A link is created when you upload the first version.'}</p>
          {p.versions.length > 0 && <Button className="mt-3" onClick={() => setOpen(true)}><Link2 className="size-4" /> Create link</Button>}
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 rounded-md bg-canvas px-3 py-2">
            <span className="min-w-0 flex-1 truncate text-[13px] text-ink-2">{link.url}</span>
          </div>
          <p className="mt-2 text-xs text-muted">
            {link.views ? `${link.views} view${link.views === 1 ? '' : 's'}, last ${relative(link.last_viewed_at).toLowerCase()}` : 'Not opened yet'}
            {' — '}{link.expires_at ? `expires ${dateTime(link.expires_at)}` : 'never expires'}
          </p>
          <ul className="mt-4 divide-y divide-line-soft border-y border-line-soft">
            {rows.map(([name, item]) => (
              <li key={name} className="flex items-center justify-between gap-2 py-2">
                <span className="text-sm">{name}</span>
                <span className="flex gap-1">
                  <CopyButton text={item.link!} label="Copy" copied={`${name} link copied`} variant="ghost" />
                  <a href={waHref(p.share.whatsapp_number, item.message!)} target="_blank" rel="noreferrer" className={buttonCls('ghost', 'sm')}>
                    <MessageCircle className="size-3.5" /> WhatsApp
                  </a>
                </span>
              </li>
            ))}
          </ul>
          <button onClick={() => setOpen(true)} className="mt-3 text-[13px] font-medium text-ink-2 hover:text-ink">Replace with a new link</button>
        </>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title={link ? 'Replace client link' : 'Create client link'}
        footer={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={create}>Create link</Button></>}>
        <div className="space-y-4">
          {link && <p className="text-sm text-ink-2">The current link stops working immediately.</p>}
          <Field label="Link expires">
            <Select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
              <option value="24h">In 24 hours</option><option value="3d">In 3 days</option><option value="7d">In 7 days</option>
              <option value="30d">In 30 days</option><option value="custom">On a date…</option><option value="never">Never</option>
            </Select>
          </Field>
          {expiry === 'custom' && <Field label="Expiry date and time"><Input type="datetime-local" value={custom} onChange={(e) => setCustom(e.target.value)} /></Field>}
          <ErrorNote error={err} />
        </div>
      </Modal>
    </Panel>
  )
}

function DetailsPanel({ p, staff }: { p: PD; staff?: boolean }) {
  const rows: [string, React.ReactNode][] = [
    ['Type', p.project_type],
    ['Canvas', p.width && p.height ? `${p.width} × ${p.height}` : null],
    ['Format', p.format],
    ['Quantity', p.quantity > 1 ? p.quantity : null],
    ['Deliverables', p.deliverable_types],
    ['Amount', staff ? null : money(p.amount)],
    ['Discount', !staff && p.discount ? money(p.discount) : null],
    ['GST', staff ? null : p.gst_enabled ? `${p.gst_rate_bp / 100}%` : 'Not applicable'],
    ['Revisions', p.deliverables.length > 1
      ? `${p.revisions_included} per design (${p.revisions_used} used so far)${!staff && p.extra_revision_price ? `, extra ${money(p.extra_revision_price)}` : ''}`
      : `${p.revisions_used} of ${p.revisions_included} used${!staff && p.extra_revision_price ? `, extra ${money(p.extra_revision_price)}` : ''}`],
    ['Advance', staff || p.advance.status === 'none' ? null : `${money(p.advance.amount)}, ${p.advance.status === 'paid' ? 'received' : p.advance.status === 'submitted' ? 'waiting for you to confirm' : 'not paid yet'}`],
    ['Payment terms', staff ? null : p.payment_terms],
    ['Description', p.description],
    ['Internal notes', p.internal_notes],
  ]
  return (
    <Panel title="Details">
      <dl className="space-y-2.5 text-sm">
        {rows.filter(([, v]) => v !== null && v !== '' && v !== undefined).map(([k, v]) => (
          <div key={k} className="grid grid-cols-[110px_1fr] gap-3">
            <dt className="text-muted">{k}</dt><dd className="min-w-0 break-words whitespace-pre-line">{v}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  )
}

function PaymentsPanel({ payments }: { payments: Payment[] }) {
  return (
    <Panel title="Payments" pad={false}>
      <ul className="divide-y divide-line-soft">
        {payments.map((x) => (
          <li key={x.id} className="px-5 py-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium tabular-nums">{money(x.amount)}</span>
              <Pill tone={x.status === 'confirmed' ? 'ok' : x.status === 'rejected' ? 'bad' : 'warn'}>
                {x.status === 'confirmed' ? 'Confirmed' : x.status === 'rejected' ? 'Not matched' : 'To confirm'}
              </Pill>
            </div>
            <div className="mt-0.5 text-xs text-muted">{x.reference ? `UPI ref ${x.reference}` : 'Screenshot'} — {dateTime(x.submitted_at)}</div>
            {x.admin_note && <div className="mt-1 text-xs text-ink-2">{x.admin_note}</div>}
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function Timeline({ p }: { p: PD }) {
  return (
    <Panel title="Timeline">
      <ol className="relative space-y-4 border-l border-line pl-5">
        {[...p.activity].reverse().map((a) => (
          <li key={a.id} className="relative">
            <span className={cx('absolute top-1.5 -left-[23.5px] size-2 rounded-full ring-4 ring-surface',
              a.actor === 'client' ? 'bg-brand' : a.actor === 'system' ? 'bg-faint' : 'bg-ink')} />
            <div className="text-sm text-ink">{a.message}</div>
            <div className="text-xs text-muted">{dateTime(a.created_at)}{a.actor === 'client' ? ' — client' : ''}</div>
          </li>
        ))}
      </ol>
    </Panel>
  )
}
