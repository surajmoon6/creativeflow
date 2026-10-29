import { ChevronLeft, ChevronRight, Clapperboard, GalleryHorizontal, Image as ImageIcon, CircleDashed, Plus } from 'lucide-react'
import { Pill, cx } from './ui'
import type { Post, PostKind, PostState, PlanProgress } from '../types'

type Tone = 'neutral' | 'info' | 'warn' | 'ok' | 'bad'

/** What each state is called: the studio's team and the client look at the same post from different sides. */
export const STATE_META: Record<PostState, { team: string; client: string; tone: Tone; tile: string }> = {
  planned: { team: 'Planned', client: 'Add your content', tone: 'neutral', tile: 'bg-line-soft text-ink-2' },
  brief: { team: 'Brief received', client: 'Content sent', tone: 'info', tile: 'bg-info-soft text-info' },
  review: { team: 'With the client', client: 'Needs your approval', tone: 'warn', tile: 'bg-warn-soft text-warn' },
  changes: { team: 'Changes requested', client: 'Changes sent', tone: 'bad', tile: 'bg-bad-soft text-bad' },
  approved: { team: 'Approved', client: 'Approved', tone: 'ok', tile: 'bg-ok-soft text-ok' },
  posted: { team: 'Posted', client: 'Posted', tone: 'info', tile: 'bg-info-soft text-info' },
}
/** When the client can't approve (chat only), a design is simply shared with them, so the words change. */
const CHAT_LABEL: Partial<Record<PostState, { team: string; client: string }>> = {
  review: { team: 'Shared with client', client: 'Ready to view' }, changes: { team: 'Shared with client', client: 'Ready to view' },
  approved: { team: 'Ready to post', client: 'Ready to view' },
}
/** The tile colour; a shared design is simply 'ready to view' when the client doesn't approve. */
export const tileClass = (state: PostState, approval = true) =>
  !approval && (state === 'review' || state === 'changes' || state === 'approved') ? 'bg-brand-soft text-brand' : STATE_META[state].tile
export const stateLabel = (state: PostState, client?: boolean, approval = true) =>
  (!approval && CHAT_LABEL[state]) ? CHAT_LABEL[state]![client ? 'client' : 'team'] : STATE_META[state][client ? 'client' : 'team']
export const StatePill = ({ state, client, approval = true }: { state: PostState; client?: boolean; approval?: boolean }) =>
  <Pill tone={!approval && (state === 'review' || state === 'changes') ? 'info' : STATE_META[state].tone}>{stateLabel(state, client, approval)}</Pill>

export const KIND_LABEL: Record<PostKind, string> = { post: 'Post', carousel: 'Carousel', reel: 'Reel', story: 'Story' }
export const KIND_PLURAL: Record<PostKind, string> = { post: 'Posts', carousel: 'Carousels', reel: 'Reels', story: 'Stories' }
export function KindIcon({ kind, className = 'size-3.5' }: { kind: PostKind; className?: string }) {
  const I = kind === 'reel' ? Clapperboard : kind === 'carousel' ? GalleryHorizontal : kind === 'story' ? CircleDashed : ImageIcon
  return <I className={className} aria-hidden />
}

export const PLATFORMS = ['Instagram', 'Facebook', 'LinkedIn', 'YouTube', 'X', 'WhatsApp', 'Google Business']

