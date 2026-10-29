import { Plus, Trash2 } from 'lucide-react'
import { KIND_PLURAL } from '../../components/calendar'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select, Spinner, Textarea, cx } from '../../components/ui'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { ClientRecord, PostKind, QuoteDetail } from '../../types'
import { money, toPaise, toRupees } from '../../utils/format'
import { ClientForm } from './Clients'

// Tap to add a line; the price is only a starting point and stays editable.
const SERVICES: [string, number][] = [
  ['Instagram post design', 1200], ['Instagram poster', 1800], ['Event banner', 3500], ['Flyer (A5)', 2500],
  ['Brochure (4 pages)', 9000], ['Logo design', 6500], ['Menu card', 4500], ['Social media pack (5 posts)', 4800],
]

// Complimentary extras: shown with their value, charged nothing.
const FREE_EXTRAS: [string, number][] = [['Instagram story design', 100], ['Extra revision round', 500], ['Social media cover', 300]]

interface Line { description: string; quantity: string; unit: string; free: boolean; detail: string; period: 'once' | 'monthly'; list: string }
interface Section { title: string; text: string; part: 'scope' | 'after' | 'appendix'; tone: '' | 'gain' | 'caution' | 'title' }
interface Incl { kind: PostKind; count: string }
const blank = (): Line => ({ description: '', quantity: '1', unit: '', free: false, detail: '', period: 'once', list: '' })
const lineTotal = (l: Line) => Math.max(1, Number(l.quantity) || 1) * toPaise(l.unit)
const pad = (n: number) => String(n).padStart(2, '0')
const addDays = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }
const daysUntil = (iso: string) => Math.round((new Date(`${iso}T00:00:00`).getTime() - new Date(addDays(0) + 'T00:00:00').getTime()) / 86400000)

