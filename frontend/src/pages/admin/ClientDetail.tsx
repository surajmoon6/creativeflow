import { Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ProjectTable } from '../../components/ProjectTable'
import { Button, Empty, ErrorNote, PageHeader, Panel, Spinner, Stat, buttonCls } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api } from '../../services/api'
import type { ClientRecord } from '../../types'
import { money } from '../../utils/format'
import { ClientForm } from './Clients'
import { MonthlyPanels } from './MonthlyClient'

export default function ClientDetail() {
  const { id } = useParams()
  const { data: c, error, loading, reload } = useAsync(() => api.get<ClientRecord>(`/api/clients/${id}`), [id], { poll: 10000 })
  const [edit, setEdit] = useState(false)
  if (loading) return <Spinner />
  if (error || !c) return <ErrorNote error={error?.message} />

  return (
    <>
      <PageHeader title={c.display_name} sub={c.company ? c.name : undefined}
        actions={<>
          <Button onClick={() => setEdit(true)}><Pencil className="size-3.5" /> Edit</Button>
          <Link to={`/projects/new?client=${c.id}`} className={buttonCls('primary')}><Plus className="size-4" /> New project</Link>
        </>} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line-soft sm:grid-cols-4 [&>*]:bg-surface">
            <Stat label="Projects" value={c.stats?.total ?? 0} />
            <Stat label="Active" value={c.stats?.active ?? 0} />
            <Stat label="Paid" value={c.stats?.paid ?? 0} />
            <Stat label="Pending amount" value={money(c.stats?.pending_amount)} />
          </div>
          <Panel title="Project history" pad={false}>
            {c.projects?.length ? <ProjectTable projects={c.projects} showClient={false} /> : <Empty title="No projects yet" />}
          </Panel>
        </div>
        <div className="space-y-6">
          <MonthlyPanels client={c} />
          <Panel title="Details">
            <dl className="space-y-3 text-sm">
              {[['Email', c.email], ['Phone', c.phone], ['WhatsApp', c.whatsapp], ['GSTIN', c.gstin], ['Billing address', c.billing_address], ['Notes', c.notes]]
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k}><dt className="text-[13px] text-muted">{k}</dt><dd className="whitespace-pre-line text-ink">{v}</dd></div>
                ))}
            </dl>
          </Panel>
        </div>
      </div>
      {edit && <ClientForm open client={c} onClose={() => setEdit(false)} onSaved={() => { setEdit(false); reload() }} />}
    </>
  )
}
