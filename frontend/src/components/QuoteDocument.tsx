import { Download } from 'lucide-react'
import type { QuoteDoc } from '../types'
import { date, money } from '../utils/format'
import { BrandMark } from '../pages/client/Portal'
import { CopyButton, buttonCls } from './ui'
import UpiApps from './UpiApps'

/** PDF and image downloads of the quote. `base` is the endpoint that serves them. */
export function DownloadButtons({ base }: { base: string }) {
  return (
    <div className="no-print flex flex-wrap gap-2">
      <a href={`${base}?format=pdf`} download className={buttonCls('secondary', 'sm')}><Download className="size-3.5" /> Download PDF</a>
      <a href={`${base}?format=png`} download className={buttonCls('secondary', 'sm')}><Download className="size-3.5" /> Download image</a>
    </div>
  )
}

/** The scope of work. In a section's lines, "# " is a subheading and "> " a note; anything else is a bullet. */
function SectionLines({ lines }: { lines: string[] }) {
  return (
    <ul className="mt-1.5 space-y-1 text-sm text-ink-2">
      {lines.map((ln, n) => ln.startsWith('# ') ? <li key={n} className="pt-1.5 font-semibold text-ink">{ln.slice(2)}</li>
        : ln.startsWith('> ') ? <li key={n} className="rounded-md bg-canvas px-3 py-2 text-[13px] text-muted">{ln.slice(2)}</li>
        : ln.startsWith('~ ') ? <li key={n}>{ln.slice(2)}</li>
        : <li key={n} className="flex gap-2"><span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-faint" /><span className="min-w-0">{ln}</span></li>)}
    </ul>
  )
}

export function ScopeOfWork({ sections }: { sections: QuoteDoc['sections'] }) {
  const scope = (sections ?? []).filter((s) => s.part !== 'after' && s.part !== 'appendix')
  if (!scope.length) return null
  return (
    <div className="mt-8">
      <h3 className="text-[13px] text-muted">Scope of work</h3>
      <div className="mt-2 space-y-5">
        {scope.map((s, i) => (
          <section key={i}>
            <h4 className="text-[15px] font-semibold text-brand">{i + 1}. {s.title}</h4>
            <SectionLines lines={s.lines} />
          </section>
        ))}
      </div>
    </div>
  )
}

/** Blocks the studio places after the pricing: payment terms, third-party costs and the like. */
export function AfterSections({ sections }: { sections: QuoteDoc['sections'] }) {
  const after = (sections ?? []).filter((s) => s.part === 'after')
  if (!after.length) return null
  return (
    <div className="mt-6 space-y-5">
      {after.map((s, i) => (
        <section key={i}>
          <h4 className="text-[15px] font-semibold text-ink">{s.title}</h4>
          <SectionLines lines={s.lines} />
        </section>
      ))}
    </div>
  )
}

/** The closing page: why the services work together, what the client gains and what can go wrong without each. */
export function AppendixSections({ sections }: { sections: QuoteDoc['sections'] }) {
  const items = (sections ?? []).filter((s) => s.part === 'appendix')
  if (!items.length) return null
  return (
    <div className="mt-10 space-y-4 border-t border-line pt-8 print:break-before-page">
      {items.map((s, i) => s.tone === 'title' ? (
        <div key={i}>
          <h3 className="text-[22px] leading-tight font-semibold tracking-[-0.02em] text-ink">{s.title}</h3>
          <div className="mt-2 space-y-2 text-[15px] text-ink-2">{s.lines.map((ln, n) => <p key={n}>{ln.replace(/^[~>#]\s/, '')}</p>)}</div>
        </div>
      ) : (
        <section key={i} className={s.tone === 'gain' ? 'rounded-lg bg-ok-soft p-4' : s.tone === 'caution' ? 'rounded-lg bg-warn-soft p-4' : 'rounded-lg border border-line-soft p-4'}>
          <h4 className={`text-[15px] font-semibold ${s.tone === 'gain' ? 'text-ok' : s.tone === 'caution' ? 'text-warn' : 'text-ink'}`}>{s.title}</h4>
          <SectionLines lines={s.lines} />
        </section>
      ))}
    </div>
  )
}

/** The quotation itself. The studio previews exactly what the client receives. */
export function QuoteDocument({ doc }: { doc: QuoteDoc }) {
  const t = doc.totals
  const b = doc.brand
  return (
    <article className="min-w-0 rounded-xl border border-line bg-surface p-5 sm:p-10 print:border-0 print:p-0">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <BrandMark brand={b} large />
          {b.address && <p className="mt-2 max-w-[30ch] text-[13px] whitespace-pre-line text-muted">{b.address}</p>}
          {b.gstin && <p className="mt-1 text-[13px] text-muted">GSTIN {b.gstin}</p>}
        </div>
        <div className="sm:text-right">
          <h2 className="text-[22px] font-semibold tracking-[-0.02em]">Quotation</h2>
          <p className="text-sm text-ink-2 tabular-nums">#{doc.number}</p>
          <p className="mt-1 text-[13px] text-muted">Date {date(doc.issued_at)}</p>
          <p className="text-[13px] font-medium text-ink-2">Valid until {date(doc.valid_until)}</p>
        </div>
      </div>

      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        <div>
          <h3 className="text-[13px] text-muted">Prepared for</h3>
          <p className="mt-1 font-medium">{doc.bill_to.name}</p>
          {doc.bill_to.contact && doc.bill_to.contact !== doc.bill_to.name && <p className="text-sm text-ink-2">{doc.bill_to.contact}</p>}
          {doc.bill_to.address && <p className="text-sm whitespace-pre-line text-ink-2">{doc.bill_to.address}</p>}
          {doc.bill_to.gstin && <p className="text-sm text-ink-2">GSTIN {doc.bill_to.gstin}</p>}
        </div>
        <div>
          <h3 className="text-[13px] text-muted">Project</h3>
          <p className="mt-1 font-medium">{doc.title}</p>
        </div>
      </div>

      {doc.scope_first !== false && <ScopeOfWork sections={doc.sections} />}

      <div className="mt-8 flex justify-between border-b border-line pb-2 text-[13px] text-muted">
        <span>Description</span><span>Amount</span>
      </div>
      <ul className="divide-y divide-line-soft">
        {doc.items.map((it, i) => (
          <li key={i} className="flex items-start justify-between gap-4 py-3.5 text-sm">
            <div className="min-w-0">
              <div className="break-words text-ink">{it.description}</div>
              {it.list_price ? <div className="mt-0.5 text-xs font-semibold text-ok">Special client offer</div> : null}
              {it.detail && <div className="mt-0.5 text-[13px] whitespace-pre-line text-muted">{it.detail}</div>}
              {it.complimentary
                ? <div className="mt-0.5 text-xs font-semibold text-ok">Complimentary{it.quantity > 1 ? `, ${it.quantity} ×` : ''}</div>
                : it.quantity > 1 && <div className="mt-0.5 text-xs text-muted tabular-nums">{it.quantity} × {money(it.unit_price)}</div>}
            </div>
            {it.complimentary ? (
              <div className="shrink-0 text-right tabular-nums">
                {it.value > 0 && <div className="text-xs text-muted line-through">{money(it.value)}</div>}
                <div className="font-semibold text-ok">FREE</div>
              </div>
            ) : (
              <div className="shrink-0 text-right tabular-nums">
                {it.list_price ? <div className="text-xs font-normal text-muted line-through">{money(it.list_price * it.quantity)}</div> : null}
                {money(it.amount)}
                {doc.mode === 'mixed' && <div className="text-xs font-normal text-muted">{it.period === 'monthly' ? 'per month' : 'one-time'}</div>}
              </div>
            )}
          </li>
        ))}
      </ul>

      <dl className="mt-4 ml-auto max-w-xs space-y-1.5 text-sm tabular-nums">
        {doc.mode === 'mixed'
          ? <><div className="flex justify-between font-semibold text-ink"><dt>Monthly recurring fee</dt><dd>{money(t.recurring)}/month</dd></div><Row label="One-time fees" value={money(t.one_time)} /></>
          : <Row label="Subtotal" value={money(t.subtotal)} />}
        {t.discount > 0 && <Row label={doc.discount_label || 'Discount'} value={`− ${money(t.discount)}`} />}
        {t.tax_rate_bp > 0 && <Row label={`GST ${t.tax_rate_bp / 100}%`} value={money(t.tax)} />}
        <div className="flex justify-between border-t border-line pt-3 text-base font-semibold">
          <dt>{doc.mode === 'monthly' || (doc.mode === undefined && doc.billing === 'monthly') ? 'Total per month' : doc.mode === 'mixed' ? (doc.recurring_start === 'launch' ? 'Initial payment' : 'Total initial payment') : 'Total'}</dt><dd>{money(t.total)}</dd>
        </div>
      </dl>
      {doc.mode === 'mixed' && doc.recurring_start === 'launch' && (
        <p className="mt-3 text-[13px] text-muted">The initial payment is the one-time fees only. The monthly fee of {money(t.recurring)} is not charged until the website is launched and the monthly service is activated. It is then payable in advance at the start of each monthly period.</p>
      )}
      {doc.mode === 'mixed' && doc.recurring_start !== 'launch' && t.discount === 0 && t.tax_rate_bp === 0 && (
        <p className="mt-3 text-[13px] text-muted">The initial payment is the one-time fees ({money(t.one_time)}) plus the first month of recurring services ({money(t.recurring)}) = {money(t.total)}. From the second month, {money(t.recurring)} is payable at the start of each billing cycle.</p>
      )}

      {t.discount > 0 && doc.discount_label && (
        <p className="mt-3 text-right text-sm font-semibold text-ok">You save {money(t.discount)}{doc.billing === 'monthly' ? ' every month' : ''} with this special offer</p>
      )}

      {t.savings_monthly > 0 && <p className="mt-3 text-right text-sm font-semibold text-ok">You save {money(t.savings_monthly)} every month with the special offer</p>}
      {t.savings_once > 0 && <p className="mt-1 text-right text-sm font-semibold text-ok">You save {money(t.savings_once)} on the one-time fees with the special offer</p>}
      {t.complimentary_value > 0 && (
        <p className="mt-3 text-right text-sm font-semibold text-ok">You save {money(t.complimentary_value)} with complimentary items</p>
      )}

      <dl className="mt-6 grid gap-3 sm:grid-cols-2">
        {doc.revisions_included > 0 && (
          <div className="rounded-lg border border-line-soft p-3">
            <dt className="text-[13px] text-muted">Revisions included</dt>
            <dd className="mt-0.5 font-semibold text-ink">{doc.revisions_included} for each design</dd>
          </div>
        )}
        {t.advance > 0 && (
          <div className="rounded-lg border border-line-soft p-3">
            <dt className="text-[13px] text-muted">{doc.billing === 'monthly' ? 'Advance each month' : 'Advance to start the work'}</dt>
            <dd className="mt-0.5 font-semibold text-ink tabular-nums">{money(t.advance)} <span className="font-normal text-muted">({doc.advance_percent}%)</span></dd>
          </div>
        )}
      </dl>

      {doc.scope_first === false && <ScopeOfWork sections={doc.sections} />}
      <AfterSections sections={doc.sections} />

      {doc.closing && (
        <div className="mt-6 rounded-lg bg-brand-soft p-4">
          <h3 className="text-[13px] text-muted">A note from {b.name}</h3>
          <p className="mt-1.5 text-[15px] leading-relaxed whitespace-pre-line text-ink">{doc.closing}</p>
        </div>
      )}

      {doc.notes && (
        <div className="mt-6">
          <h3 className="text-[13px] text-muted">Notes</h3>
          <p className="mt-1 text-sm whitespace-pre-line text-ink-2">{doc.notes}</p>
        </div>
      )}
      {doc.terms && (
        <div className="mt-6 border-t border-line-soft pt-5">
          <h3 className="text-[13px] text-muted">Terms</h3>
          <p className="mt-1 text-[13px] whitespace-pre-line text-ink-2">{doc.terms}</p>
        </div>
      )}

      {doc.payment && (
        <div className="mt-6 flex flex-wrap items-center gap-5 rounded-lg border border-line-soft p-4 print:border-0 print:p-0">
          <img src={doc.payment.qr} alt="UPI QR code to pay" className="size-32 shrink-0" />
          <div className="min-w-0 flex-1 text-sm">
            <h3 className="font-semibold text-ink">Pay by UPI</h3>
            <p className="mt-0.5 text-[13px] text-muted">Scan with any UPI app, or pay to</p>
            <p className="mt-1 font-semibold break-all text-ink">{doc.payment.upi_id}</p>
            <p className="text-[13px] text-muted">{doc.payment.payee}. Add {doc.number} as the note.</p>
            <UpiApps uri={doc.payment.uri} className="no-print mt-3 w-full" />
            <div className="no-print mt-3 flex flex-wrap gap-2">
              <CopyButton text={doc.payment.upi_id} label="Copy UPI ID" copied="UPI ID copied" />
            </div>
          </div>
        </div>
      )}
      <AppendixSections sections={doc.sections} />
    </article>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between text-ink-2"><dt>{label}</dt><dd>{value}</dd></div>
}
