import { CalendarPlus, Check, ExternalLink, FileText, MessageCircle, Pencil, Sparkles, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import FileDrop from '../../components/FileDrop'
import Thread from '../../components/Thread'
import { KIND_LABEL, KindIcon, MonthCalendar, MonthChips, MonthNav, startMonth, PLATFORMS, ProgressBars, StatePill, SummaryStrip, dayOf, thisMonth, when } from '../../components/calendar'
import { Button, CopyButton, Empty, ErrorNote, Field, Input, Modal, PageHeader, Panel, Select, Spinner, Textarea, useToast } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { Attention, CalendarData, Post, PostKind, ThreadItem } from '../../types'

interface CalClient { id: number; name: string; plan: string; active: boolean; unread: number }

export default function Calendar() {
  const { isStaff } = useAdmin()
  const [params, setParams] = useSearchParams()
  const { data: clients, loading: loadingClients } = useAsync(() => api.get<CalClient[]>('/api/calendar/clients'), [], { poll: 15000 })
  const asked = params.get('month')
  const month = asked || thisMonth()
  const clientId = Number(params.get('client')) || clients?.[0]?.id
  const set = (patch: Record<string, string>) => setParams({ client: String(clientId ?? ''), month, ...patch }, { replace: true })

  const { data: cal, setData, error, loading, reload } = useAsync(
    () => (clientId ? api.get<CalendarData>(`/api/calendar?client_id=${clientId}&month=${month}`) : Promise.resolve(null)), [clientId, month], { poll: 10000 })
  const { data: attention } = useAsync(() => api.get<Attention>('/api/calendar/attention'), [], { poll: 15000 })
  useEffect(() => {
    if (cal && !asked) { const m = startMonth(cal.months); if (m !== month) set({ month: m }) }
  }, [cal?.months, clientId]) // eslint-disable-line react-hooks/exhaustive-deps
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState<{ post?: Post; day?: string } | null>(null)
  const post = cal?.items.find((p) => p.id === selected) ?? null
  const want = useRef<number | null>(null)  // a post to open once the client and month it belongs to have loaded
  useEffect(() => { setSelected(want.current); want.current = null }, [clientId, month])

  if (loadingClients) return <Spinner />
  if (!clients?.length) {
    return (
      <>
        <PageHeader title="Calendar" />
        <Empty title="No monthly clients yet">
          {isStaff ? 'When the studio owner assigns you a monthly client, their content calendar shows up here.'
            : <>Set up a monthly plan on a client's page and their content calendar appears here. <Link to="/clients" className="underline underline-offset-2">Go to clients</Link></>}
        </Empty>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Calendar" sub="Plan each post, upload its design, and the client reviews it on their own login."
        actions={<Button variant="primary" onClick={() => setForm({ day: `${month}-${String(Math.min(new Date().getDate(), 28)).padStart(2, '0')}` })}><CalendarPlus className="size-4" /> Add post</Button>} />

      {!!attention?.items.length && (
        <section className="mb-5 rounded-xl border border-info/30 bg-info-soft p-4">
          <h2 className="font-semibold">Needs your attention <span className="ml-1 rounded-full bg-info px-2 py-0.5 text-[11px] font-semibold text-white">{attention.count}</span></h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {attention.items.slice(0, 6).map((a) => (
              <li key={`${a.post_id}${a.what}`}>
                <button type="button" onClick={() => { want.current = a.post_id; setSelected(a.post_id); set({ client: String(a.client_id), month: a.scheduled_at?.slice(0, 7) ?? month }) }}
                  className="flex w-full items-start gap-3 rounded-lg bg-surface p-3 text-left hover:shadow-sm">
                  <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-info-soft text-info">{a.what === 'brief' ? <Sparkles className="size-4" /> : <MessageCircle className="size-4" />}</span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{a.client}: {a.title}</span>
                    <span className="block text-xs text-muted">{a.what === 'brief' ? 'Sent their content' : `${a.count} new ${a.count === 1 ? 'message' : 'messages'}`}{a.scheduled_at ? `, goes out ${when(a.scheduled_at)}` : ''}</span>
                    <span className="mt-0.5 line-clamp-2 block text-[13px] text-ink-2">{a.text}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Select value={clientId} onChange={(e) => set({ client: e.target.value })} aria-label="Client" className="max-w-[16rem]">
          {clients.map((c) => <option key={c.id} value={c.id}>{c.name}{c.unread ? ` (${c.unread} new)` : ''}</option>)}
        </Select>
        <MonthNav month={month} onChange={(m) => set({ month: m })} />
      </div>

      {loading ? <Spinner /> : error || !cal ? <ErrorNote error={error?.message} /> : (
        <div className="space-y-5">
          <MonthChips months={cal.months} current={month} onPick={(m) => set({ month: m })} />
          <SummaryStrip counts={cal.counts} approval={cal.plan.client_approval} />
          <ProgressBars progress={cal.progress} approval={cal.plan.client_approval} />
          <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="min-w-0 rounded-xl border border-line bg-surface p-3 sm:p-4">
              <MonthCalendar month={month} items={cal.items} selectedId={selected} onSelect={(p) => setSelected(p.id)} onAdd={(day) => setForm({ day })} approval={cal.plan.client_approval} />
            </div>
            <div className="min-w-0 xl:sticky xl:top-20">
              {post ? <div className="space-y-5">
                <PostPanel key={post.id} post={post} approval={cal.plan.client_approval} onChange={() => reload()} onEdit={() => setForm({ post })}
                  onGone={() => { setSelected(null); reload() }} onUpdated={(p) => setData({ ...cal, items: cal.items.map((i) => (i.id === p.id ? p : i)) })} />
                <Conversation key={`c${post.id}`} post={post} onOpened={reload} />
              </div>
                : <Panel title="Post details"><p className="text-sm text-muted">Pick a post on the calendar to see its design, caption and status, or press the + on a day to plan a new one.</p></Panel>}
            </div>
          </div>
        </div>
      )}

      {form && clientId && <PostForm clientId={clientId} post={form.post} day={form.day} month={month} onClose={() => setForm(null)}
        onSaved={(p) => { setForm(null); setSelected(p.id); reload() }} onAnother={() => reload()} />}
    </>
  )
}

/** The chat on a post: the client's messages and change requests, your replies, and each design you add. */
function Conversation({ post, onOpened }: { post: Post; onOpened: () => void }) {
  const { data, setData } = useAsync(() => api.get<{ thread: ThreadItem[] }>(`/api/calendar/posts/${post.id}/thread`), [post.id], { poll: 10000 })
  useEffect(() => { onOpened() }, [post.id]) // eslint-disable-line react-hooks/exhaustive-deps -- opening it marks the client's messages read
  return (
    <Panel title="Conversation with the client">
      {data ? <Thread items={data.thread} theirs="the client" placeholder="Reply to the client…"
        onSend={async (text) => { setData(await api.post<{ thread: ThreadItem[] }>(`/api/calendar/posts/${post.id}/messages`, { body: text })) }} /> : <Spinner />}
    </Panel>
  )
}

function PostPanel({ post, approval, onChange, onEdit, onGone, onUpdated }: { post: Post; approval: boolean; onChange: () => void; onEdit: () => void; onGone: () => void; onUpdated: (p: Post) => void }) {
  const toast = useToast()
  const [upload, setUpload] = useState(false)
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true)
    try { await fn(); if (done) toast(done); onChange() } catch (e) { alert((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Panel title={post.title} actions={<StatePill state={post.state} approval={approval} />} pad={false}>
      <div className="space-y-4 p-5 text-sm">
        {post.latest_version_id ? (
          <img src={`/api/admin/versions/${post.latest_version_id}/pages/1?r=${post.preview_rev}`} alt={`${post.title}, version ${post.version_number}`}
            className="max-h-[420px] w-full rounded-lg border border-line-soft bg-stage object-contain" />
        ) : (
          <div className="flex h-36 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line bg-canvas text-muted">
            <KindIcon kind={post.kind} className="size-6" /><span>No design uploaded yet</span>
          </div>
        )}
        <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2">
          <dt className="text-muted">Type</dt><dd className="flex items-center gap-1.5"><KindIcon kind={post.kind} />{KIND_LABEL[post.kind]}</dd>
          <dt className="text-muted">Goes out</dt><dd>{when(post.scheduled_at)}</dd>
          <dt className="text-muted">Platforms</dt><dd>{post.platforms.join(', ') || 'Not set'}</dd>
          <dt className="text-muted">Version</dt><dd>{post.version_number ? `${post.version_number} (${post.versions} in total)` : 'None yet'}</dd>
          {approval && <><dt className="text-muted">Changes</dt><dd>{post.revisions_used} of {post.revisions_included} used</dd></>}
          {post.media_url && <><dt className="text-muted">Video</dt><dd><a href={post.media_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2">Open link <ExternalLink className="size-3" /></a></dd></>}
        </dl>
        {(post.brief || !!post.brief_files?.length) && (
          <div className="rounded-lg border border-info/30 bg-info-soft p-3">
            <div className="flex items-center justify-between gap-2 text-xs font-medium text-info">
              <span>Content from the client{post.brief_by ? `, ${post.brief_by}` : ''}</span>
              {post.brief_new && <span className="rounded-full bg-info px-1.5 py-0.5 text-[10px] font-semibold text-white">New</span>}
            </div>
            {post.brief && <p className="mt-1 whitespace-pre-line text-ink">{post.brief}</p>}
            {!!post.brief_files?.length && (
              <ul className="mt-2 flex flex-wrap gap-2">
                {post.brief_files.map((f) => (
                  <li key={f.id}>
                    <a href={`/api/admin/files/${f.id}?inline=1`} target="_blank" rel="noreferrer" title={f.name}
                      className="flex items-center gap-2 rounded-lg border border-line-soft bg-surface p-1.5 pr-3 text-[13px] hover:border-faint">
                      {f.image ? <img src={`/api/admin/files/${f.id}?inline=1`} alt="" className="size-12 rounded object-cover" /> : <span className="flex size-12 items-center justify-center rounded bg-canvas"><FileText className="size-4 text-muted" /></span>}
                      <span className="max-w-[9rem] truncate">{f.name}</span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {post.request && (
          <div className="rounded-lg bg-bad-soft p-3 text-bad"><div className="text-xs font-medium">The client asked for</div><p className="mt-0.5 whitespace-pre-line text-ink">{post.request}</p></div>
        )}
        {post.caption && (
          <div>
            <div className="mb-1 flex items-center justify-between"><span className="text-[13px] text-muted">Caption</span><CopyButton text={post.caption} label="Copy" copied="Caption copied" /></div>
            <p className="rounded-lg bg-canvas p-3 whitespace-pre-line">{post.caption}</p>
          </div>
        )}
        <div className="flex flex-wrap gap-2 border-t border-line-soft pt-4">
          {post.state !== 'approved' && post.state !== 'posted' && post.project_id && (
            <Button variant={post.state === 'planned' || post.state === 'brief' || post.state === 'changes' ? 'primary' : 'secondary'} onClick={() => setUpload(true)}>
              <Upload className="size-4" /> {post.versions ? `Upload version ${(post.version_number ?? 0) + 1}` : 'Upload design'}
            </Button>
          )}
          {(post.state === 'approved' || (!approval && (post.state === 'review' || post.state === 'changes') && post.versions > 0)) && <Button variant="primary" loading={busy} onClick={() => run(() => api.post<Post>(`/api/calendar/posts/${post.id}/posted`, { posted: true }), 'Marked as posted')}><Check className="size-4" /> Mark as posted</Button>}
          {post.state === 'posted' && <Button loading={busy} onClick={() => run(() => api.post<Post>(`/api/calendar/posts/${post.id}/posted`, { posted: false }))}>Undo posted</Button>}
          <Button onClick={onEdit}><Pencil className="size-3.5" /> Edit</Button>
          {post.versions === 0 && <Button variant="ghost" loading={busy} aria-label="Remove post"
            onClick={() => { if (confirm('Remove this planned post?')) run(async () => { await api.del(`/api/calendar/posts/${post.id}`); onGone() }) }}><Trash2 className="size-4" /></Button>}
        </div>
      </div>
      {upload && post.project_id && <UploadDesign post={post} onClose={() => setUpload(false)} onDone={(p) => { setUpload(false); onUpdated(p); onChange() }} />}
    </Panel>
  )
}

function UploadDesign({ post, onClose, onDone }: { post: Post; onClose: () => void; onDone: (p: Post) => void }) {
  const toast = useToast()
  const file = useRef<HTMLInputElement>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const go = async () => {
    const f = file.current?.files?.[0]
    if (!f) { setErr('Choose a file to upload.'); return }
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.set('file', f); fd.set('note', note); fd.set('deliverable_id', String(post.id))
    try {
      await api.post(`/api/projects/${post.project_id}/versions`, fd)
      toast(`${post.title}: version ${(post.version_number ?? 0) + 1} sent for review`)
      onDone(post)
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={`Upload ${post.kind === 'reel' ? 'the cover for' : 'the design for'} ${post.title}`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={go}>Upload and send for review</Button></>}>
      <div className="space-y-4">
        <FileDrop inputRef={file} accept=".png,.jpg,.jpeg,.webp,.pdf" title="Drag and drop the design here" hint="or click to browse. PNG, JPG, WEBP or PDF" />
        {post.kind === 'reel' && <p className="text-[13px] text-muted">For a reel, upload a cover image. The video itself goes in as a link when you edit the post.</p>}
        <Field label="Note to the client (optional)"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Date enlarged as requested." /></Field>
        <ErrorNote error={err} />
      </div>
    </Modal>
  )
}

/** Planning a slot takes two things: what it is and which day. Everything else is optional, and the client adds their own content. */
function PostForm({ clientId, post, day, month, onClose, onSaved, onAnother }: {
  clientId: number; post?: Post; day?: string; month: string; onClose: () => void; onSaved: (p: Post) => void; onAnother: () => void
}) {
  const toast = useToast()
  const [title, setTitle] = useState(post?.title ?? '')
  const [kind, setKind] = useState<PostKind>(post?.kind ?? 'post')
  const [date, setDate] = useState(post?.scheduled_at ? dayOf(post.scheduled_at) : day ?? `${month}-01`)
  const [time, setTime] = useState(post?.scheduled_at?.slice(11, 16) ?? '10:00')
  const [platforms, setPlatforms] = useState<string[]>(post?.platforms ?? [])
  const [caption, setCaption] = useState(post?.caption ?? '')
  const [url, setUrl] = useState(post?.media_url ?? '')
  const [more, setMore] = useState(!!post)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const toggle = (p: string) => setPlatforms((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]))

  const save = async (another: boolean) => {
    setBusy(true); setErr(null)
    const body = { client_id: clientId, title, kind, scheduled_at: `${date}T${time || '10:00'}`, platforms, caption, media_url: url }
    try {
      const saved = post ? await api.put<Post>(`/api/calendar/posts/${post.id}`, body) : await api.post<Post>('/api/calendar/posts', body)
      if (another) {  // keep the type, clear the rest, so the next slot is two taps away
        toast(`${saved.title} added`); setTitle(''); setCaption(''); setUrl(''); onAnother()
      } else onSaved(saved)
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={post ? 'Edit post' : 'Plan a post'} wide
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        {!post && <Button loading={busy} onClick={() => save(true)}>Add and plan another</Button>}
        <Button variant="primary" loading={busy} onClick={() => save(false)}>{post ? 'Save changes' : 'Add to calendar'}</Button>
      </>}>
      <div className="space-y-5">
        <div>
          <div className="mb-1.5 text-[13px] font-medium">What goes out</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Type">
            {(Object.keys(KIND_LABEL) as PostKind[]).map((k) => (
              <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}
                className={`flex h-12 items-center justify-center gap-2 rounded-lg border text-sm font-medium transition-colors ${kind === k ? 'border-ink bg-canvas' : 'border-line text-ink-2 hover:border-faint'}`}>
                <KindIcon kind={k} className="size-4" />{KIND_LABEL[k]}
              </button>
            ))}
          </div>
        </div>
        <Field label="On which day"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} autoFocus /></Field>
        {!post && <p className="-mt-2 text-[13px] text-muted">The client opens this day on their calendar and tells you what they want in it. Then you make the creative.</p>}

        <button type="button" onClick={() => setMore(!more)} aria-expanded={more} className="text-[13px] font-medium text-ink-2 underline underline-offset-2">
          {more ? 'Hide the extra details' : 'Add more details (optional)'}
        </button>
        {more && (
          <div className="space-y-4 rounded-xl border border-line-soft p-4">
            <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
              <Field label="Title" hint="Empty is fine: it is named like “Reel, 5 Nov”."><Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="World Mental Health Day" /></Field>
              <Field label="Time"><Input type="time" value={time} onChange={(e) => setTime(e.target.value)} /></Field>
            </div>
            <div>
              <div className="mb-1.5 text-[13px] font-medium">Platforms</div>
              <div className="flex flex-wrap gap-2">
                {PLATFORMS.map((p) => (
                  <label key={p} className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] ${platforms.includes(p) ? 'border-ink bg-canvas font-medium' : 'border-line text-ink-2'}`}>
                    <input type="checkbox" className="sr-only" checked={platforms.includes(p)} onChange={() => toggle(p)} />{p}
                  </label>
                ))}
              </div>
            </div>
            <Field label="Caption" hint="You can also write it later, after the client sends their content."><Textarea rows={3} value={caption} onChange={(e) => setCaption(e.target.value)} maxLength={4000} placeholder="Your mind deserves attention too. #MentalHealthDay" /></Field>
            {kind === 'reel' && <Field label="Video link" hint="A Google Drive, YouTube (unlisted) or other link to the reel. Upload a cover image as the design."><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://drive.google.com/…" /></Field>}
          </div>
        )}
        <ErrorNote error={err} />
      </div>
    </Modal>
  )
}
