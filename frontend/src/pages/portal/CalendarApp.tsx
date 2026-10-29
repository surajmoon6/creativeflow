import { Check, ExternalLink, FileText, LogOut, MessageCircle, MessageSquare, Sparkles, Wallet, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { KIND_LABEL, KindIcon, MonthCalendar, MonthChips, MonthNav, startMonth, ProgressBars, StatePill, SummaryStrip, thisMonth, tileClass, when } from '../../components/calendar'
import FilesDrop from '../../components/FilesDrop'
import { PreviewStage } from '../../components/preview'
import Thread from '../../components/Thread'
import UpiApps from '../../components/UpiApps'
import { Button, CopyButton, ErrorNote, Modal, Spinner, Textarea, cx } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api, ApiError, setCsrf } from '../../services/api'
import type { CalendarData, ClientUpdate, PlanDue, Post, ThreadItem } from '../../types'
import { date, dateTime, money, relative } from '../../utils/format'
import { BrandMark, useBrandColor } from '../client/Portal'

interface Detail extends Post {
  history: { id: number; number: number; status: string; created_at: string; note: string | null; pages: number }[]
  thread: ThreadItem[]
}

/** A client's own login: their monthly content calendar, and nothing else. */
export default function CalendarApp() {
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const asked = params.get('month')
  const month = asked || thisMonth()
  const [ready, setReady] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => {
    const out = () => nav('/login', { replace: true })  // the sign-in ran out (a week without use) or was switched off
    window.addEventListener('cf:logout', out)
    return () => window.removeEventListener('cf:logout', out)
  }, [nav])

  useEffect(() => {
    api.get<{ csrf: string; user: { role: string } }>('/api/auth/me')
      .then((m) => { if (m.user.role !== 'client') nav('/', { replace: true }); else { setCsrf(m.csrf); setReady(true) } })
      .catch(() => nav('/login', { replace: true }))
  }, [nav])

  const { data: cal, setData, error, loading, reload } = useAsync(
    () => (ready ? api.get<CalendarData>(`/api/c/calendar?month=${month}`) : Promise.resolve(null)), [ready, month], { poll: 12000 })
  // Nothing planned this month but more later: open on the month that has the work.
  useEffect(() => {
    if (cal && !asked) { const m = startMonth(cal.months); if (m !== month) setParams({ month: m }, { replace: true }) }
  }, [cal?.months]) // eslint-disable-line react-hooks/exhaustive-deps
  useBrandColor(cal?.brand?.color)
  useEffect(() => { if (cal) document.title = `${cal.client.name}: content calendar` }, [cal])

  if (!ready) return <Spinner />
  const logout = async () => { await api.post('/api/auth/logout').catch(() => {}); nav('/login', { replace: true }) }
  const approval = !!cal?.plan.client_approval
  const needContent = (cal?.items ?? []).filter((p) => p.state === 'planned').sort((a, b) => (a.scheduled_at ?? '').localeCompare(b.scheduled_at ?? ''))
  const waiting = !approval ? [] : (cal?.items ?? []).filter((p) => p.state === 'review').sort((a, b) => (a.scheduled_at ?? '').localeCompare(b.scheduled_at ?? ''))

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          {cal?.brand ? <BrandMark brand={cal.brand} /> : <span />}
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-muted sm:inline">{cal?.me?.name}</span>
            <button type="button" onClick={logout} className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-ink-2 hover:bg-line-soft"><LogOut className="size-4" /> Sign out</button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        {loading && !cal ? <Spinner /> : error || !cal ? <ErrorNote error={error?.message ?? 'Your calendar could not be loaded.'} /> : (
          <div className="flex flex-col gap-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-[13px] text-muted">{cal.client.name}</p>
                <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] sm:text-[30px]">Content calendar</h1>
              </div>
              <MonthNav month={month} onChange={(m) => setParams({ month: m }, { replace: true })} />
            </div>
            <MonthChips months={cal.months} current={month} onPick={(m) => setParams({ month: m }, { replace: true })} />

            {cal.payment && <PayReminder pay={cal.payment} onClaimed={(p) => setData({ ...cal, payment: p })} />}

            {needContent.length > 0 && (
              <section className="rounded-xl border border-info/30 bg-info-soft p-4">
                <h2 className="font-semibold text-ink">{needContent.length} {needContent.length === 1 ? 'post is' : 'posts are'} waiting for your content</h2>
                <p className="mt-0.5 text-[13px] text-ink-2">Tap a post and tell us what you would like in it. We start on the design as soon as you send it.</p>
                <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {needContent.slice(0, 6).map((p) => (
                    <li key={p.id}>
                      <button type="button" onClick={() => setSelected(p.id)} className="flex w-full items-center gap-3 rounded-lg bg-surface p-3 text-left hover:shadow-sm">
                        <span className={cx('flex size-9 shrink-0 items-center justify-center rounded-lg', tileClass('brief'))}><KindIcon kind={p.kind} className="size-4" /></span>
                        <span className="min-w-0"><span className="block truncate text-sm font-medium">{p.title}</span><span className="block text-xs text-muted">{when(p.scheduled_at)}</span></span>
                      </button>
                    </li>
                  ))}
                </ul>
                {needContent.length > 6 && <p className="mt-2 text-xs text-muted">And {needContent.length - 6} more on the calendar below.</p>}
              </section>
            )}

            {waiting.length > 0 && (
              <section className="rounded-xl border border-warn/40 bg-warn-soft p-4">
                <h2 className="font-semibold text-ink">{waiting.length} {waiting.length === 1 ? 'post is' : 'posts are'} waiting for your approval</h2>
                <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {waiting.map((p) => (
                    <li key={p.id}>
                      <button type="button" onClick={() => setSelected(p.id)} className="flex w-full items-center gap-3 rounded-lg bg-surface p-3 text-left hover:shadow-sm">
                        <span className={cx('flex size-9 shrink-0 items-center justify-center rounded-lg', tileClass('review'))}><KindIcon kind={p.kind} className="size-4" /></span>
                        <span className="min-w-0"><span className="block truncate text-sm font-medium">{p.title}</span><span className="block text-xs text-muted">{when(p.scheduled_at)}</span></span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <Updates items={cal.updates ?? []} onOpen={setSelected} />

            <SummaryStrip counts={cal.counts} client approval={approval} />
            <section>
              <h2 className="mb-2 text-[15px] font-semibold">Your plan this month</h2>
              <ProgressBars progress={cal.progress} approval={approval} />
            </section>

            <div className="rounded-xl border border-line bg-surface p-3 sm:p-4">
              <MonthCalendar month={month} items={cal.items} selectedId={selected} onSelect={(p) => setSelected(p.id)} client approval={approval} />
            </div>
          </div>
        )}
      </main>

      {selected && cal && <PostDialog id={selected} canApprove={!!cal.can_approve} approval={approval} onClose={() => setSelected(null)} onOpened={reload}
        onChanged={(p) => { setData({ ...cal, items: cal.items.map((i) => (i.id === p.id ? p : i)) }); reload() }} />}
    </div>
  )
}

/** The month-end payment reminder the studio switched on: amount, due date, UPI, and a way to say it is paid. */
function PayReminder({ pay, onClaimed }: { pay: PlanDue; onClaimed: (p: PlanDue | null) => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const claim = async () => {
    setBusy(true); setErr(null)
    try { const r = await api.post<{ payment: PlanDue | null }>('/api/c/payment/claim'); onClaimed(r.payment) } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const when = pay.overdue ? `was due on ${date(pay.due_date)}` : pay.days_left <= 0 ? 'is due today' : `is due by ${date(pay.due_date)}, in ${pay.days_left} ${pay.days_left === 1 ? 'day' : 'days'}`
  return (
    <section className={cx('rounded-xl border p-4', pay.overdue ? 'border-bad/40 bg-bad-soft' : 'border-line bg-surface')}>
      <div className="flex items-start gap-3">
        <span className={cx('flex size-9 shrink-0 items-center justify-center rounded-full', pay.overdue ? 'bg-surface text-bad' : 'bg-brand-soft text-brand')}><Wallet className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold">Your {pay.label} payment</h2>
          <p className="mt-0.5 text-sm text-ink-2"><b className="font-semibold text-ink">{money(pay.amount)}</b> {when}.</p>
        </div>
      </div>
      {pay.claimed ? (
        <p className="mt-3 rounded-lg bg-ok-soft p-3 text-sm text-ok">Thank you! We have been told, and we will confirm once we see it.</p>
      ) : (
        <>
          {pay.upi && (
            <div className="mt-3">
              <UpiApps uri={pay.upi.uri} />
              <div className="mt-3 hidden justify-center sm:flex"><img src={pay.upi.qr} alt="UPI QR code to pay" className="size-40 rounded-lg border border-line-soft p-2" /></div>
              <div className="mt-3 flex items-center justify-between gap-2 rounded-md bg-canvas px-3 py-2">
                <div className="min-w-0"><div className="text-xs text-muted">UPI ID, {pay.upi.payee}</div><div className="truncate text-sm font-medium">{pay.upi.upi_id}</div></div>
                <CopyButton text={pay.upi.upi_id} copied="UPI ID copied" />
              </div>
            </div>
          )}
          <ErrorNote error={err} />
          <Button className="mt-3 w-full sm:w-auto" variant={pay.upi ? 'secondary' : 'primary'} loading={busy} onClick={claim}><Check className="size-4" /> I have paid</Button>
        </>
      )}
    </section>
  )
}

/** What's new since the client last looked: designs the team added and replies from the team. */
function Updates({ items, onOpen }: { items: ClientUpdate[]; onOpen: (id: number) => void }) {
  const [all, setAll] = useState(false)
  if (!items.length) return null
  const shown = all ? items : items.slice(0, 4)
  const fresh = items.filter((i) => i.new).length
  return (
    <section className="rounded-xl border border-line bg-surface">
      <h2 className="flex items-center gap-2 px-4 pt-4 text-[15px] font-semibold">
        What's new {fresh > 0 && <span className="rounded-full bg-info px-2 py-0.5 text-[11px] font-semibold text-white">{fresh} new</span>}
      </h2>
      <ul className="mt-2 divide-y divide-line-soft">
        {shown.map((u, i) => (
          <li key={`${u.kind}${u.post_id}${u.at}${i}`}>
            <button type="button" onClick={() => onOpen(u.post_id)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-canvas">
              <span className={cx('mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full', u.kind === 'creative' ? 'bg-brand-soft text-brand' : 'bg-info-soft text-info')}>
                {u.kind === 'creative' ? <Sparkles className="size-4" /> : <MessageCircle className="size-4" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2"><span className="truncate text-sm font-medium">{u.title}</span>{u.new && <span className="size-2 shrink-0 rounded-full bg-info" role="img" aria-label="New" />}</span>
                <span className="mt-0.5 line-clamp-2 text-[13px] text-ink-2">{u.kind === 'message' ? <>{u.name ? <b className="font-medium">{u.name}: </b> : null}{u.text}</> : u.text}</span>
                <span className="mt-0.5 block text-xs text-muted">{relative(u.at)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {items.length > 4 && <button type="button" onClick={() => setAll(!all)} className="w-full rounded-b-xl border-t border-line-soft py-2.5 text-[13px] text-ink-2 hover:bg-canvas">{all ? 'Show less' : `Show ${items.length - 4} more`}</button>}
    </section>
  )
}

/** The client's own content for a post: what they want in it, plus photos or a PDF. Open until the studio shares a design. */
function BriefBox({ d, onSaved }: { d: Post; onSaved: () => Promise<void> }) {
  const open = d.state === 'planned' || d.state === 'brief'
  const [text, setText] = useState(d.brief ?? '')
  const [dirty, setDirty] = useState(false)  // the person has typed something that is not saved yet
  const [baseAt, setBaseAt] = useState(d.brief_at ?? '')  // which saved version this text started from
  const [clash, setClash] = useState(false)  // someone else on the same login saved a newer version
  const [picked, setPicked] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const existing = d.brief_files ?? []
  // Several people can use one login. If a colleague saves, an untouched box follows along; one being typed in is never overwritten.
  useEffect(() => {
    if ((d.brief_at ?? '') === baseAt) return
    if (!dirty) { setText(d.brief ?? ''); setBaseAt(d.brief_at ?? '') } else setClash(true)
  }, [d.brief_at]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!open && !d.brief && !existing.length) return null

  const fileLink = (f: { id: number; name: string; image: boolean }, remove?: boolean) => (
    <li key={f.id} className="flex items-center gap-2 rounded-lg border border-line-soft bg-surface p-2 text-sm">
      {f.image ? <img src={`/api/c/brief-files/${f.id}`} alt="" className="size-10 shrink-0 rounded object-cover" /> : <span className="flex size-10 shrink-0 items-center justify-center rounded bg-canvas"><FileText className="size-4 text-muted" /></span>}
      <a href={`/api/c/brief-files/${f.id}`} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate underline-offset-2 hover:underline">{f.name}</a>
      {remove && <button type="button" aria-label={`Remove ${f.name}`} className="rounded p-1.5 text-muted hover:bg-line-soft"
        onClick={async () => { try { await api.del(`/api/c/posts/${d.id}/brief/files/${f.id}`); await onSaved() } catch (e) { setErr((e as ApiError).message) } }}><X className="size-4" /></button>}
    </li>
  )

  if (!open) return (
    <div>
      <h3 className="mb-2 text-[15px] font-semibold">Your content</h3>
      {d.brief && <p className="rounded-lg bg-canvas p-3 text-sm whitespace-pre-line">{d.brief}</p>}
      {existing.length > 0 && <ul className="mt-2 space-y-2">{existing.map((f) => fileLink(f))}</ul>}
    </div>
  )

  const save = async () => {
    setBusy(true); setErr(null); setSaved(false)
    const fd = new FormData()
    fd.set('text', text)
    picked.forEach((f) => fd.append('files', f))
    fd.set('base', baseAt)
    try {
      await api.post(`/api/c/posts/${d.id}/brief`, fd)
      setPicked([]); setDirty(false); setClash(false)
      await onSaved(); setSaved(true)
    } catch (e) {
      const ae = e as ApiError
      if (ae.code === 'brief_changed') { setClash(true); await onSaved() } else setErr(ae.message)
    } finally { setBusy(false) }
  }
  return (
    <div className="rounded-xl border border-line p-3 sm:p-4">
      <h3 className="text-[15px] font-semibold">{d.state === 'brief' ? 'Your content' : 'What would you like in this post?'}</h3>
      <p className="mt-0.5 text-[13px] text-muted">{d.state === 'brief' ? 'Sent to the studio. You can still add more until we share the design.' : 'Tell us the topic, any offer, dates, wording and photos. We make the design from this.'}</p>
      {clash && (
        <div role="alert" className="mt-3 rounded-lg border border-warn/40 bg-warn-soft p-3 text-[13px] text-ink">
          Someone on your account just saved a newer version. Your own wording is still in the box below, nothing was lost.
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => { setText(d.brief ?? ''); setBaseAt(d.brief_at ?? ''); setDirty(false); setClash(false) }}>Show their version</Button>
            <Button size="sm" onClick={() => { setBaseAt(d.brief_at ?? ''); setClash(false) }}>Keep mine and replace theirs</Button>
          </div>
        </div>
      )}
      <Textarea rows={5} value={text} onChange={(e) => { setText(e.target.value); setDirty(true); setSaved(false) }} maxLength={4000} data-noautofocus
        placeholder="For example: Diwali offer, 20% off on all packages till 15 Nov. Use our new logo and add our phone number." className="mt-3" />
      {existing.length > 0 && <ul className="mt-3 space-y-2">{existing.map((f) => fileLink(f, true))}</ul>}
      <div className="mt-3">
        <FilesDrop files={picked} onChange={(f) => { setPicked(f); setSaved(false) }} accept=".png,.jpg,.jpeg,.webp,.pdf" max={Math.max(0, 8 - existing.length)}
          title="Drag and drop photos or a PDF here" hint="or tap to choose. Up to 8 files, 10 MB each." />
      </div>
      <ErrorNote error={err} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={busy} disabled={!text.trim() && !picked.length && !existing.length} onClick={save}>{d.state === 'brief' ? 'Update' : 'Send to the studio'}</Button>
        {saved && <span className="flex items-center gap-1 text-[13px] text-ok"><Check className="size-4" /> Sent to the studio</span>}
      </div>
    </div>
  )
}

function PostDialog({ id, canApprove, approval, onClose, onChanged, onOpened }: { id: number; canApprove: boolean; approval: boolean; onClose: () => void; onChanged: (p: Post) => void; onOpened: () => void }) {
  const { data: d, error, loading, setData } = useAsync(() => api.get<Detail>(`/api/c/posts/${id}`), [id], { poll: 12000 })
  const [asking, setAsking] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { onOpened() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps -- opening a post marks it read, so refresh the badges once

  const act = async (fn: () => Promise<Post>) => {
    setBusy(true); setErr(null)
    try {
      const p = await fn()
      onChanged(p)
      setData(await api.get<Detail>(`/api/c/posts/${id}`))
      setAsking(false); setText('')
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} wide title={d?.title ?? 'Post'}>
      {loading && !d ? <Spinner /> : error || !d ? <ErrorNote error={error?.message} /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatePill state={d.state} client approval={approval} />
            <span className="flex items-center gap-1 text-sm text-ink-2"><KindIcon kind={d.kind} />{KIND_LABEL[d.kind]}</span>
            <span className="text-sm text-muted">{when(d.scheduled_at)}</span>
            {d.platforms.length > 0 && <span className="text-sm text-muted">· {d.platforms.join(', ')}</span>}
          </div>

          {d.latest_version_id ? (
            <PreviewStage pageUrl={(n) => `/api/c/versions/${d.latest_version_id}/pages/${n}?r=${d.preview_rev}`} pages={d.pages}
              alt={`${d.title}, version ${d.version_number}`} watermarked={d.watermarked}
              caption={`Version ${d.version_number}${d.watermarked ? ', with a review watermark' : ''}`} />
          ) : (
            <div className="flex h-28 items-center justify-center rounded-lg border border-dashed border-line bg-canvas px-4 text-center text-sm text-muted">{d.state === 'brief' ? "Thank you. We're working on your design and will show it here." : "The design isn't ready yet. Tell us what you'd like below."}</div>
          )}

          {d.media_url && (
            <a href={d.media_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-medium hover:bg-canvas">
              <KindIcon kind="reel" className="size-4" /> Watch the reel <ExternalLink className="size-3.5 text-muted" />
            </a>
          )}

          {d.caption && (
            <div>
              <div className="mb-1 flex items-center justify-between"><span className="text-[13px] text-muted">Caption</span><CopyButton text={d.caption} label="Copy" copied="Caption copied" /></div>
              <p className="rounded-lg bg-canvas p-3 text-sm whitespace-pre-line">{d.caption}</p>
            </div>
          )}

          {approval && d.state === 'review' && (
            canApprove ? (
              asking ? (
                <div className="space-y-3 rounded-lg border border-line p-3">
                  <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="What should we change? For example: make the date bigger." maxLength={4000} autoFocus />
                  <ErrorNote error={err} />
                  <div className="flex justify-end gap-2">
                    <Button onClick={() => { setAsking(false); setErr(null) }}>Cancel</Button>
                    <Button variant="primary" loading={busy} disabled={text.trim().length < 3}
                      onClick={() => act(() => api.post<Post>(`/api/c/posts/${id}/revisions`, { body: text }))}>Send changes</Button>
                  </div>
                </div>
              ) : (
                <>
                  <ErrorNote error={err} />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="primary" size="lg" loading={busy} onClick={() => act(() => api.post<Post>(`/api/c/posts/${id}/approve`, { version_id: d.latest_version_id }))}><Check className="size-4" /> Approve</Button>
                    <Button size="lg" onClick={() => setAsking(true)}><MessageSquare className="size-4" /> Request changes</Button>
                  </div>
                </>
              )
            ) : <p className="rounded-lg bg-canvas p-3 text-sm text-ink-2">This post is waiting for approval. Your sign-in is view only, so ask your colleague who approves.</p>
          )}
          {approval && d.state === 'changes' && <p className="rounded-lg bg-bad-soft p-3 text-sm text-bad">Your changes were sent. The next version shows up here as soon as it's ready.</p>}
          {(approval ? (d.state === 'approved' || d.state === 'posted') : d.state === 'posted') && <p className="rounded-lg bg-ok-soft p-3 text-sm text-ok">{d.state === 'posted' ? 'This post has gone live.' : 'Approved. We will schedule it.'}</p>}

          <BriefBox d={d} onSaved={async () => { const fresh = await api.get<Detail>(`/api/c/posts/${id}`); setData(fresh); onChanged(fresh) }} />

          <div>
            <h3 className="mb-2 text-[15px] font-semibold">Conversation</h3>
            <Thread items={d.thread} theirs="the studio" placeholder={approval ? 'Write to the studio…' : 'Tell us what you think…'}
              onSend={async (text) => { const r = await api.post<{ thread: ThreadItem[] }>(`/api/c/posts/${id}/messages`, { body: text }); setData({ ...d, thread: r.thread }) }} />
          </div>

          {d.history.length > 1 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-muted">Earlier versions ({d.history.length - 1})</summary>
              <ul className="mt-2 space-y-1 text-ink-2">{d.history.slice(1).map((h) => <li key={h.id}>Version {h.number}, {dateTime(h.created_at)}{h.note ? `: ${h.note}` : ''}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </Modal>
  )
}
