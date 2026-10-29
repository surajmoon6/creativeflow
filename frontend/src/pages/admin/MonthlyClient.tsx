import { CalendarDays, Check, ExternalLink, FileText, Pencil, Plus, Shuffle, Trash2, UserPlus } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import FileDrop from '../../components/FileDrop'
import { KIND_LABEL, KIND_PLURAL } from '../../components/calendar'
import { Button, CopyButton, ErrorNote, Field, Input, Modal, Panel, Pill, Select, Switch, buttonCls, useToast } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api, ApiError } from '../../services/api'
import type { ClientLogin, ClientRecord, PlanDetail, PostKind } from '../../types'
import { date, money, toPaise, toRupees, waHref } from '../../utils/format'
import { makePassword } from '../../utils/password'

/** On a client's page: their monthly plan, and the sign-ins their people use for the content calendar. */
export function MonthlyPanels({ client }: { client: ClientRecord }) {
  const { data: plan, setData: setPlan, reload: reloadPlan } = useAsync(() => api.get<PlanDetail | null>(`/api/clients/${client.id}/plan`), [client.id], { poll: 20000 })
  const { data: logins, reload: reloadLogins } = useAsync(() => api.get<ClientLogin[]>(`/api/clients/${client.id}/logins`), [client.id])
  const [editPlan, setEditPlan] = useState(false)
  const [login, setLogin] = useState<ClientLogin | 'new' | null>(null)
  const [shown, setShown] = useState<{ email: string; password: string } | null>(null)
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [paying, setPaying] = useState(false)
  const act = async (url: string, body: object, done: string) => {
    setBusy(true)
    try { setPlan(await api.post<PlanDetail>(url, body)); toast(done) } catch (e) { alert((e as ApiError).message) } finally { setBusy(false) }
  }

  return (
    <>
      <Panel title="Monthly plan" actions={plan && <Button size="sm" onClick={() => setEditPlan(true)}><Pencil className="size-3.5" /> Edit</Button>}>
        {!plan ? (
          <>
            <p className="text-sm text-ink-2">For a client you work with every month. Set what the plan includes and their content calendar opens.</p>
            <Button className="mt-3" variant="primary" onClick={() => setEditPlan(true)}><CalendarDays className="size-4" /> Set up a monthly plan</Button>
          </>
        ) : (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{plan.name}</span><Pill tone={plan.active ? 'ok' : 'neutral'}>{plan.active ? 'Active' : 'Switched off'}</Pill></div>
            <div className="text-2xl font-semibold tabular-nums">{money(plan.monthly_price)}<span className="text-sm font-normal text-muted"> a month</span></div>
            <ul className="flex flex-wrap gap-1.5">
              {plan.inclusions.map((i) => <li key={i.kind} className="rounded-full bg-line-soft px-2.5 py-0.5 text-xs text-ink-2">{i.count} {(i.count === 1 ? KIND_LABEL : KIND_PLURAL)[i.kind].toLowerCase()}</li>)}
            </ul>
            <p className="text-[13px] text-muted">{plan.revisions_per_post} rounds of changes per post.</p>
            <div className="space-y-3 border-t border-line-soft pt-3">
              <label className="flex items-start justify-between gap-4">
                <span><span className="font-medium">Client approves designs</span><span className="block text-[13px] text-muted">{plan.client_approval ? 'On: they see Approve and Request changes buttons.' : 'Off: they only view designs and chat with you.'}</span></span>
                <Switch checked={plan.client_approval} disabled={busy} label="Client approves designs"
                  onChange={(on) => act(`/api/clients/${client.id}/plan/toggles`, { client_approval: on }, on ? 'Approval switched on' : 'Chat only')} />
              </label>
              {plan.payment_available && <label className="flex items-start justify-between gap-4">
                <span><span className="font-medium">Month-end payment reminder</span><span className="block text-[13px] text-muted">{plan.payment_reminder ? `On: they see ${money(plan.monthly_price)} and how to pay from ${REMIND_DAYS} days before the month ends.` : 'Off: they never see a payment reminder.'}</span></span>
                <Switch checked={plan.payment_reminder} disabled={busy} label="Month-end payment reminder"
                  onChange={(on) => act(`/api/clients/${client.id}/plan/toggles`, { payment_reminder: on }, on ? 'Payment reminder on' : 'Payment reminder off')} />
              </label>}
              {plan.payment_available && plan.payment_reminder && <PayStatus plan={plan} busy={busy} onPaid={(paid) => act(`/api/clients/${client.id}/plan/paid`, { paid }, paid ? 'Marked as paid' : 'Marked as not paid')} />}
            </div>
            <Link to={`/calendar?client=${client.id}`} className={buttonCls('secondary', 'sm')}><CalendarDays className="size-3.5" /> Open the calendar</Link>
          </div>
        )}
      </Panel>

      {plan && (
        <Panel title="Payments received" actions={
          <div className="flex flex-wrap gap-2">
            {plan.invoice
              ? <Link to={`/invoices/${plan.invoice.id}`} className={buttonCls('secondary', 'sm')}><FileText className="size-3.5" /> Invoice {plan.invoice.number}</Link>
              : plan.payments.length > 0 && <Button size="sm" onClick={() => act(`/api/clients/${client.id}/plan/invoice`, {}, 'Invoice created')}><FileText className="size-3.5" /> Create invoice</Button>}
            <Button size="sm" onClick={() => setPaying(true)}><Plus className="size-3.5" /> Record a payment</Button>
          </div>}>
          {!plan.payments.length ? (
            <p className="text-sm text-ink-2">Nothing recorded yet. When {client.display_name} pays you, write it down here with the amount, the day and the screenshot.</p>
          ) : (
            <>
              <div className="text-sm text-muted">Received so far</div>
              <div className="text-2xl font-semibold tabular-nums">{money(plan.payments.reduce((s, p) => s + p.amount, 0))}</div>
              <ul className="mt-3 divide-y divide-line-soft text-sm">
                {plan.payments.map((p) => (
                  <li key={p.id} className="flex items-start justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <div className="font-medium tabular-nums">{money(p.amount)} <span className="font-normal text-muted">on {date(p.received_on)}</span></div>
                      {p.note && <div className="text-[13px] text-ink-2">{p.note}</div>}
                      {p.reference && <div className="text-xs text-muted">Ref {p.reference}</div>}
                    </div>
                    {p.proof_file_id && <a href={`/api/admin/files/${p.proof_file_id}?inline=1`} target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-1 text-[13px] font-medium underline underline-offset-2">Screenshot <ExternalLink className="size-3" /></a>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
      )}

      {plan && (
        <Panel title="Client sign-ins" actions={<Button size="sm" onClick={() => setLogin('new')}><UserPlus className="size-3.5" /> Add sign-in</Button>}>
          {!logins?.length ? (
            <p className="text-sm text-ink-2">Give the people at {client.display_name} their own email and password. They see only their calendar and chat. Prices stay hidden unless you switch on the month-end payment reminder.</p>
          ) : (
            <ul className="divide-y divide-line-soft text-sm">
              {logins.map((l) => (
                <li key={l.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{l.name}</div>
                    <div className="truncate text-xs text-muted">{l.email}</div>
                    <div className="mt-1 flex gap-1.5"><Pill tone={l.can_approve ? 'ok' : 'neutral'}>{l.can_approve ? 'Can approve' : 'View only'}</Pill>{!l.active && <Pill tone="bad">Switched off</Pill>}</div>
                  </div>
                  <Button size="sm" onClick={() => setLogin(l)}><Pencil className="size-3.5" /> Edit</Button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {editPlan && <PlanForm client={client} plan={plan ?? null} onClose={() => setEditPlan(false)} onSaved={() => { setEditPlan(false); reloadPlan(); toast('Plan saved') }} />}
      {paying && <PaymentForm client={client} onClose={() => setPaying(false)} onSaved={(p) => { setPaying(false); setPlan(p); toast('Payment recorded') }} />}
      {login && <LoginForm client={client} login={login === 'new' ? null : login} onClose={() => setLogin(null)}
        onSaved={(info) => { setLogin(null); reloadLogins(); if (info) setShown(info); else toast('Saved') }} />}
      <Modal open={!!shown} onClose={() => setShown(null)} title="Share these sign-in details" footer={<Button variant="primary" onClick={() => setShown(null)}>Done</Button>}>
        {shown && <Details info={shown} client={client} />}
      </Modal>
    </>
  )
}

function PaymentForm({ client, onClose, onSaved }: { client: ClientRecord; onClose: () => void; onSaved: (p: PlanDetail) => void }) {
  const file = useRef<HTMLInputElement>(null)
  const [amount, setAmount] = useState('')
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10))
  const [ref, setRef] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const save = async () => {
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.set('amount', String(toPaise(amount))); fd.set('received_on', day); fd.set('reference', ref); fd.set('note', note)
    const f = file.current?.files?.[0]
    if (f) fd.set('proof', f)
    try { onSaved(await api.post<PlanDetail>(`/api/clients/${client.id}/plan/payments`, fd)) } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={`Payment from ${client.display_name}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!(Number(amount) > 0)} onClick={save}>Save payment</Button></>}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Amount received (₹)"><Input type="number" min={0} step="any" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus /></Field>
          <Field label="Received on"><Input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></Field>
        </div>
        <Field label="Reference (optional)" hint="The UTR or transaction ID."><Input value={ref} onChange={(e) => setRef(e.target.value)} maxLength={64} /></Field>
        <Field label="Note (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={255} placeholder="IMPS, half of the first month" /></Field>
        <FileDrop inputRef={file} accept=".png,.jpg,.jpeg,.webp,.pdf" title="Add the payment screenshot (optional)" hint="Drag and drop it here, or click to browse." />
        <p className="text-[13px] text-muted">Only you can see this. It counts in your revenue for the month it was received.</p>
        <ErrorNote error={err} />
      </div>
    </Modal>
  )
}

const REMIND_DAYS = 5

/** Where this month's payment stands, and the button that settles it once the money has arrived. */
function PayStatus({ plan, busy, onPaid }: { plan: PlanDetail; busy: boolean; onPaid: (paid: boolean) => void }) {
  const p = plan.payment
  return (
    <div className="rounded-lg bg-canvas p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-medium">{p.label}: {p.paid ? 'paid' : p.claimed ? 'client says paid' : p.showing ? (p.overdue ? 'overdue' : 'reminder showing') : 'not due yet'}</div>
          <div className="text-[13px] text-muted">{p.paid ? 'No reminder will show for this month.' : p.showing ? `Due ${date(p.due_date)}.` : `The reminder starts on ${date(p.opens)}.`}</div>
        </div>
        {p.paid
          ? <Button size="sm" loading={busy} onClick={() => onPaid(false)}>Undo</Button>
          : <Button size="sm" variant={p.claimed ? 'primary' : 'secondary'} loading={busy} onClick={() => onPaid(true)}><Check className="size-3.5" /> Mark {p.label.split(' ')[0]} as paid</Button>}
      </div>
    </div>
  )
}

function Details({ info, client }: { info: { email: string; password: string }; client: ClientRecord }) {
  const url = `${window.location.origin}/login`
  const text = `Hi ${client.name}, your content calendar is ready. See your posts and chat with us here:\n${url}\nEmail: ${info.email}\nPassword: ${info.password}`
  return (
    <>
      <p className="text-sm text-ink-2">The password is shown only now. Send it to them privately.</p>
      <dl className="mt-4 space-y-2 rounded-lg bg-canvas p-3 text-sm">
        <div className="flex justify-between gap-3"><dt className="text-muted">Sign in at</dt><dd className="break-all font-medium">{url}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">Email</dt><dd className="break-all font-medium">{info.email}</dd></div>
        <div className="flex justify-between gap-3"><dt className="text-muted">Password</dt><dd className="font-mono font-medium">{info.password}</dd></div>
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        <CopyButton text={text} label="Copy message" copied="Copied" />
        <a href={waHref(client.whatsapp || client.phone || '', text)} target="_blank" rel="noreferrer" className={buttonCls('secondary', 'sm')}>Send on WhatsApp</a>
      </div>
    </>
  )
}

interface Row { kind: PostKind; count: string }

function PlanForm({ client, plan, onClose, onSaved }: { client: ClientRecord; plan: PlanDetail | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(plan?.name ?? 'Monthly plan')
  const [price, setPrice] = useState(plan ? String(toRupees(plan.monthly_price)) : '')
  const [rev, setRev] = useState(String(plan?.revisions_per_post ?? 2))
  const [start, setStart] = useState(plan?.start_date ?? new Date().toISOString().slice(0, 10))
  const [active, setActive] = useState(plan?.active ?? true)
  const [rows, setRows] = useState<Row[]>(plan?.inclusions.map((i) => ({ kind: i.kind, count: String(i.count) })) ?? [{ kind: 'post', count: '12' }, { kind: 'reel', count: '4' }])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (i: number, patch: Partial<Row>) => setRows(rows.map((r, n) => (n === i ? { ...r, ...patch } : r)))
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.put(`/api/clients/${client.id}/plan`, { name, monthly_price: toPaise(price), start_date: start, active, revisions_per_post: Number(rev) || 0,
        inclusions: rows.map((r) => ({ kind: r.kind, count: Number(r.count) || 0 })) })
      onSaved()
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={plan ? 'Edit monthly plan' : 'Set up a monthly plan'} wide
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save plan</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Plan name"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></Field>
          <Field label="Monthly price (₹)" hint="Only you see this."><Input type="number" min={0} step="any" value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" /></Field>
          <Field label="Starts"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="Rounds of changes per post"><Input type="number" min={0} max={20} value={rev} onChange={(e) => setRev(e.target.value)} /></Field>
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-medium">Included every month</div>
          <div className="space-y-2">
            {rows.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <Select value={r.kind} onChange={(e) => set(i, { kind: e.target.value as PostKind })} className="max-w-[10rem]">
                  {(Object.keys(KIND_LABEL) as PostKind[]).map((k) => <option key={k} value={k}>{KIND_PLURAL[k]}</option>)}
                </Select>
                <Input type="number" min={0} max={500} value={r.count} onChange={(e) => set(i, { count: e.target.value })} className="w-24" aria-label="How many" />
                <Button size="sm" variant="ghost" onClick={() => setRows(rows.filter((_, n) => n !== i))} aria-label="Remove line"><Trash2 className="size-4" /></Button>
              </div>
            ))}
            <Button size="sm" onClick={() => setRows([...rows, { kind: 'post', count: '4' }])}><Plus className="size-3.5" /> Add a line</Button>
          </div>
        </div>
        <Switch checked={active} onChange={setActive} label="Plan is active" />
        <ErrorNote error={err} />
      </div>
    </Modal>
  )
}

function LoginForm({ client, login, onClose, onSaved }: { client: ClientRecord; login: ClientLogin | null; onClose: () => void; onSaved: (info?: { email: string; password: string }) => void }) {
  const [name, setName] = useState(login?.name ?? client.name)
  const [email, setEmail] = useState(login?.email ?? client.email ?? '')
  const [password, setPassword] = useState(login ? '' : makePassword())
  const [canApprove, setCanApprove] = useState(login?.can_approve ?? true)
  const [active, setActive] = useState(login?.active ?? true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      if (login) {
        await api.put(`/api/logins/${login.id}`, { name, can_approve: canApprove, active, ...(password ? { password } : {}) })
        onSaved(password ? { email: login.email, password } : undefined)
      } else {
        await api.post(`/api/clients/${client.id}/logins`, { name, email, password, can_approve: canApprove })
        onSaved({ email, password })
      }
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={login ? `Edit ${login.name}` : `Add a sign-in for ${client.display_name}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!name.trim() || (!login && (!email.trim() || password.length < 10))} onClick={save}>{login ? 'Save changes' : 'Create sign-in'}</Button></>}>
      <div className="space-y-4">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></Field>
        <Field label="Email (their sign-in)"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!!login} /></Field>
        <Field label={login ? 'Set a new password (leave empty to keep theirs)' : 'Password'} hint="At least 10 characters.">
          <div className="flex gap-2">
            <Input value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" className="font-mono" />
            <Button type="button" onClick={() => setPassword(makePassword())}><Shuffle className="size-4" /> Generate</Button>
          </div>
        </Field>
        <Switch checked={canApprove} onChange={setCanApprove} label="Can approve posts and ask for changes" />
        <p className="-mt-2 text-[13px] text-muted">Only matters when approvals are switched on for the plan. Switch it off for people who should only look.</p>
        {login && <Switch checked={active} onChange={setActive} label="Sign-in is active" />}
        <ErrorNote error={err} />
      </div>
    </Modal>
  )
}
