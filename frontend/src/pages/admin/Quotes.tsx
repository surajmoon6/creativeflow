import { Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Empty, ErrorNote, Input, PageHeader, Panel, QuotePill, Spinner, Stat, buttonCls, cx } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api } from '../../services/api'
import type { QuoteStatus, QuoteSummary } from '../../types'
import { QUOTE_LABEL, date, money, relative } from '../../utils/format'

const FILTERS: (QuoteStatus | 'all')[] = ['all', 'draft', 'sent', 'accepted', 'declined', 'expired']

export default function Quotes() {
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const filter = (params.get('status') as QuoteStatus | 'all') || 'all'
  const [q, setQ] = useState('')
  const { data, error, loading } = useAsync(() => api.get<QuoteSummary[]>('/api/quotes'), [], { poll: 10000 })

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (data ?? []).filter((x) => (filter === 'all' || x.status === filter)
      && (!needle || `${x.number} ${x.title} ${x.client.name}`.toLowerCase().includes(needle)))
  }, [data, filter, q])

  const all = data ?? []
  const sum = (st: QuoteStatus) => all.filter((x) => x.status === st).reduce((s, x) => s + x.total, 0)
  const count = (st: QuoteStatus | 'all') => all.filter((x) => st === 'all' || x.status === st).length
  const decided = count('accepted') + count('declined') + count('expired')
  const winRate = decided ? Math.round((count('accepted') / decided) * 100) : null

  return (
    <>
      <PageHeader title="Quotations" sub="Make a quote, send it on WhatsApp, and turn it into a project when it's accepted."
        actions={<Link to="/quotes/new" className={buttonCls('primary')}><Plus className="size-4" /> New quote</Link>} />

      {all.length > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line-soft md:grid-cols-4 [&>*]:bg-surface">
          <Stat label="Awaiting reply" value={money(sum('sent'))} hint={`${count('sent')} quote${count('sent') === 1 ? '' : 's'} sent`} />
          <Stat label="Accepted" value={money(sum('accepted'))} hint={`${count('accepted')} quote${count('accepted') === 1 ? '' : 's'}`} />
          <Stat label="Drafts" value={count('draft')} hint="Not sent yet" />
          <Stat label="Win rate" value={winRate === null ? '—' : `${winRate}%`} hint="Accepted of all answered or expired" />
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1" role="tablist">
          {FILTERS.map((f) => (
            <button key={f} role="tab" aria-selected={filter === f} onClick={() => setParams(f === 'all' ? {} : { status: f })}
              className={cx('h-9 rounded-md px-3 text-[13px] sm:h-8', filter === f ? 'bg-ink text-white' : 'text-ink-2 hover:bg-line-soft')}>
              {f === 'all' ? 'All' : QUOTE_LABEL[f]}
              <span className={cx('ml-1.5 tabular-nums', filter === f ? 'text-white/60' : 'text-faint')}>{data ? count(f) : ''}</span>
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="pointer-events-none absolute top-3.5 left-3 size-4 text-faint sm:top-2.5" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search quotes" className="pl-9" aria-label="Search quotes" />
        </div>
      </div>

      <Panel pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div> : !shown.length ? (
          <Empty title={all.length ? 'No quotes here' : 'No quotes yet'}
            action={!all.length && <Link to="/quotes/new" className={buttonCls('primary')}>Make your first quote</Link>}>
            {all.length ? 'Try another filter.' : 'Add a client, list what you will do and the price, then share the link. They can accept it from their phone.'}
          </Empty>
        ) : (
          <>
            <ul className="divide-y divide-line-soft md:hidden">
              {shown.map((x) => (
                <li key={x.id}>
                  <Link to={`/quotes/${x.id}`} className="block px-4 py-3.5 active:bg-canvas">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-medium text-ink">{x.title}</div>
                        <div className="mt-0.5 text-xs text-muted"><span className="tabular-nums">{x.number}</span> · {x.client.name}</div>
                      </div>
                      <QuotePill status={x.status} />
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-3 text-[13px] text-ink-2">
                      <span className="font-medium tabular-nums text-ink">{money(x.total)}</span>
                      <span className="text-right">{activity(x)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-line-soft text-left text-[13px] whitespace-nowrap text-muted">
                    <th className="px-5 py-2.5 font-normal">Quote</th><th className="px-3 py-2.5 font-normal">Client</th>
                    <th className="px-3 py-2.5 text-right font-normal">Total</th><th className="px-3 py-2.5 font-normal">Status</th>
                    <th className="px-3 py-2.5 font-normal">Activity</th><th className="px-5 py-2.5 font-normal">Valid until</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {shown.map((x) => (
                    <tr key={x.id} onClick={() => nav(`/quotes/${x.id}`)} className="cursor-pointer hover:bg-canvas/70">
                      <td className="px-5 py-3"><div className="font-medium text-ink">{x.title}</div><div className="text-xs text-muted tabular-nums">{x.number}</div></td>
                      <td className="px-3 py-3 text-ink-2">{x.client.name}</td>
                      <td className="px-3 py-3 text-right whitespace-nowrap tabular-nums">{money(x.total)}</td>
                      <td className="px-3 py-3"><QuotePill status={x.status} /></td>
                      <td className="px-3 py-3 text-ink-2">{activity(x)}</td>
                      <td className="px-5 py-3 whitespace-nowrap text-ink-2">{date(x.valid_until)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>
    </>
  )
}

function activity(x: QuoteSummary) {
  if (x.status === 'draft') return `Created ${relative(x.created_at).toLowerCase()}`
  if (x.status === 'accepted') return x.project_code ? `Project ${x.project_code}` : `Accepted ${relative(x.responded_at).toLowerCase()}`
  if (x.status === 'declined') return `Declined ${relative(x.responded_at).toLowerCase()}`
  if (x.views) return `Viewed ${x.views}×, last ${relative(x.last_viewed_at).toLowerCase()}`
  return x.sent_at ? `Sent ${relative(x.sent_at).toLowerCase()}, not opened` : '—'
}