export default function QuoteForm() {
  const { id } = useParams()
  const editing = !!id
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { settings } = useAdmin()
  const [clients, setClients] = useState<ClientRecord[] | null>(null)
  const [existing, setExisting] = useState<QuoteDetail | null>(null)
  const [f, setF] = useState<{ client_id: string; title: string; discount: string; gst: boolean; rate: string; valid: string; notes: string; terms: string; revisions: string; advance: string } | null>(null)
  const [lines, setLines] = useState<Line[]>([blank()])
  const [closing, setClosing] = useState('')
  const [sections, setSections] = useState<Section[]>([])
  const [scopeFirst, setScopeFirst] = useState(true)
  const [billing, setBilling] = useState<'once' | 'monthly'>('once')
  const [startsLater, setStartsLater] = useState(false)
  const [discountLabel, setDiscountLabel] = useState('')
  const [incl, setIncl] = useState<Incl[]>([])
  const [closingTouched, setClosingTouched] = useState(false)
  const [newClient, setNewClient] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.get<ClientRecord[]>('/api/clients').then(setClients) }, [])
  // Load an existing quote once. (Never depend on the form's own state here: that re-triggers the load forever
  // and wipes whatever you have just typed.)
  useEffect(() => {
    if (!editing) return
    api.get<QuoteDetail>(`/api/quotes/${id}`).then((q) => {
      setExisting(q)
      setF({ client_id: String(q.client_id), title: q.title, discount: String(toRupees(q.discount)), gst: q.gst_enabled,
        rate: String(q.gst_rate_bp / 100), valid: q.valid_until, notes: q.document.notes ?? '', terms: q.document.terms ?? '',
        revisions: String(q.document.revisions_included), advance: String(q.document.advance_percent) })
      setLines(q.document.items.map((i) => ({ description: i.description, quantity: String(i.quantity), unit: String(toRupees(i.unit_price)), free: i.complimentary, detail: i.detail ?? '', period: i.period ?? 'once', list: i.list_price ? String(toRupees(i.list_price)) : '' })))
      setClosing(q.document.closing ?? '')
      setClosingTouched(true)
      setSections((q.document.sections ?? []).map((s) => ({ title: s.title, text: s.lines.join('\n'), part: s.part ?? 'scope', tone: s.tone ?? '' })))
      setScopeFirst(q.document.scope_first !== false)
      setBilling(q.document.billing)
      setStartsLater(q.document.recurring_start === 'launch')
      setDiscountLabel(q.document.discount_label ?? '')
      setIncl((q.plan_inclusions ?? []).map((i) => ({ kind: i.kind as PostKind, count: String(i.count) })))
    })
  }, [editing, id])

  // Starting values for a new quote, once the settings are known.
  useEffect(() => {
    if (editing || !settings) return
    setF((cur) => cur ?? { client_id: params.get('client') ?? '', title: '', discount: '0', gst: !!settings.gst_enabled_default,
      rate: String(Number(settings.gst_rate_bp_default) / 100), valid: addDays(Number(settings.quote_valid_days) || 15),
      notes: '', terms: String(settings.quote_terms ?? ''), revisions: String(settings.default_revisions ?? 4), advance: String(settings.quote_advance_percent ?? 50) })
  }, [editing, settings, params])

  const totals = useMemo(() => {
    if (!f) return null
    const subtotal = lines.reduce((s, l) => s + (l.free ? 0 : lineTotal(l)), 0)
    const freeValue = lines.reduce((s, l) => s + (l.free ? lineTotal(l) : 0), 0)
    const discount = Math.max(0, Math.min(toPaise(f.discount), subtotal))
    const taxable = subtotal - discount
    const tax = f.gst ? Math.floor((taxable * Math.round(Number(f.rate || 0) * 100) + 5000) / 10000) : 0
    const total = taxable + tax
    return { subtotal, discount, tax, total, freeValue, advance: Math.round((total * Math.min(100, Math.max(0, Number(f.advance) || 0))) / 100) }
  }, [f, lines])

  const clientName = clients?.find((c) => String(c.id) === f?.client_id)?.name
  const standardClosing = () => {
    const tpl = String(settings?.quote_closing ?? '')
    const withClient = clientName ? tpl.replaceAll('{client}', clientName) : tpl.replaceAll(', {client}', '').replaceAll('{client}', '')
    return withClient.replaceAll('{studio}', String(settings?.brand_name ?? ''))
  }
  // Until you edit it yourself, the message follows the chosen client.
  useEffect(() => {
    if (!editing && !closingTouched && settings) setClosing(standardClosing())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientName, settings, closingTouched, editing])

  if (!f || !clients || !totals) return <Spinner />
  const typedDiscount = toPaise(f.discount)
  const discountError = typedDiscount < 0 ? "A discount can't be negative."
    : typedDiscount > totals.subtotal ? `A discount can't be more than the subtotal (${money(totals.subtotal)}).` : null
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setF({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value })
  const setLine = (i: number, patch: Partial<Line>) => setLines(lines.map((l, n) => (n === i ? { ...l, ...patch } : l)))
  const addService = ([description, price]: [string, number], free = false) => {
    const empty = lines.length === 1 && !lines[0].description && !lines[0].unit
    const line: Line = { ...blank(), description, unit: String(price), free }
    setLines(empty ? [line] : [...lines, line])
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (discountError) { setErr(discountError); return }
    setBusy(true); setErr(null)
    const body = {
      client_id: Number(f.client_id), title: f.title, discount: toPaise(f.discount), gst_enabled: f.gst,
      gst_rate_bp: Math.round(Number(f.rate || 0) * 100), valid_until: f.valid, notes: f.notes, terms: f.terms,
      revisions_included: Number(f.revisions) || 0, advance_percent: Number(f.advance) || 0,
      closing, billing, discount_label: discountLabel, scope_first: scopeFirst, recurring_start: startsLater ? 'launch' : 'now',
      sections: sections.map((s) => ({ title: s.title, part: s.part, tone: s.tone || null, lines: s.text.split('\n') })),
      plan_inclusions: billing === 'monthly' ? incl.map((i) => ({ kind: i.kind, count: Number(i.count) || 0 })) : [],
      items: lines.map((l) => ({ description: l.description, quantity: Number(l.quantity) || 1, unit_price: toPaise(l.unit), complimentary: l.free, detail: l.detail, period: l.period, list_price: l.list ? toPaise(l.list) : null })),
    }
    try {
      const q = editing ? await api.put<QuoteDetail>(`/api/quotes/${id}`, body) : await api.post<QuoteDetail>('/api/quotes', body)
      nav(`/quotes/${q.id}`)
    } catch (e2) {
      setErr((e2 as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  const saveLabel = editing ? 'Save changes' : 'Save quote'
  return (
    <form onSubmit={submit}>
      <PageHeader title={editing ? `Edit ${existing?.number ?? 'quote'}` : 'New quote'}
        actions={<><Button type="button" onClick={() => nav(-1)}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>{saveLabel}</Button></>} />
      {existing?.stored_status === 'sent' && (
        <p className="mb-4 rounded-md bg-info-soft px-3 py-2 text-[13px] text-info">This quote was already sent. The client sees your changes on the same link.</p>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          <Panel title="Who is it for">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Client">
                <div className="flex gap-2">
                  <Select value={f.client_id} onChange={set('client_id')} required>
                    <option value="">Choose a client</option>
                    {clients.map((c) => <option key={c.id} value={c.id}>{c.display_name}</option>)}
                  </Select>
                  <Button type="button" onClick={() => setNewClient(true)}>New</Button>
                </div>
              </Field>
              <Field label="Quote title"><Input value={f.title} onChange={set('title')} required placeholder="Diwali campaign creatives" autoFocus={!editing} /></Field>
            </div>
          </Panel>

          <Panel title="What you'll do">
            <div className="mb-4">
              <p className="mb-2 text-[13px] text-muted">Tap to add a service, then adjust the price.</p>
              <div className="flex flex-wrap gap-1.5">
                {SERVICES.map((s) => (
                  <button key={s[0]} type="button" onClick={() => addService(s)}
                    className="rounded-full border border-line px-3 py-1.5 text-[13px] text-ink-2 hover:border-faint">+ {s[0]}</button>
                ))}
              </div>
              <p className="mt-3 mb-2 text-[13px] text-muted">Add a free extra. The client sees its value, crossed out, marked FREE.</p>
              <div className="flex flex-wrap gap-1.5">
                {FREE_EXTRAS.map((s) => (
                  <button key={s[0]} type="button" onClick={() => addService(s, true)}
                    className="rounded-full border border-ok/40 bg-ok-soft px-3 py-1.5 text-[13px] text-ok hover:border-ok">+ Free: {s[0]}</button>
                ))}
              </div>
            </div>
            <ul className="space-y-3">
              {lines.map((l, i) => (
                <li key={i} className="rounded-lg border border-line p-3">
                  <div className="flex items-start gap-2">
                    <Input value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} required maxLength={255}
                      placeholder="e.g. Instagram poster design" aria-label={`Item ${i + 1} description`} />
                    {lines.length > 1 && (
                      <button type="button" onClick={() => setLines(lines.filter((_, n) => n !== i))} aria-label={`Remove item ${i + 1}`}
                        className="flex size-11 shrink-0 items-center justify-center rounded-md text-muted hover:bg-bad-soft hover:text-bad sm:size-9"><Trash2 className="size-4" /></button>
                    )}
                  </div>
                  <div className="mt-2 grid grid-cols-[84px_1fr_auto] items-end gap-3">
                    <Field label="Qty"><Input type="number" min={1} inputMode="numeric" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} /></Field>
                    <Field label={l.free ? 'Value each (₹)' : 'Price each (₹)'}><Input type="number" min={0} step="0.01" inputMode="decimal" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} required placeholder="0" /></Field>
                    <div className="pb-2.5 text-sm font-medium tabular-nums">
                      {l.free ? <span className="font-semibold text-ok">FREE</span> : money(lineTotal(l))}
                    </div>
                  </div>
                  <Field label="What this covers (optional)" className="mt-2"><Textarea rows={2} value={l.detail} onChange={(e) => setLine(i, { detail: e.target.value })} maxLength={2000} placeholder="UI/UX design, responsive development, testing and deployment." /></Field>
                  <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1">
                    <label className="flex min-h-9 items-center gap-2 text-[13px] text-ink-2">
                      <input type="checkbox" checked={l.free} onChange={(e) => setLine(i, { free: e.target.checked })} className="size-4 accent-[var(--brand)]" />
                      Free for the client (complimentary)
                    </label>
                    <label className="flex min-h-9 items-center gap-2 text-[13px] text-ink-2">
                      Standard price (₹, crossed out)
                      <Input type="number" min={0} step="0.01" inputMode="decimal" value={l.list} onChange={(e) => setLine(i, { list: e.target.value })} className="h-8 w-28 py-0 text-[13px]" placeholder="optional" />
                    </label>
                    <label className="flex min-h-9 items-center gap-2 text-[13px] text-ink-2">
                      Charged
                      <Select value={l.period} onChange={(e) => setLine(i, { period: e.target.value as 'once' | 'monthly' })} className="h-8 w-auto py-0 text-[13px]">
                        <option value="once">One time</option><option value="monthly">Every month</option>
                      </Select>
                    </label>
                  </div>
                </li>
              ))}
            </ul>
            <Button type="button" className="mt-3" onClick={() => setLines([...lines, blank()])}><Plus className="size-4" /> Add item</Button>
            {lines.some((l) => l.period === 'monthly' && !l.free) && lines.some((l) => l.period !== 'monthly' && !l.free) && (
              <label className="mt-3 flex items-start gap-2 text-[13px] text-ink-2">
                <input type="checkbox" checked={startsLater} onChange={(e) => setStartsLater(e.target.checked)} className="mt-0.5 size-4 accent-[var(--brand)]" />
                <span>The monthly fee starts after the work is delivered (for example website maintenance after launch). The first payment, and the advance, then count the one-time fees only.</span>
              </label>
            )}
          </Panel>

          <Panel title="Scope of work (optional)">
            <p className="mb-3 text-[13px] text-muted">List what is included under headings. In a section, start a line with <code># </code> for a subheading, <code>&gt; </code> for a small note or <code>~ </code> for a plain paragraph. Every other line becomes a bullet.</p>
            <label className="mb-3 flex items-center gap-2 text-[13px] text-ink-2">
              <input type="checkbox" checked={scopeFirst} onChange={(e) => setScopeFirst(e.target.checked)} className="size-4 accent-[var(--brand)]" />
              Show the scope of work above the pricing (untick to show the pricing first)
            </label>
            <div className="space-y-4">
              {sections.map((s, i) => (
                <div key={i} className="rounded-lg border border-line-soft p-3">
                  <div className="flex items-end gap-2">
                    <Field label={`Section ${i + 1} title`} className="flex-1"><Input value={s.title} maxLength={120} onChange={(e) => setSections(sections.map((x, n) => (n === i ? { ...x, title: e.target.value } : x)))} placeholder="Social media content creation" /></Field>
                    <Select value={s.part} onChange={(e) => setSections(sections.map((x, n) => (n === i ? { ...x, part: e.target.value as Section['part'] } : x)))} className="w-auto" aria-label="Where it appears">
                      <option value="scope">In the scope of work</option><option value="after">After the pricing</option><option value="appendix">On the last page</option>
                    </Select>
                    {s.part === 'appendix' && (
                      <Select value={s.tone} onChange={(e) => setSections(sections.map((x, n) => (n === i ? { ...x, tone: e.target.value as Section['tone'] } : x)))} className="w-auto" aria-label="Style">
                        <option value="">Plain</option><option value="title">Page title</option><option value="gain">Advantages (green)</option><option value="caution">Watch out (amber)</option>
                      </Select>
                    )}
                    <Button type="button" size="sm" variant="ghost" aria-label="Remove section" onClick={() => setSections(sections.filter((_, n) => n !== i))}><Trash2 className="size-4" /></Button>
                  </div>
                  <Field label="What's included" className="mt-3"><Textarea rows={6} value={s.text} onChange={(e) => setSections(sections.map((x, n) => (n === i ? { ...x, text: e.target.value } : x)))} placeholder={'# Reels, 7 per month\nCreative concepts and content planning\n> Ad spend is paid by the client directly.'} /></Field>
                </div>
              ))}
              <Button type="button" size="sm" onClick={() => setSections([...sections, { title: '', text: '', part: 'scope', tone: '' }])}><Plus className="size-3.5" /> Add a section</Button>
            </div>
          </Panel>

          {billing === 'monthly' && (
            <Panel title="What the monthly plan includes">
              <p className="mb-3 text-[13px] text-muted">When the client accepts, you can start their monthly plan from this quote. These counts become the plan: the calendar tracks delivered against them.</p>
              <div className="space-y-2">
                {incl.map((r, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Select value={r.kind} onChange={(e) => setIncl(incl.map((x, n) => (n === i ? { ...x, kind: e.target.value as PostKind } : x)))} className="max-w-[10rem]">
                      {(Object.keys(KIND_PLURAL) as PostKind[]).map((k) => <option key={k} value={k}>{KIND_PLURAL[k]}</option>)}
                    </Select>
                    <Input type="number" min={0} max={500} value={r.count} onChange={(e) => setIncl(incl.map((x, n) => (n === i ? { ...x, count: e.target.value } : x)))} className="w-24" aria-label="How many" />
                    <Button type="button" size="sm" variant="ghost" aria-label="Remove line" onClick={() => setIncl(incl.filter((_, n) => n !== i))}><Trash2 className="size-4" /></Button>
                  </div>
                ))}
                <Button type="button" size="sm" onClick={() => setIncl([...incl, { kind: 'post', count: '4' }])}><Plus className="size-3.5" /> Add a line</Button>
              </div>
            </Panel>
          )}

          <Panel title="A friendly closing message">
            <Field label="Message to the client" hint="Shown at the end of the quote. A warm, confident note helps them say yes.">
              <Textarea rows={4} value={closing} maxLength={1500}
                onChange={(e) => { setClosing(e.target.value); setClosingTouched(true) }} />
            </Field>
            <button type="button" className="mt-2 text-[13px] font-medium text-ink-2 hover:text-ink"
              onClick={() => { setClosing(standardClosing()); setClosingTouched(false) }}>Use our standard message</button>
          </Panel>

          <Panel title="Notes and terms">
            <div className="space-y-4">
              <Field label="Note to the client" hint="Optional. Shown on the quote."><Textarea rows={3} value={f.notes} onChange={set('notes')} maxLength={2000} placeholder="Delivery in 3 working days after approval." /></Field>
              <Field label="Terms" hint="Default terms come from Settings."><Textarea rows={4} value={f.terms} onChange={set('terms')} maxLength={4000} /></Field>
            </div>
          </Panel>
        </div>

        <div className="min-w-0 space-y-6">
          <Panel title="Pricing">
            <div className="space-y-4">
              <Field label="Billing">
                <Select value={billing} onChange={(e) => setBilling(e.target.value as 'once' | 'monthly')}>
                  <option value="once">One-time</option><option value="monthly">Every month</option>
                </Select>
              </Field>
              <Field label="Discount label" hint="Shown instead of 'Discount', for example: Special client discount."><Input value={discountLabel} maxLength={80} onChange={(e) => setDiscountLabel(e.target.value)} placeholder="Special client discount" /></Field>
              <Field label="Discount (₹)">
                <>
                  <Input type="number" min={0} step="0.01" inputMode="decimal" value={f.discount} onChange={set('discount')} aria-invalid={!!discountError} />
                  {discountError && <span className="mt-1.5 block text-xs text-bad" role="alert">{discountError}</span>}
                </>
              </Field>
              <div className="flex items-end gap-3">
                <label className="flex h-11 items-center gap-2 text-sm sm:h-9">
                  <input type="checkbox" checked={f.gst} onChange={set('gst')} className="size-4 accent-[var(--brand)]" /> GST applies
                </label>
                {f.gst && <Field label="Rate (%)" className="w-24"><Input type="number" min={0} max={50} step="0.01" value={f.rate} onChange={set('rate')} /></Field>}
              </div>
              <div>
                <Field label="Valid until"><Input type="date" value={f.valid} onChange={set('valid')} required /></Field>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted">Valid for</span>
                  {[3, 7, 15, 30].map((n) => (
                    <button key={n} type="button" onClick={() => setF({ ...f, valid: addDays(n) })}
                      className={cx('rounded-full border px-2.5 py-1 text-xs', f.valid === addDays(n) ? 'border-ink bg-ink text-white' : 'border-line text-ink-2 hover:border-faint')}>
                      {n} days
                    </button>
                  ))}
                </div>
                {f.valid && <p className="mt-1.5 text-xs text-muted">{(() => { const n = daysUntil(f.valid); return n < 0 ? 'This date has already passed.' : n === 0 ? 'Expires today.' : `Expires in ${n} day${n === 1 ? '' : 's'}.` })()}</p>}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Revisions per design"><Input type="number" min={0} max={50} inputMode="numeric" value={f.revisions} onChange={set('revisions')} /></Field>
                <Field label="Advance (%)"><Input type="number" min={0} max={100} inputMode="numeric" value={f.advance} onChange={set('advance')} /></Field>
              </div>
              <dl className="space-y-1 rounded-lg bg-canvas p-3 text-[13px] tabular-nums">
                <div className="flex justify-between text-ink-2"><dt>Subtotal</dt><dd>{money(totals.subtotal)}</dd></div>
                {totals.discount > 0 && <div className="flex justify-between text-ink-2"><dt>Discount</dt><dd>− {money(totals.discount)}</dd></div>}
                {totals.tax > 0 && <div className="flex justify-between text-ink-2"><dt>GST</dt><dd>{money(totals.tax)}</dd></div>}
                <div className="flex justify-between pt-1 text-base font-semibold text-ink"><dt>Total</dt><dd>{money(totals.total)}</dd></div>
                {totals.freeValue > 0 && <div className="flex justify-between pt-1 font-medium text-ok"><dt>Free extras</dt><dd>{money(totals.freeValue)}</dd></div>}
                {totals.advance > 0 && <div className="flex justify-between pt-1 text-ink-2"><dt>Advance to start</dt><dd>{money(totals.advance)}</dd></div>}
              </dl>
            </div>
          </Panel>
          <div className="hidden sm:block"><ErrorNote error={err} /></div>
        </div>
      </div>

      <div className="sticky bottom-0 z-20 -mx-4 mt-6 border-t border-line bg-surface/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:hidden">
        {err && <div className="mb-2"><ErrorNote error={err} /></div>}
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}>{saveLabel} · {money(totals.total)}</Button>
      </div>
      <ClientForm open={newClient} onClose={() => setNewClient(false)}
        onSaved={(c) => { setClients([...(clients ?? []), c]); setF({ ...f, client_id: String(c.id) }); setNewClient(false) }} />
    </form>
  )
}
