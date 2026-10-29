import { Link, useNavigate } from 'react-router-dom'
import { useAdmin } from '../layouts/AdminLayout'
import type { ProjectSummary } from '../types'
import { money, relative, shortDate } from '../utils/format'
import { StatusPill } from './ui'

/** Cards on phones, a full table from tablet width up. */
export function ProjectTable({ projects, showClient = true }: { projects: ProjectSummary[]; showClient?: boolean }) {
  const nav = useNavigate()
  const { isStaff } = useAdmin()
  return (
    <>
      <ul className="divide-y divide-line-soft md:hidden">
        {projects.map((p) => (
          <li key={p.id}>
            <Link to={`/projects/${p.id}`} className="block px-4 py-3.5 active:bg-canvas">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-ink">{p.name}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    <span className="tabular-nums">{p.code}</span>
                    {showClient && <> · {p.client.name}</>} · {p.project_type}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <StatusPill status={p.status} staff={isStaff} />
                  {p.pending_payment && <span className="size-1.5 rounded-full bg-warn" title="Payment to confirm" />}
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3 text-[13px] text-ink-2">
                {p.total > 0 && <span className="font-medium tabular-nums text-ink">{money(p.total)}</span>}
                <span className="text-right">
                  {p.due_date ? `Due ${shortDate(p.due_date)} · ` : ''}{relative(p.last_activity)}
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-line-soft text-left text-[13px] whitespace-nowrap text-muted">
              <th className="px-5 py-2.5 font-normal">Project</th>
              {showClient && <th className="px-3 py-2.5 font-normal">Client</th>}
              <th className="px-3 py-2.5 font-normal">Type</th>
              <th className="px-3 py-2.5 text-right font-normal">Amount</th>
              <th className="px-3 py-2.5 font-normal">Status</th>
              <th className="px-3 py-2.5 font-normal">Last activity</th>
              <th className="px-3 py-2.5 font-normal">Due</th>
              <th className="px-5 py-2.5"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {projects.map((p) => (
              <tr key={p.id} onClick={() => nav(`/projects/${p.id}`)} className="cursor-pointer hover:bg-canvas/70">
                <td className="px-5 py-3">
                  <div className="font-medium text-ink">{p.name}</div>
                  <div className="text-xs text-muted tabular-nums">{p.code}</div>
                </td>
                {showClient && <td className="px-3 py-3 text-ink-2">{p.client.name}</td>}
                <td className="px-3 py-3 text-ink-2">{p.project_type}</td>
                <td className="px-3 py-3 text-right whitespace-nowrap tabular-nums">{p.total > 0 ? money(p.total) : ''}</td>
                <td className="px-3 py-3">
                  <div className="flex items-center gap-1.5">
                    <StatusPill status={p.status} staff={isStaff} />
                    {p.pending_payment && <span className="size-1.5 rounded-full bg-warn" title="Payment to confirm" />}
                  </div>
                </td>
                <td className="px-3 py-3 whitespace-nowrap text-ink-2">{relative(p.last_activity)}</td>
                <td className="px-3 py-3 whitespace-nowrap text-ink-2">{shortDate(p.due_date)}</td>
                <td className="px-5 py-3 text-right">
                  <Link to={`/projects/${p.id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-ink hover:underline">View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
