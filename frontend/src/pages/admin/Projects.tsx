import { Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ProjectTable } from '../../components/ProjectTable'
import { Empty, ErrorNote, Input, PageHeader, Panel, Spinner, buttonCls, cx } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { useAdmin } from '../../layouts/AdminLayout'
import { api } from '../../services/api'
import type { ProjectSummary, Status } from '../../types'
import { STATUS_LABEL } from '../../utils/format'

const FILTERS: (Status | 'all' | 'active')[] = ['active', 'review', 'revision_requested', 'payment_pending', 'paid', 'all']

export default function Projects() {
  const { isStaff } = useAdmin()
  const [params, setParams] = useSearchParams()
  const filter = (params.get('status') as Status | 'all' | 'active') || 'active'
  const [q, setQ] = useState('')
  const { data, error, loading } = useAsync(() => api.get<ProjectSummary[]>('/api/projects'), [], { poll: 10000 })

  const shown = useMemo(() => {
    let list = data ?? []
    if (filter === 'active') list = list.filter((p) => p.status !== 'completed')
    else if (filter !== 'all') list = list.filter((p) => p.status === filter)
    const needle = q.trim().toLowerCase()
    if (needle) list = list.filter((p) => `${p.name} ${p.code} ${p.client.name} ${p.project_type}`.toLowerCase().includes(needle))
    return list
  }, [data, filter, q])

  const count = (f: (typeof FILTERS)[number]) =>
    (data ?? []).filter((p) => (f === 'all' ? true : f === 'active' ? p.status !== 'completed' : p.status === f)).length

  return (
    <>
      <PageHeader title={isStaff ? 'My work' : 'Projects'} actions={isStaff ? undefined : <Link to="/projects/new" className={buttonCls('primary')}><Plus className="size-4" /> New project</Link>} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1" role="tablist">
          {FILTERS.filter((f) => !isStaff || (f !== 'payment_pending' && f !== 'paid')).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f}
              onClick={() => setParams(f === 'active' ? {} : { status: f })}
              className={cx('h-8 rounded-md px-3 text-[13px]', filter === f ? 'bg-ink text-white' : 'text-ink-2 hover:bg-line-soft')}>
              {f === 'all' ? 'All' : f === 'active' ? 'Active' : STATUS_LABEL[f]}
              <span className={cx('ml-1.5 tabular-nums', filter === f ? 'text-white/60' : 'text-faint')}>{data ? count(f) : ''}</span>
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search projects" className="pl-9" aria-label="Search projects" />
        </div>
      </div>
      <Panel pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div>
          : shown.length ? <ProjectTable projects={shown} /> : <Empty title="No projects here">Try another filter or create a project.</Empty>}
      </Panel>
    </>
  )
}
