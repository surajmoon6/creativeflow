import { Download, ExternalLink } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Empty, ErrorNote, Modal, PageHeader, Panel, Pill, Spinner, Textarea, Field, buttonCls, cx, useToast } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { Activity, FileInfo, Invoice, Payment } from '../../types'
import { bytes, date, dateTime, fileKind, money, relative } from '../../utils/format'

type Inv = Invoice & { project: { id: number; code: string; name: string; client: string } }

const Th = ({ children, right }: { children?: React.ReactNode; right?: boolean }) =>
  <th className={cx('px-5 py-2.5 font-normal first:pl-5', right && 'text-right')}>{children}</th>

export function Invoices() {
  const { data, error, loading } = useAsync(() => api.get<Inv[]>('/api/invoices'), [], { poll: 15000 })
  const outstanding = (data ?? []).filter((i) => i.status === 'issued').reduce((s, i) => s + i.total, 0)
  return (
    <>
      <PageHeader title="Invoices" sub={data ? `${money(outstanding)} outstanding` : undefined} />
      <Panel pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div> : !data?.length ? (
          <Empty title="No invoices yet">Invoices are issued from a project once the client approves and final files are attached.</Empty>
        ) : (
          <>
          <ul className="divide-y divide-line-soft md:hidden">
            {data.map((i) => (
              <li key={i.id}>
                <Link to={`/invoices/${i.id}`} className="block px-4 py-3.5 active:bg-canvas">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium tabular-nums">{i.number}</span>
                    <Pill tone={i.status === 'paid' ? 'ok' : i.status === 'void' ? 'neutral' : 'warn'}>{i.status === 'paid' ? 'Paid' : i.status === 'void' ? 'Void' : 'Payment pending'}</Pill>
                  </div>
                  <div className="mt-1 text-[13px] text-ink-2">{i.project.name} <span className="text-muted">· {i.project.client}</span></div>
                  <div className="mt-1 flex items-center justify-between text-[13px]">
                    <span className="text-muted">Issued {date(i.issued_at)}</span>
                    <span className="font-medium tabular-nums">{money(i.total)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="border-b border-line-soft text-left text-[13px] text-muted"><Th>Invoice</Th><Th>Project</Th><Th>Issued</Th><Th right>Total</Th><Th>Status</Th><Th /></tr></thead>
              <tbody className="divide-y divide-line-soft">
                {data.map((i) => (
                  <tr key={i.id} className="hover:bg-canvas/70">
                    <td className="px-5 py-3 font-medium tabular-nums"><Link to={`/invoices/${i.id}`} className="underline-offset-2 hover:underline">{i.number}</Link></td>
                    <td className="px-5 py-3"><Link to={`/projects/${i.project.id}`} className="hover:underline">{i.project.name}</Link><div className="text-xs text-muted">{i.project.client}</div></td>
                    <td className="px-5 py-3 text-ink-2">{date(i.issued_at)}</td>
                    <td className="px-5 py-3 text-right tabular-nums">{money(i.total)}</td>
                    <td className="px-5 py-3"><Pill tone={i.status === 'paid' ? 'ok' : i.status === 'void' ? 'neutral' : 'warn'}>{i.status === 'paid' ? 'Paid' : i.status === 'void' ? 'Void' : 'Payment pending'}</Pill></td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1.5">
                        <a href={`/api/invoices/${i.id}/download?format=pdf`} download className={buttonCls('ghost', 'sm')} title="Download PDF"><Download className="size-3.5" /> PDF</a>
                        <Link to={`/invoices/${i.id}`} className={buttonCls('secondary', 'sm')}>{i.status === 'issued' ? 'View / edit' : 'View'}</Link>
                      </div>
                    </td>
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

export function Payments() {
  const { data, error, loading, reload } = useAsync(() => api.get<Payment[]>('/api/payments'), [], { poll: 10000 })
  const { bump } = useAdmin()
  const toast = useToast()
  const [deciding, setDeciding] = useState<{ pay: Payment; mode: 'confirm' | 'reject' } | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const go = async () => {
    if (!deciding) return
    setBusy(true); setErr(null)
    try {
      await api.post(`/api/${deciding.pay.kind === 'advance' ? 'advances' : 'payments'}/${deciding.pay.id}/${deciding.mode}`, deciding.mode === 'reject' ? { note } : {})
      toast(deciding.mode === 'confirm' ? (deciding.pay.kind === 'advance' ? 'Advance confirmed.' : 'Payment confirmed. Files released.') : 'Client asked to check the reference')
      setDeciding(null); setNote(''); reload(); bump()
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }
  const pending = (data ?? []).filter((p) => p.status === 'submitted')
  return (
    <>
      <PageHeader title="Payments" sub="Clients pay by UPI and share their reference. Files unlock only after you confirm." />
      {pending.length > 0 && (
        <Panel title={`To confirm (${pending.length})`} pad={false} className="mb-6 border-warn/40">
          <ul className="divide-y divide-line-soft">
            {pending.map((x) => (
              <li key={`${x.kind}-${x.id}`} className="flex flex-wrap items-center gap-4 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{money(x.amount)} <span className="font-normal text-ink-2">from {x.project?.client}</span></div>
                  <div className="text-[13px] text-ink-2">
                    {x.reference ? <>UPI ref <b className="font-semibold tabular-nums">{x.reference}</b></> : <b className="font-semibold">Screenshot only</b>} for <Link to={`/projects/${x.project?.id}`} className="underline underline-offset-2">{x.project?.name}</Link> ({x.kind === 'advance' ? 'advance' : x.invoice_number}), {relative(x.submitted_at)}
                  </div>
                  {x.proof_file_id && <a href={`/api/admin/files/${x.proof_file_id}?inline=1`} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[13px] font-medium underline underline-offset-2">Screenshot <ExternalLink className="size-3" /></a>}
                </div>
                <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto">
                  <Button onClick={() => setDeciding({ pay: x, mode: 'reject' })}>Can't find it</Button>
                  <Button variant="primary" onClick={() => setDeciding({ pay: x, mode: 'confirm' })}>Confirm received</Button>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel title="All payments" pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div> : !data?.length ? (
          <Empty title="No payments yet">When a client submits their UPI reference it appears here for you to confirm.</Empty>
        ) : (
          <>
          <ul className="divide-y divide-line-soft md:hidden">
            {data.map((x) => (
              <li key={`${x.kind}-${x.id}`} className="px-4 py-3.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium tabular-nums">{x.reference || 'Screenshot'}</span>
                  <Pill tone={x.status === 'confirmed' ? 'ok' : x.status === 'rejected' ? 'bad' : 'warn'}>{x.status === 'confirmed' ? 'Confirmed' : x.status === 'rejected' ? 'Not matched' : 'To confirm'}</Pill>
                </div>
                <div className="mt-1 text-[13px] text-ink-2"><Link to={`/projects/${x.project?.id}`} className="underline underline-offset-2">{x.project?.name}</Link> <span className="text-muted">· {x.kind === 'advance' ? 'Advance' : x.invoice_number}</span></div>
                <div className="mt-1 flex items-center justify-between text-[13px]">
                  <span className="text-muted">{dateTime(x.submitted_at)}</span>
                  <span className="font-medium tabular-nums">{money(x.amount)}</span>
                </div>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="border-b border-line-soft text-left text-[13px] text-muted"><Th>Reference</Th><Th>Project</Th><Th>Submitted</Th><Th right>Amount</Th><Th>Status</Th></tr></thead>
              <tbody className="divide-y divide-line-soft">
                {data.map((x) => (
                  <tr key={`${x.kind}-${x.id}`}>
                    <td className="px-5 py-3 tabular-nums">{x.reference || 'Screenshot'}</td>
                    <td className="px-5 py-3"><Link to={`/projects/${x.project?.id}`} className="hover:underline">{x.project?.name}</Link><div className="text-xs text-muted">{x.kind === 'advance' ? 'Advance' : x.invoice_number}</div></td>
                    <td className="px-5 py-3 text-ink-2">{dateTime(x.submitted_at)}</td>
                    <td className="px-5 py-3 text-right tabular-nums">{money(x.amount)}</td>
                    <td className="px-5 py-3"><Pill tone={x.status === 'confirmed' ? 'ok' : x.status === 'rejected' ? 'bad' : 'warn'}>{x.status === 'confirmed' ? 'Confirmed' : x.status === 'rejected' ? 'Not matched' : 'To confirm'}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
      </Panel>
      <Modal open={!!deciding} onClose={() => setDeciding(null)} title={deciding?.mode === 'confirm' ? 'Confirm this payment?' : 'Payment not found'}
        footer={<><Button onClick={() => setDeciding(null)}>Cancel</Button><Button variant={deciding?.mode === 'confirm' ? 'primary' : 'danger'} loading={busy} onClick={go}>{deciding?.mode === 'confirm' ? (deciding.pay.kind === 'advance' ? 'Confirm advance' : 'Confirm and release files') : 'Ask client to check'}</Button></>}>
        {deciding?.mode === 'confirm' ? (
          <p className="text-ink-2">Only confirm once you've seen <b>{money(deciding.pay.amount)}</b> {deciding.pay.reference ? <>with reference <b>{deciding.pay.reference}</b> </> : null}in your account.</p>
        ) : (
          <Field label="Message to the client (optional)"><Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={255} /></Field>
        )}
        <div className="mt-3"><ErrorNote error={err} /></div>
      </Modal>
    </>
  )
}

type FileRow = FileInfo & { project: { id: number; code: string; name: string; client: string } | null }

export function FilesPage() {
  const { data, error, loading } = useAsync(() => api.get<FileRow[]>('/api/files'))
  const [kind, setKind] = useState<'all' | 'final' | 'master'>('all')
  const shown = (data ?? []).filter((f) => kind === 'all' || f.kind === kind)
  return (
    <>
      <PageHeader title="Files" sub="Design uploads and final deliverables. All stored privately; nothing here has a public URL." />
      <div className="mb-4 flex gap-1">
        {(['all', 'final', 'master'] as const).map((k) => (
          <button key={k} onClick={() => setKind(k)} className={cx('h-8 rounded-md px-3 text-[13px]', kind === k ? 'bg-ink text-white' : 'text-ink-2 hover:bg-line-soft')}>
            {k === 'all' ? 'All' : k === 'final' ? 'Final files' : 'Design uploads'}
          </button>
        ))}
      </div>
      <Panel pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div> : !shown.length ? <Empty title="No files yet" /> : (
          <>
          <ul className="divide-y divide-line-soft md:hidden">
            {shown.map((f) => (
              <li key={f.id} className="flex items-center gap-3 px-4 py-3.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{f.label || f.name}</div>
                  <div className="text-xs text-muted">
                    {f.kind === 'final' ? 'Final' : 'Design upload'} · {fileKind(f)}{f.width ? `, ${f.width} × ${f.height}` : ''} · {bytes(f.size)}
                  </div>
                  {f.project && <Link to={`/projects/${f.project.id}`} className="text-[13px] text-ink-2 underline underline-offset-2">{f.project.name}</Link>}
                </div>
                <a href={`/api/admin/files/${f.id}`} className={buttonCls('secondary', 'sm')}>Download</a>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="border-b border-line-soft text-left text-[13px] text-muted"><Th>File</Th><Th>Project</Th><Th>Kind</Th><Th right>Size</Th><Th>Added</Th><Th /></tr></thead>
              <tbody className="divide-y divide-line-soft">
                {shown.map((f) => (
                  <tr key={f.id}>
                    <td className="px-5 py-3"><div className="font-medium">{f.label || f.name}</div><div className="text-xs text-muted">{fileKind(f)}{f.width ? `, ${f.width} × ${f.height}` : ''}</div></td>
                    <td className="px-5 py-3">{f.project && <><Link to={`/projects/${f.project.id}`} className="hover:underline">{f.project.name}</Link><div className="text-xs text-muted">{f.project.client}</div></>}</td>
                    <td className="px-5 py-3 text-ink-2">{f.kind === 'final' ? 'Final' : 'Design upload'}</td>
                    <td className="px-5 py-3 text-right text-ink-2 tabular-nums">{bytes(f.size)}</td>
                    <td className="px-5 py-3 text-ink-2">{date(f.created_at)}</td>
                    <td className="px-5 py-3 text-right"><a href={`/api/admin/files/${f.id}`} className="font-medium hover:underline">Download</a></td>
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

export function ActivityPage() {
  const { data, error, loading } = useAsync(() => api.get<Activity[]>('/api/activity?limit=300'), [], { poll: 15000 })
  return (
    <>
      <PageHeader title="Activity" sub="Every action on every project, newest first." />
      <Panel pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div> : !data?.length ? <Empty title="No activity yet" /> : (
          <ul className="divide-y divide-line-soft">
            {data.map((a) => (
              <li key={a.id} className="grid gap-1 px-5 py-3 text-sm sm:grid-cols-[150px_90px_1fr] sm:gap-4">
                <span className="text-muted tabular-nums">{dateTime(a.created_at)}</span>
                <span className={cx('text-[13px]', a.actor === 'client' ? 'font-medium text-brand' : 'text-muted')}>{a.actor === 'client' ? 'Client' : a.actor === 'system' ? 'System' : 'You'}</span>
                <span>
                  {a.message}
                  {a.project && <> — <Link to={`/projects/${a.project.id}`} className="text-ink-2 hover:underline">{a.project.name}</Link></>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  )
}
