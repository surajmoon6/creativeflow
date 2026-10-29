import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ProjectTable } from '../../components/ProjectTable'
import { Empty, ErrorNote, PageHeader, Panel, QuotePill, Spinner, Stat, StatusPill, buttonCls } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api } from '../../services/api'
import type { ProjectSummary, QuoteSummary } from '../../types'
import { money } from '../../utils/format'

interface Dash {
  stats: Record<string, number>
  needs_attention: { project: ProjectSummary; reason: string }[]
  quotes: (QuoteSummary & { reason: string })[]
  recent: ProjectSummary[]
}

export default function Dashboard() {
  const { data, error, loading } = useAsync(() => api.get<Dash>('/api/dashboard'), [], { poll: 10000 })
  if (loading) return <Spinner />
  if (error || !data) return <ErrorNote error={error?.message} />
  const s = data.stats
  const month = new Date().toLocaleDateString('en-IN', { month: 'long' })

  return (
    <>
      <PageHeader title="Dashboard" sub={`${s.active} active project${s.active === 1 ? '' : 's'}`}
        actions={<Link to="/projects/new" className={buttonCls('primary')}><Plus className="size-4" /> New project</Link>} />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line-soft md:grid-cols-4 [&>*]:bg-surface">
        <Stat label={`Revenue in ${month}`} value={money(s.revenue_month)} />
        <Stat label="Outstanding" value={money(s.outstanding)} hint="Issued, unpaid invoices" />
        <Stat label="In review" value={s.in_review} hint="Waiting on client approval" />
        <Stat label="Changes requested" value={s.changes_requested} />
        <Stat label="Payment pending" value={s.payment_pending} />
        <Stat label="Paid" value={s.paid} hint="Not yet downloaded" />
        <Stat label="Delivered" value={s.delivered} />
        <Stat label="New this month" value={s.projects_this_month} />
      </div>

      {data.needs_attention.length > 0 && (
        <Panel title="Needs your attention" pad={false} className="mt-6">
          <ul className="grid divide-y divide-line-soft md:grid-cols-2 md:divide-y-0 xl:grid-cols-3">
            {data.needs_attention.map(({ project: p, reason }) => (
              <li key={`${p.id}-${reason}`} className="md:border-b md:border-line-soft">
                <Link to={`/projects/${p.id}`} className="block px-5 py-3.5 hover:bg-canvas/70">
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate font-medium text-ink">{p.name}</span>
                    <StatusPill status={p.status} />
                  </div>
                  <div className="mt-0.5 text-[13px] text-ink-2">{reason} — {p.client.name}</div>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {data.quotes.length > 0 && (
        <Panel title="Quotes to follow up" pad={false} className="mt-6"
          actions={<Link to="/quotes" className="text-[13px] font-medium text-ink-2 hover:text-ink">All quotes</Link>}>
          <ul className="grid divide-y divide-line-soft md:grid-cols-2 md:divide-y-0 xl:grid-cols-3">
            {data.quotes.map((x) => (
              <li key={x.id} className="md:border-b md:border-line-soft">
                <Link to={`/quotes/${x.id}`} className="block px-5 py-3.5 hover:bg-canvas/70">
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate font-medium text-ink">{x.title}</span>
                    <QuotePill status={x.status} />
                  </div>
                  <div className="mt-0.5 text-[13px] text-ink-2">{x.reason}: {x.client.name}, {money(x.total)}</div>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="Recent projects" pad={false} className="mt-6"
        actions={<Link to="/projects" className="text-[13px] font-medium text-ink-2 hover:text-ink">All projects</Link>}>
        {data.recent.length ? <ProjectTable projects={data.recent} /> : (
          <Empty title="No projects yet" action={<Link to="/projects/new" className={buttonCls('primary')}>Create your first project</Link>}>
            Add a client and a project, upload the first version and share the review link.
          </Empty>
        )}
      </Panel>
    </>
  )
}
