import { ArrowLeft, ExternalLink, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DownloadButtons } from '../../components/QuoteDocument'
import { Button, CopyButton, ErrorNote, Field, Input, Panel, Pill, Spinner, Switch, Textarea, buttonCls, useToast } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api, ApiError } from '../../services/api'
import type { InvoiceDetail as ID, InvoiceDoc } from '../../types'
import { date, money, relative, toPaise, toRupees } from '../../utils/format'
import { BrandMark } from '../client/Portal'

const tone = (s: string) => (s === 'paid' ? 'ok' : s === 'void' ? 'neutral' : 'warn')
const label = (s: string) => (s === 'paid' ? 'Paid' : s === 'void' ? 'Void' : 'Payment pending')

export default function InvoiceDetail() {
  const { id } = useParams()
  const { data: inv, setData, error, loading } = useAsync(() => api.get<ID>(`/api/invoices/${id}`), [id], { poll: 10000 })
  const [editing, setEditing] = useState(false)
  if (loading) return <Spinner />
  if (error || !inv) return <ErrorNote error={error?.message} />

  return (
    <>
      <Link to="/invoices" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft className="size-3.5" /> Invoices</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] tabular-nums">{inv.number}</h1>
            <Pill tone={tone(inv.status)}>{label(inv.status)}</Pill>
          </div>
          <p className="mt-1 text-sm text-ink-2">
            <Link to={`/projects/${inv.project.id}`} className="underline underline-offset-2">{inv.project.name}</Link>
            <span className="text-muted"> · {inv.project.client}</span>
          </p>
        </div>
        {!editing && (
          <div className="flex flex-wrap items-center gap-2">
            <DownloadButtons base={`/api/invoices/${inv.id}/download`} />
            {inv.editable && <Button variant="primary" size="sm" onClick={() => setEditing(true)}><Pencil className="size-3.5" /> Edit invoice</Button>}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          {editing
            ? <EditForm inv={inv} onCancel={() => setEditing(false)} onSaved={(next) => { setData(next); setEditing(false) }} />
            : <InvoiceDocument doc={inv.document} />}
        </div>
        <div className="min-w-0 space-y-6">
          <Panel title="Details">
            <dl className="space-y-2.5 text-sm">
              <Row k="Total">{money(inv.total)}</Row>
              {inv.advance_paid > 0 && <Row k="Advance paid">{money(inv.advance_paid)}</Row>}
              <Row k={inv.status === 'paid' ? 'Paid' : 'Due'}>{money(inv.amount_due)}</Row>
              <Row k="Issued">{date(inv.issued_at)}</Row>
              {inv.paid_at && <Row k="Paid on">{date(inv.paid_at)}</Row>}
            </dl>
            {!inv.editable && inv.status === 'issued' && (
              <p className="mt-4 text-[13px] text-ink-2">A payment is waiting for your confirmation, so editing is paused. Confirm or reject it on the project first.</p>
            )}
            {inv.status === 'paid' && <p className="mt-4 text-[13px] text-ink-2">Paid invoices are a record, so they can't be edited.</p>}
          </Panel>
          {inv.link && (
            <Panel title="Client link">
              <p className="break-all text-[13px] text-ink-2">{inv.link}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <CopyButton text={inv.link} label="Copy link" copied="Link copied" />
                <a href={inv.link} target="_blank" rel="noreferrer" className={buttonCls('secondary', 'sm')}>Open <ExternalLink className="size-3.5" /></a>
              </div>
            </Panel>
          )}
          {inv.advances.length > 0 && (
            <Panel title="Advance received">
              <ul className="divide-y divide-line-soft text-sm">
                {inv.advances.map((a) => (
                  <li key={a.id} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <div className="font-medium tabular-nums">{money(a.amount)} <span className="font-normal text-muted">on {date(a.received_on)}</span></div>
                      {a.note && <div className="text-[13px] text-ink-2">{a.note}</div>}
                      {a.reference && <div className="text-xs text-muted">Ref {a.reference}</div>}
                    </div>
                    {a.proof_file_id && <a href={`/api/admin/files/${a.proof_file_id}?inline=1`} target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-1 text-[13px] font-medium underline underline-offset-2">Screenshot <ExternalLink className="size-3" /></a>}
                  </li>
                ))}
              </ul>
              {inv.advances.filter((a) => a.proof_file_id).map((a) => (
                <a key={a.id} href={`/api/admin/files/${a.proof_file_id}?inline=1`} target="_blank" rel="noreferrer" className="mt-3 block overflow-hidden rounded-lg border border-line-soft">
                  <img src={`/api/admin/files/${a.proof_file_id}?inline=1`} alt={`Payment screenshot, ${money(a.amount)}`} className="max-h-72 w-full object-cover object-top" />
                </a>
              ))}
            </Panel>
          )}
          {inv.payments.length > 0 && (
            <Panel title="Payments">
              <ul className="space-y-3 text-sm">
                {inv.payments.map((p) => (
                  <li key={p.id}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium tabular-nums">{money(p.amount)}</span>
                      <Pill tone={p.status === 'confirmed' ? 'ok' : p.status === 'rejected' ? 'bad' : 'warn'}>{p.status === 'confirmed' ? 'Confirmed' : p.status === 'rejected' ? 'Not matched' : 'To confirm'}</Pill>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">{p.reference ? `UPI ref ${p.reference}` : 'Screenshot'} · {relative(p.submitted_at)}</div>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </>
  )
}

const Row = ({ k, children }: { k: string; children: React.ReactNode }) => (
  <div className="grid grid-cols-[100px_1fr] gap-3"><dt className="text-muted">{k}</dt><dd className="min-w-0 break-words tabular-nums">{children}</dd></div>
)
const Line = ({ label, value }: { label: string; value: string }) => <div className="flex justify-between text-ink-2"><dt>{label}</dt><dd>{value}</dd></div>

/** The invoice itself, as the client receives it. */
function InvoiceDocument({ doc }: { doc: InvoiceDoc }) {
  const t = doc.totals
  const paid = doc.status === 'paid'
  const b = doc.brand
  return (
    <article className="min-w-0 rounded-xl border border-line bg-surface p-5 sm:p-10">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <BrandMark brand={b} large />
          {b.address && <p className="mt-2 max-w-[30ch] text-[13px] whitespace-pre-line text-muted">{b.address}</p>}
          {b.gstin && <p className="mt-1 text-[13px] text-muted">GSTIN {b.gstin}</p>}
        </div>
        <div className="sm:text-right">
          <h2 className="text-[22px] font-semibold tracking-[-0.02em]">Invoice</h2>
          <p className="text-sm text-ink-2 tabular-nums">#{doc.number}</p>
          <p className="mt-1 text-[13px] text-muted">Issued {date(doc.issued_at)}</p>
          {paid && doc.paid_at && <p className="text-[13px] font-semibold text-ok">PAID on {date(doc.paid_at)}</p>}
        </div>
      </div>

      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        <div>
          <h3 className="text-[13px] text-muted">Bill to</h3>
          <p className="mt-1 font-medium">{doc.bill_to.name}</p>
          {doc.bill_to.contact && doc.bill_to.contact !== doc.bill_to.name && <p className="text-sm text-ink-2">{doc.bill_to.contact}</p>}
          {doc.bill_to.address && <p className="text-sm whitespace-pre-line text-ink-2">{doc.bill_to.address}</p>}
          {doc.bill_to.gstin && <p className="text-sm text-ink-2">GSTIN {doc.bill_to.gstin}</p>}
        </div>
        <div>
          <h3 className="text-[13px] text-muted">Project</h3>
          <p className="mt-1 font-medium">{doc.project.name}</p>
          <p className="text-sm text-ink-2">#{doc.project.code}</p>
        </div>
      </div>

      <div className="mt-8 flex justify-between border-b border-line pb-2 text-[13px] text-muted"><span>Description</span><span>Amount</span></div>
      <ul className="divide-y divide-line-soft">
        {doc.items.map((it, i) => (
          <li key={i} className="flex items-start justify-between gap-4 py-3.5 text-sm">
            <div className="min-w-0">
              <div className="break-words text-ink">{it.description}</div>
              {it.quantity > 1 && <div className="text-xs text-muted">{it.quantity} × {money(it.unit_price)}</div>}
            </div>
            <div className="shrink-0 font-medium tabular-nums">{it.note ?? money(it.amount)}</div>
          </li>
        ))}
      </ul>

      <dl className="mt-4 ml-auto max-w-xs space-y-1.5 text-sm tabular-nums">
        <Line label="Subtotal" value={money(t.subtotal)} />
        {t.discount > 0 && <Line label="Discount" value={`− ${money(t.discount)}`} />}
        {t.tax_rate_bp > 0 && <Line label={`GST ${t.tax_rate_bp / 100}%`} value={money(t.tax)} />}
        <div className="flex justify-between border-t border-line pt-3 text-base font-semibold"><dt>Total</dt><dd>{money(t.total)}</dd></div>
        {t.advance_paid > 0 && (
          <>
            <Line label="Advance received" value={`− ${money(t.advance_paid)}`} />
            <div className="flex justify-between text-base font-semibold"><dt>{paid ? 'Paid' : 'Balance due'}</dt><dd>{money(t.amount_due)}</dd></div>
          </>
        )}
      </dl>
      {t.advance_paid > 0 && doc.advances.length > 0 && (
        <ul className="mt-2 ml-auto max-w-xs space-y-0.5 text-right text-xs text-muted">
          {doc.advances.map((a, i) => <li key={i}>Received {money(a.amount)} on {date(a.received_on)}{a.reference && ` · Ref ${a.reference}`}</li>)}
        </ul>
      )}

      {doc.notes && <div className="mt-8 text-sm"><h3 className="text-[13px] text-muted">Notes</h3><p className="mt-1 whitespace-pre-line">{doc.notes}</p></div>}
      {!paid && doc.payment_terms && <p className="mt-6 text-[13px] text-muted">{doc.payment_terms}</p>}
      {doc.payment && (
        <div className="mt-8 flex flex-wrap items-center gap-5 rounded-lg border border-line-soft p-4">
          <img src={doc.payment.qr} alt="UPI QR code to pay" className="size-28 shrink-0" />
          <div className="min-w-0 text-sm">
            <h3 className="font-semibold">Pay {money(t.amount_due)} by UPI</h3>
            <p className="mt-0.5 text-[13px] text-muted">Scan with any UPI app. The amount is filled in for you.</p>
            <p className="mt-1 font-semibold break-all">{doc.payment.upi_id}</p>
            <p className="text-[13px] text-muted">{doc.payment.payee}. Reference {doc.number}.</p>
          </div>
        </div>
      )}
      {doc.closing && (
        <div className="mt-8 rounded-lg bg-[color-mix(in_srgb,var(--brand)_8%,white)] p-4 text-sm">
          <p className="text-[13px] text-muted">A note from {b.name}</p>
          <p className="mt-1 whitespace-pre-line text-ink">{doc.closing}</p>
        </div>
      )}
    </article>
  )
}

interface L { description: string; quantity: string; unit: string; note: string }

function EditForm({ inv, onCancel, onSaved }: { inv: ID; onCancel: () => void; onSaved: (i: ID) => void }) {
  const toast = useToast()
  const [lines, setLines] = useState<L[]>(inv.items.map((i) => ({ description: i.description, quantity: String(i.quantity), unit: String(toRupees(i.unit_price)), note: i.note ?? '' })))
  const [discount, setDiscount] = useState(String(toRupees(inv.discount)))
  const [gst, setGst] = useState(inv.gst_enabled)
  const [rate, setRate] = useState(String(inv.gst_rate_bp / 100))
  const [notes, setNotes] = useState(inv.notes ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const amount = (l: L) => Math.max(1, Number(l.quantity) || 1) * toPaise(l.unit)
  const subtotal = lines.reduce((s, l) => s + amount(l), 0)
  const disc = Math.max(0, Math.min(toPaise(discount), subtotal))
  const tax = gst ? Math.floor(((subtotal - disc) * Math.round(Number(rate || 0) * 100) + 5000) / 10000) : 0
  const total = subtotal - disc + tax
  const discountError = toPaise(discount) > subtotal ? `A discount can't be more than the subtotal (${money(subtotal)}).` : null
  const belowAdvance = total < inv.advance_paid ? `The client already paid ${money(inv.advance_paid)} as an advance, so the total can't be lower than that.` : null
  const set = (i: number, patch: Partial<L>) => setLines(lines.map((l, n) => (n === i ? { ...l, ...patch } : l)))

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const next = await api.put<ID>(`/api/invoices/${inv.id}`, {
        items: lines.map((l) => ({ description: l.description, quantity: Math.max(1, Number(l.quantity) || 1), unit_price: toPaise(l.unit), note: l.note || null })),
        discount: toPaise(discount), gst_enabled: gst, gst_rate_bp: Math.round(Number(rate || 0) * 100), notes,
      })
      toast('Invoice updated')
      onSaved(next)
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-6">
      <Panel title="Edit invoice">
        <p className="mb-4 text-[13px] text-ink-2">Changes show on the client's invoice page straight away. If you issue the invoice again from the project, it is rebuilt from the project price and these edits are replaced.</p>
        <div className="space-y-3">
          {lines.map((l, i) => (
            <div key={i} className="rounded-lg border border-line-soft p-3">
              <div className="grid gap-3 sm:grid-cols-[1fr_80px_130px]">
                <Field label="Description"><Input value={l.description} onChange={(e) => set(i, { description: e.target.value })} maxLength={255} /></Field>
                <Field label="Qty"><Input type="number" min={1} value={l.quantity} onChange={(e) => set(i, { quantity: e.target.value })} inputMode="numeric" /></Field>
                <Field label="Price (₹)"><Input type="number" min={0} step="any" value={l.unit} onChange={(e) => set(i, { unit: e.target.value })} inputMode="decimal" /></Field>
              </div>
              <div className="mt-2 flex items-end justify-between gap-3">
                <Field label="Show instead of the amount (optional)" className="max-w-[240px] flex-1"><Input value={l.note} onChange={(e) => set(i, { note: e.target.value })} placeholder="e.g. Included" maxLength={60} /></Field>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium tabular-nums">{money(amount(l))}</span>
                  <Button size="sm" variant="ghost" onClick={() => setLines(lines.filter((_, n) => n !== i))} disabled={lines.length === 1} aria-label="Remove line"><Trash2 className="size-4" /></Button>
                </div>
              </div>
            </div>
          ))}
          <Button size="sm" onClick={() => setLines([...lines, { description: '', quantity: '1', unit: '', note: '' }])}><Plus className="size-3.5" /> Add line</Button>
        </div>
      </Panel>

      <Panel title="Discount, GST and notes">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Discount (₹)" hint={discountError ? <span className="text-bad">{discountError}</span> : undefined}>
            <Input type="number" min={0} step="any" value={discount} onChange={(e) => setDiscount(e.target.value)} inputMode="decimal" />
          </Field>
          <div className="flex items-end gap-4">
            <Switch checked={gst} onChange={setGst} label="Charge GST" />
            {gst && <Field label="Rate (%)" className="w-24"><Input type="number" min={0} max={50} step="any" value={rate} onChange={(e) => setRate(e.target.value)} /></Field>}
          </div>
          <Field label="Notes on the invoice (optional)" className="sm:col-span-2"><Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} /></Field>
        </div>
        <dl className="mt-5 ml-auto max-w-xs space-y-1.5 text-sm tabular-nums">
          <Line label="Subtotal" value={money(subtotal)} />
          {disc > 0 && <Line label="Discount" value={`− ${money(disc)}`} />}
          {gst && <Line label={`GST ${rate}%`} value={money(tax)} />}
          <div className="flex justify-between border-t border-line pt-3 text-base font-semibold"><dt>Total</dt><dd>{money(total)}</dd></div>
          {inv.advance_paid > 0 && <>
            <Line label="Advance received" value={`− ${money(inv.advance_paid)}`} />
            <div className="flex justify-between font-semibold"><dt>Balance due</dt><dd>{money(Math.max(0, total - inv.advance_paid))}</dd></div>
          </>}
        </dl>
        <div className="mt-4"><ErrorNote error={err ?? belowAdvance} /></div>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save} disabled={!!discountError || !!belowAdvance}>Save changes</Button>
        </div>
      </Panel>
    </div>
  )
}