// ---------- months and times (the studio's wall-clock, never shifted by the browser's timezone) ----------
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
export const monthLabel = (ym: string) => { const [y, m] = ym.split('-').map(Number); return `${MONTHS[m - 1]} ${y}` }
export const thisMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }
export const shiftMonth = (ym: string, by: number) => {
  const [y, m] = ym.split('-').map(Number)
  const d = new Date(y, m - 1 + by, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
export const dayOf = (s: string) => s.slice(0, 10)
export function when(s: string | null) {
  if (!s) return ''
  const [y, mo, d] = s.slice(0, 10).split('-').map(Number)
  const t = s.slice(11, 16)
  const date = new Date(y, mo - 1, d)
  const [hh, mm] = (t || '10:00').split(':').map(Number)
  const clock = `${hh % 12 || 12}:${String(mm).padStart(2, '0')} ${hh >= 12 ? 'pm' : 'am'}`
  return `${DAYS[date.getDay()]} ${d} ${MONTHS[mo - 1].slice(0, 3)}, ${clock}`
}

export function MonthNav({ month, onChange }: { month: string; onChange: (m: string) => void }) {
  return (
    <div className="flex items-center gap-1">
      <button type="button" aria-label="Previous month" onClick={() => onChange(shiftMonth(month, -1))} className="rounded-md border border-line bg-surface p-2 hover:bg-canvas"><ChevronLeft className="size-4" /></button>
      <span className="min-w-[8.5rem] text-center text-sm font-semibold">{monthLabel(month)}</span>
      <button type="button" aria-label="Next month" onClick={() => onChange(shiftMonth(month, 1))} className="rounded-md border border-line bg-surface p-2 hover:bg-canvas"><ChevronRight className="size-4" /></button>
      {month !== thisMonth() && <button type="button" onClick={() => onChange(thisMonth())} className="ml-1 rounded-md px-2 py-1.5 text-[13px] text-muted hover:text-ink">Today</button>}
    </div>
  )
}

/** What the plan includes against what has been made and gone out: "3 of 7 reels posted, 2 ready, 2 still to make". */
export function ProgressBars({ progress, approval = true }: { progress: PlanProgress[]; approval?: boolean }) {
  if (!progress.length) return null
  return (
    <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
      {progress.map((p) => {
        const total = Math.max(p.included, p.planned, 1)
        const done = approval ? p.approved : p.posted
        const ready = approval ? Math.max(0, p.planned - p.approved) : Math.max(0, p.made - p.posted)
        const left = approval ? 0 : Math.max(0, (p.included || p.planned) - p.made)
        return (
          <div key={p.kind} className="rounded-lg border border-line-soft bg-surface p-3">
            <div className="flex items-center gap-1.5 text-sm font-medium"><KindIcon kind={p.kind} className="size-3.5 text-muted" />{KIND_PLURAL[p.kind]}</div>
            <div className="mt-0.5 text-sm tabular-nums text-ink-2"><b className="text-lg font-semibold text-ink">{done}</b> of {p.included || p.planned} {approval ? 'approved' : 'posted'}</div>
            <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-line-soft" role="img" aria-label={`${done} done, ${ready} ready, ${p.included} included`}>
              <span className="bg-ok" style={{ width: `${(done / total) * 100}%` }} />
              <span className={approval ? 'bg-faint/60' : 'bg-info/50'} style={{ width: `${(ready / total) * 100}%` }} />
            </div>
            <div className="mt-1.5 text-xs text-muted tabular-nums">
              {approval
                ? <>{p.planned} planned{p.posted ? `, ${p.posted} posted` : ''}{p.included && p.planned > p.included ? `, ${p.planned - p.included} over plan` : ''}</>
                : <>{ready} ready to post · {left} still to make{p.included && p.made > p.included ? ` · ${p.made - p.included} extra` : ''}</>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function SummaryStrip({ counts, client, approval = true }: { counts: Record<PostState, number>; client?: boolean; approval?: boolean }) {
  const cells: [PostState, number][] = approval
    ? [['planned', counts.planned], ['brief', counts.brief], ['review', counts.review], ['changes', counts.changes], ['approved', counts.approved], ['posted', counts.posted]]
    : [['planned', counts.planned], ['brief', counts.brief], ['review', counts.review + counts.changes + counts.approved], ['posted', counts.posted]]
  return (
    <div className={cx('grid grid-cols-3 gap-2', approval ? 'sm:grid-cols-6' : 'sm:grid-cols-4')}>
      {cells.map(([s, n]) => (
        <div key={s} className={cx('rounded-lg px-2.5 py-2 sm:px-3', tileClass(s, approval))}>
          <div className="text-xl font-semibold tabular-nums">{n}</div>
          <div className="text-[11px] leading-tight sm:text-xs">{stateLabel(s, client, approval)}</div>
        </div>
      ))}
    </div>
  )
}

/** A month grid on tablets and desktops, a day-by-day agenda on phones. */
export function MonthCalendar({ month, items, selectedId, onSelect, onAdd, client, approval = true }: {
  month: string; items: Post[]; selectedId?: number | null; onSelect: (p: Post) => void; onAdd?: (day: string) => void; client?: boolean; approval?: boolean
}) {
  const [y, m] = month.split('-').map(Number)
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7 // weeks start on Monday
  const days = new Date(y, m, 0).getDate()
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const key = (d: number) => `${month}-${String(d).padStart(2, '0')}`
  const by = (day: string) => items.filter((i) => i.scheduled_at && dayOf(i.scheduled_at) === day).sort((a, b) => a.scheduled_at!.localeCompare(b.scheduled_at!))

  const tile = (p: Post, compact: boolean) => (
    <button key={p.id} type="button" onClick={() => onSelect(p)} title={`${p.title}, ${stateLabel(p.state, client, approval)}`}
      className={cx('flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-[11px] leading-tight transition-shadow',
        tileClass(p.state, approval), selectedId === p.id && 'ring-2 ring-ink')}>
      <KindIcon kind={p.kind} className="size-3 shrink-0" />
      {!compact && <span className="min-w-0 flex-1 truncate font-medium">{p.title.replace(/^(Post|Reel|Carousel|Story), \d{1,2} [A-Za-z]{3}$/, '$1')}</span>}
      {(p.fresh || !!p.unread) && <span className="ml-auto size-2 shrink-0 rounded-full bg-info" role="img" aria-label="New" />}
    </button>
  )

  return (
    <>
      <div className="hidden md:block">
        <div className="grid grid-cols-7 gap-1 pb-1 text-center text-xs text-muted">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d}>{d}</div>)}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {Array.from({ length: lead }, (_, i) => <div key={`l${i}`} />)}
          {Array.from({ length: days }, (_, i) => {
            const day = key(i + 1)
            const list = by(day)
            return (
              <div key={day} className={cx('group min-h-[88px] rounded-lg border bg-surface p-1.5', day === today ? 'border-ink' : 'border-line-soft')}>
                <div className="flex items-center justify-between">
                  <span className={cx('text-xs tabular-nums', day === today ? 'font-semibold text-ink' : 'text-muted')}>{i + 1}</span>
                  {onAdd && <button type="button" onClick={() => onAdd(day)} aria-label={`Add a post on ${day}`}
                    className="rounded p-0.5 text-faint opacity-0 hover:bg-line-soft hover:text-ink focus:opacity-100 group-hover:opacity-100"><Plus className="size-3.5" /></button>}
                </div>
                <div className="mt-1 space-y-1">{list.map((p) => tile(p, false))}</div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="md:hidden">
        {items.length === 0 ? <p className="py-8 text-center text-sm text-muted">Nothing planned this month yet.</p> : (
          <ul className="space-y-2">
            {[...items].sort((a, b) => (a.scheduled_at ?? '').localeCompare(b.scheduled_at ?? '')).map((p) => (
              <li key={p.id}>
                <button type="button" onClick={() => onSelect(p)} className={cx('flex w-full items-center gap-3 rounded-lg border bg-surface p-3 text-left', selectedId === p.id ? 'border-ink' : 'border-line-soft')}>
                  <span className={cx('flex size-9 shrink-0 items-center justify-center rounded-lg', tileClass(p.state, approval))}><KindIcon kind={p.kind} className="size-4" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{p.title}</span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">{when(p.scheduled_at)}<StatePill state={p.state} client={client} approval={approval} /></span>
                  </span>
                  {(p.fresh || !!p.unread) && <span className="self-start rounded-full bg-info px-1.5 py-0.5 text-[10px] font-semibold text-white">{p.unread ? `${p.unread} new` : 'New'}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
        {onAdd && <button type="button" onClick={() => onAdd(`${month}-01`)} className="mt-3 w-full rounded-lg border border-dashed border-line py-2.5 text-sm text-ink-2">Add a post</button>}
      </div>
    </>
  )
}

/** Months that have something planned, so nobody lands on an empty month and wonders where it all went. */
export function MonthChips({ months, current, onPick }: { months: { month: string; count: number }[]; current: string; onPick: (m: string) => void }) {
  const others = months.filter((m) => m.month !== current)
  if (!others.length) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-[13px]">
      <span className="text-muted">Also planned:</span>
      {others.map((m) => (
        <button key={m.month} type="button" onClick={() => onPick(m.month)} className="rounded-full border border-line bg-surface px-3 py-1 font-medium text-ink-2 hover:border-faint hover:text-ink">
          {monthLabel(m.month)} <span className="text-muted">({m.count})</span>
        </button>
      ))}
    </div>
  )
}

/** The month to open on when none was asked for: this month, unless it is empty and another has posts planned. */
export function startMonth(months: { month: string; count: number }[]): string {
  const now = thisMonth()
  if (!months.length || months.some((m) => m.month === now)) return now
  return (months.find((m) => m.month > now) ?? months[months.length - 1]).month
}
