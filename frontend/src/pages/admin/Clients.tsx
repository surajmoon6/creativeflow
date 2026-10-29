import { Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Empty, ErrorNote, Field, Input, Modal, PageHeader, Panel, Spinner, Textarea } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api, ApiError } from '../../services/api'
import type { ClientRecord } from '../../types'
import { money } from '../../utils/format'

export default function Clients() {
  const nav = useNavigate()
  const { data, error, loading, reload } = useAsync(() => api.get<ClientRecord[]>('/api/clients'), [], { poll: 15000 })
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const shown = useMemo(() => {
    const n = q.trim().toLowerCase()
    return (data ?? []).filter((c) => !n || `${c.name} ${c.company ?? ''} ${c.email ?? ''} ${c.phone ?? ''}`.toLowerCase().includes(n))
  }, [data, q])

  return (
    <>
      <PageHeader title="Clients" actions={<Button variant="primary" onClick={() => setOpen(true)}><Plus className="size-4" /> New client</Button>} />
      <div className="relative mb-4 w-full sm:w-72">
        <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-faint" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search clients" className="pl-9" aria-label="Search clients" />
      </div>
      <Panel pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><ErrorNote error={error.message} /></div> : !shown.length ? (
          <Empty title="No clients yet" action={<Button variant="primary" onClick={() => setOpen(true)}>Add a client</Button>}>
            Clients hold contact and billing details used on review links and invoices.
          </Empty>
        ) : (
          <>
          <ul className="divide-y divide-line-soft md:hidden">
            {shown.map((c) => (
              <li key={c.id}>
                <Link to={`/clients/${c.id}`} className="block px-4 py-3.5 active:bg-canvas">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium">{c.display_name}</div>
                      {c.company && <div className="text-xs text-muted">{c.name}</div>}
                    </div>
                    {!!c.stats?.pending_amount && <span className="shrink-0 text-[13px] font-medium text-warn tabular-nums">{money(c.stats.pending_amount)} due</span>}
                  </div>
                  <div className="mt-1 text-[13px] text-ink-2">{c.whatsapp || c.phone || c.email || '—'}</div>
                  <div className="mt-0.5 text-xs text-muted">{c.stats?.total ?? 0} project{c.stats?.total === 1 ? '' : 's'}, {c.stats?.active ?? 0} active</div>
                </Link>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line-soft text-left text-[13px] text-muted">
                  <th className="px-5 py-2.5 font-normal">Client</th>
                  <th className="px-3 py-2.5 font-normal">Contact</th>
                  <th className="px-3 py-2.5 text-right font-normal">Projects</th>
                  <th className="px-3 py-2.5 text-right font-normal">Active</th>
                  <th className="px-5 py-2.5 text-right font-normal">Pending</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {shown.map((c) => (
                  <tr key={c.id} onClick={() => nav(`/clients/${c.id}`)} className="cursor-pointer hover:bg-canvas/70">
                    <td className="px-5 py-3">
                      <div className="font-medium">{c.display_name}</div>
                      {c.company && <div className="text-xs text-muted">{c.name}</div>}
                    </td>
                    <td className="px-3 py-3 text-ink-2">
                      <div>{c.whatsapp || c.phone || '—'}</div>
                      {c.email && <div className="text-xs text-muted">{c.email}</div>}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{c.stats?.total}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{c.stats?.active}</td>
                    <td className="px-5 py-3 text-right tabular-nums">{c.stats?.pending_amount ? money(c.stats.pending_amount) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
      </Panel>
      <ClientForm open={open} onClose={() => setOpen(false)} onSaved={(c) => { setOpen(false); reload(); nav(`/clients/${c.id}`) }} />
    </>
  )
}

const EMPTY = { name: '', company: '', email: '', phone: '', whatsapp: '', billing_address: '', gstin: '', notes: '' }

export function ClientForm({ open, onClose, onSaved, client }:
  { open: boolean; onClose: () => void; onSaved: (c: ClientRecord) => void; client?: ClientRecord }) {
  const [f, setF] = useState(() => client ? { ...EMPTY, ...Object.fromEntries(Object.entries(client).map(([k, v]) => [k, v ?? ''])) } : EMPTY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })
  const save = async (e?: React.FormEvent) => {
    e?.preventDefault()
    e?.stopPropagation() // rendered in a portal; don't let the submit bubble to a parent form
    setBusy(true); setErr(null)
    try {
      const body = Object.fromEntries(Object.keys(EMPTY).map((k) => [k, (f as Record<string, string>)[k]]))
      const c = client ? await api.put<ClientRecord>(`/api/clients/${client.id}`, body) : await api.post<ClientRecord>('/api/clients', body)
      if (!client) setF(EMPTY)
      onSaved(c)
    } catch (e2) {
      setErr((e2 as ApiError).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} wide title={client ? 'Edit client' : 'New client'}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => save()}>{client ? 'Save changes' : 'Create client'}</Button></>}>
      <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
        <Field label="Contact name"><Input value={f.name} onChange={set('name')} required autoFocus /></Field>
        <Field label="Company"><Input value={f.company} onChange={set('company')} /></Field>
        <Field label="Email"><Input type="email" value={f.email} onChange={set('email')} /></Field>
        <Field label="Phone"><Input type="tel" value={f.phone} onChange={set('phone')} /></Field>
        <Field label="WhatsApp number" hint="10-digit numbers get +91 when sharing."><Input type="tel" value={f.whatsapp} onChange={set('whatsapp')} /></Field>
        <Field label="GSTIN" hint="Optional"><Input value={f.gstin} onChange={set('gstin')} maxLength={15} className="uppercase" /></Field>
        <Field label="Billing address" className="sm:col-span-2"><Textarea rows={2} value={f.billing_address} onChange={set('billing_address')} /></Field>
        <Field label="Notes" hint="Only visible to you." className="sm:col-span-2"><Textarea rows={2} value={f.notes} onChange={set('notes')} /></Field>
        <button type="submit" hidden />
        <div className="sm:col-span-2"><ErrorNote error={err} /></div>
      </form>
    </Modal>
  )
}
