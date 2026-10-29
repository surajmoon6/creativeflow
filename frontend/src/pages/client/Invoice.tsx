import { CircleCheck, Clock, Printer } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PaymentProof from '../../components/PaymentProof'
import UpiApps from '../../components/UpiApps'
import { Button, CopyButton, buttonCls } from '../../components/ui'
import { api } from '../../services/api'
import type { ClientView } from '../../types'
import { date, dateTime, money } from '../../utils/format'
import { BrandMark, usePortal } from './Portal'

export default function InvoicePage() {
  const { view, token, refresh } = usePortal()
  const inv = view.invoice
  // While a payment awaits the studio's confirmation, check back quietly.
  const waiting = !!view.payment?.pending
  useEffect(() => {
    if (!waiting) return
    const t = window.setInterval(refresh, 15000)
    return () => window.clearInterval(t)
  }, [waiting, refresh])

  if (!inv) return <p className="text-ink-2">The invoice isn't ready yet.</p>
  const paid = inv.status === 'paid'

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-8">
      <article className="min-w-0 rounded-xl border border-line bg-surface p-5 sm:p-10 print:border-0 print:p-0">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <BrandMark brand={view.brand} large />
            {view.brand.address && <p className="mt-2 max-w-[28ch] text-[13px] whitespace-pre-line text-muted">{view.brand.address}</p>}
            {view.brand.gstin && <p className="mt-1 text-[13px] text-muted">GSTIN {view.brand.gstin}</p>}
          </div>
          <div className="sm:text-right">
            <h2 className="text-[22px] font-semibold tracking-[-0.02em]">Invoice</h2>
            <p className="text-sm text-ink-2 tabular-nums">#{inv.number}</p>
            <p className="mt-1 text-[13px] text-muted">Issued {date(inv.issued_at)}</p>
          </div>
        </div>

        <div className="mt-8 grid gap-6 sm:grid-cols-2">
          <div>
            <h3 className="text-[13px] text-muted">Bill to</h3>
            <p className="mt-1 font-medium">{inv.bill_to?.name}</p>
            {inv.bill_to?.contact && inv.bill_to.contact !== inv.bill_to.name && <p className="text-sm text-ink-2">{inv.bill_to.contact}</p>}
            {inv.bill_to?.address && <p className="text-sm whitespace-pre-line text-ink-2">{inv.bill_to.address}</p>}
            {inv.bill_to?.gstin && <p className="text-sm text-ink-2">GSTIN {inv.bill_to.gstin}</p>}
          </div>
          <div>
            <h3 className="text-[13px] text-muted">Project</h3>
            <p className="mt-1 font-medium">{view.name}</p>
            <p className="text-sm text-ink-2">#{view.code}</p>
          </div>
        </div>

        <table className="mt-8 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-[13px] text-muted">
              <th className="pb-2 font-normal">Description</th>
              <th className="hidden pb-2 text-right font-normal sm:table-cell">Qty</th>
              <th className="pb-2 text-right font-normal">Amount</th>
            </tr>
          </thead>
          <tbody>
            {inv.items.map((it, i) => (
              <tr key={i} className="border-b border-line-soft align-top">
                <td className="py-3 pr-4">
                  {it.description}
                  {it.quantity > 1 && <span className="block text-xs text-muted sm:hidden">{it.quantity} × {money(it.unit_price)}</span>}
                </td>
                <td className="hidden py-3 text-right tabular-nums text-ink-2 sm:table-cell">{it.quantity}</td>
                <td className="py-3 text-right tabular-nums">{it.note ?? money(it.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="mt-4 ml-auto max-w-xs space-y-1.5 text-sm tabular-nums">
          <Row label="Subtotal" value={money(inv.subtotal)} />
          {inv.discount > 0 && <Row label="Discount" value={`− ${money(inv.discount)}`} />}
          {inv.tax_rate_bp > 0 && <Row label={`GST ${inv.tax_rate_bp / 100}%`} value={money(inv.tax)} />}
          <div className="flex justify-between border-t border-line pt-3 text-base font-semibold">
            <dt>Total</dt><dd>{money(inv.total)}</dd>
          </div>
          {inv.advance_paid > 0 && (
            <>
              <Row label="Advance received" value={`− ${money(inv.advance_paid)}`} />
              <div className="flex justify-between text-base font-semibold">
                <dt>{paid ? 'Paid' : 'Balance due'}</dt><dd>{money(inv.amount_due)}</dd>
              </div>
            </>
          )}
        </dl>

        {inv.notes && (
          <div className="mt-8 text-sm"><h3 className="text-[13px] text-muted">Notes</h3><p className="mt-1 whitespace-pre-line">{inv.notes}</p></div>
        )}

        {!paid && view.payment?.has_qr && (
          <div className="mt-8 hidden items-center gap-5 border-t border-line-soft pt-5 print:flex">
            <img src={`/api/r/${token}/payment-qr.png`} alt="UPI QR code for this invoice" className="size-32 shrink-0" />
            <div className="text-sm">
              <h3 className="font-semibold">Pay {money(inv.amount_due)} by UPI</h3>
              <p className="mt-0.5 text-[13px] text-muted">Scan with any UPI app. The amount is filled in for you.</p>
              {view.payment.upi_id && <p className="mt-1 font-semibold">{view.payment.upi_id}</p>}
              <p className="text-[13px] text-muted">{view.payment.payee}. Reference {inv.number}.</p>
            </div>
          </div>
        )}

        {inv.closing && (
          <div className="mt-8 rounded-lg bg-[color-mix(in_srgb,var(--brand)_8%,white)] p-4 text-sm">
            <p className="text-[13px] text-muted">A note from {view.brand.name}</p>
            <p className="mt-1 whitespace-pre-line text-ink">{inv.closing}</p>
          </div>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-5 text-[13px] text-muted">
          <span>{paid ? `Paid on ${date(inv.paid_at)}` : inv.payment_terms}</span>
          <Button size="sm" variant="ghost" className="no-print" onClick={() => window.print()}>
            <Printer className="size-3.5" /> Print or save as PDF
          </Button>
        </div>
      </article>

      <aside id="pay" className="no-print order-first lg:sticky lg:top-6 lg:order-none">
        <PaymentPanel view={view} token={token} onSubmitted={refresh} />
      </aside>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between text-ink-2"><dt>{label}</dt><dd>{value}</dd></div>
}

function PaymentPanel({ view, token, onSubmitted }: { view: ClientView; token: string; onSubmitted: () => Promise<void> }) {
  const inv = view.invoice!
  const pay = view.payment!
  const [upiUri, setUpiUri] = useState<string | null>(null)
  useEffect(() => {
    if (pay.upi_id && inv.status === 'issued') api.get<{ uri: string | null }>(`/api/r/${token}/upi-uri`).then((r) => setUpiUri(r.uri)).catch(() => {})
  }, [pay.upi_id, inv.status, token])

  if (inv.status === 'paid' || pay.confirmed) {
    return (
      <Box>
        <h2 className="flex items-center gap-2 font-semibold"><CircleCheck className="size-5 text-ok" /> Payment received</h2>
        <p className="mt-1 text-sm text-ink-2">Your final files are ready.</p>
        <Link to="../delivery" relative="path" className={buttonCls('brand', 'lg', 'mt-4 w-full')}>Download deliverables</Link>
      </Box>
    )
  }
  if (pay.pending) {
    return (
      <Box>
        <h2 className="flex items-center gap-2 font-semibold"><Clock className="size-5 text-warn" /> Payment details received</h2>
        <p className="mt-2 text-sm text-ink-2">
          Thank you. The studio will confirm your payment and your final files will appear on this page.
        </p>
        <dl className="mt-4 space-y-1 text-[13px]">
          <div className="flex justify-between gap-4"><dt className="text-muted">Reference</dt><dd className="font-medium tabular-nums">{pay.pending.reference || 'Screenshot uploaded'}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">Submitted</dt><dd>{dateTime(pay.pending.submitted_at)}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-muted">Amount</dt><dd className="tabular-nums">{money(pay.pending.amount)}</dd></div>
        </dl>
      </Box>
    )
  }

  return (
    <Box>
      <h2 className="font-semibold">Complete payment</h2>
      <p className="mt-1 text-sm text-ink-2">Complete the project payment to unlock your final deliverables.</p>
      <div className="mt-4 flex items-baseline justify-between border-y border-line-soft py-3">
        <span className="text-sm text-muted">{inv.advance_paid > 0 ? 'Balance due' : 'Amount'}</span>
        <span className="text-xl font-semibold tabular-nums">{money(inv.amount_due)}</span>
      </div>

      {pay.last_rejected && (
        <p className="mt-4 rounded-md bg-bad-soft px-3 py-2 text-[13px] text-bad">
          The studio couldn't match your last payment details{pay.last_rejected.reference ? ` (${pay.last_rejected.reference})` : ''}.
          {pay.last_rejected.admin_note ? ` ${pay.last_rejected.admin_note}` : ''} Please check and submit again.
        </p>
      )}

      <ol className="mt-5 space-y-6">
        <li>
          <Step n={1}>Pay with any UPI app</Step>
          {pay.has_qr ? (
            <>
              {upiUri && <UpiApps uri={upiUri} className="mt-3" />}
              <div>
                <div className="mt-3 flex justify-center rounded-lg border border-line-soft p-3">
                  <img src={`/api/r/${token}/payment-qr.png`} alt="UPI QR code for this invoice" className="size-48" />
                </div>
                <p className="mt-2 text-center text-xs text-muted">Scan with Google Pay, PhonePe, Paytm or your bank app. The amount is filled in for you. On this phone? Take a screenshot and pick it from your gallery inside the app's scanner.</p>
              </div>
            </>
          ) : (
            <p className="mt-2 text-sm text-ink-2">The studio will share payment details with you.</p>
          )}
          {pay.upi_id && (
            <div className="mt-3 flex items-center justify-between gap-2 rounded-md bg-canvas px-3 py-2">
              <div className="min-w-0">
                <div className="text-xs text-muted">UPI ID — {pay.payee}</div>
                <div className="truncate text-sm font-medium">{pay.upi_id}</div>
              </div>
              <CopyButton text={pay.upi_id} copied="UPI ID copied" />
            </div>
          )}
        </li>
        <li>
          <Step n={2}>Show us your payment</Step>
          <PaymentProof whatsapp={view.brand.whatsapp}
            waText={`Hi, I've paid ${money(inv.amount_due)} for invoice ${inv.number} (${view.name}, #${view.code}). Sharing the payment screenshot here.`}
            onSubmit={async (fd) => { await api.post(`/api/r/${token}/payments`, fd); await onSubmitted() }} />
        </li>
      </ol>
    </Box>
  )
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 text-sm font-medium">
      <span className="flex size-5 items-center justify-center rounded-full bg-ink text-[11px] text-white tabular-nums">{n}</span>
      {children}
    </div>
  )
}

const Box = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-xl border border-line bg-surface p-5 sm:p-6">{children}</div>
)
