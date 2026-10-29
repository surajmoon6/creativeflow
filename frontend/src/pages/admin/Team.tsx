import { KeyRound, Pencil, Plus, Shuffle, UserCog } from 'lucide-react'
import { useState } from 'react'
import { Button, CopyButton, Empty, ErrorNote, Field, Input, Modal, PageHeader, Panel, Pill, Spinner, useToast } from '../../components/ui'
import { useAsync } from '../../hooks/useAsync'
import { api, ApiError } from '../../services/api'
import type { ClientRecord } from '../../types'
import { makePassword } from '../../utils/password'
import { relative } from '../../utils/format'

interface Member {
  id: number; name: string; email: string; role: 'admin' | 'staff'; active: boolean; created_at: string
  client_ids: number[]; clients: { id: number; name: string }[]
}

export default function Team() {
  const { data, error, loading, reload } = useAsync(() => api.get<Member[]>('/api/team'), [], { poll: 20000 })
  const { data: clients } = useAsync(() => api.get<ClientRecord[]>('/api/clients'))
  const [editing, setEditing] = useState<Member | 'new' | null>(null)
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null)
  const toast = useToast()

  const toggle = async (m: Member) => {
    try { await api.put(`/api/team/${m.id}`, { active: !m.active }); toast(m.active ? `${m.name} switched off` : `${m.name} switched on`); reload() }
    catch (e) { alert((e as ApiError).message) }
  }

  if (loading) return <Spinner />
  if (error || !data) return <ErrorNote error={error?.message} />
  const staff = data.filter((m) => m.role === 'staff')

  return (
    <>
      <PageHeader title="Team" sub="Give employees their own sign-in, so your owner login stays with you."
        actions={<Button variant="primary" onClick={() => setEditing('new')}><Plus className="size-4" /> Add team member</Button>} />

      <div className="mb-6 rounded-xl border border-line bg-surface p-5 text-sm">
        <h2 className="font-semibold">What an employee can and can't do</h2>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <ul className="space-y-1 text-ink-2">
            <li className="font-medium text-ink">They can</li>
            <li>See and work on the clients you assign to them</li>
            <li>Read the brief and upload new versions of designs</li>
            <li>Read the client's change requests and add final files</li>
          </ul>
          <ul className="space-y-1 text-ink-2">
            <li className="font-medium text-ink">They never see</li>
            <li>Prices, quotes, invoices, payments or UPI details</li>
            <li>Other clients, or any client's phone, email or address</li>
            <li>The client's links, or the Settings and Team pages</li>
          </ul>
        </div>
        <p className="mt-3 text-[13px] text-muted">Switching an account off signs them out straight away. Every change an employee makes is marked with their name in the project's activity log, which only you can see.</p>
      </div>

      <Panel title={`Employees (${staff.length})`} pad={false}>
        {staff.length === 0 ? (
          <Empty title="No team members yet" action={<Button variant="primary" onClick={() => setEditing('new')}><Plus className="size-4" /> Add team member</Button>}>
            Add an employee, choose the clients they work on, and they can sign in at the same address as you.
          </Empty>
        ) : (
          <ul className="divide-y divide-line-soft">
            {staff.map((m) => (
              <li key={m.id} className="flex flex-wrap items-start gap-x-4 gap-y-2 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{m.name}</span>
                    <Pill tone={m.active ? 'ok' : 'neutral'}>{m.active ? 'Active' : 'Switched off'}</Pill>
                  </div>
                  <div className="text-[13px] text-muted">{m.email} · added {relative(m.created_at)}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.clients.length === 0
                      ? <span className="text-[13px] text-warn">No clients assigned yet, so they see nothing</span>
                      : m.clients.map((c) => <span key={c.id} className="rounded-full bg-line-soft px-2.5 py-0.5 text-xs text-ink-2">{c.name}</span>)}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" onClick={() => setEditing(m)}><Pencil className="size-3.5" /> Edit</Button>
                  <Button size="sm" variant={m.active ? 'secondary' : 'primary'} onClick={() => toggle(m)}>{m.active ? 'Switch off' : 'Switch on'}</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {editing && (
        <MemberForm key={editing === 'new' ? 'new' : editing.id} member={editing === 'new' ? null : editing} clients={clients ?? []}
          onClose={() => setEditing(null)}
          onSaved={(info) => { setEditing(null); reload(); if (info) setCreated(info); else toast('Saved') }} />
      )}

      <Modal open={!!created} onClose={() => setCreated(null)} title="Share these sign-in details"
        footer={<Button variant="primary" onClick={() => setCreated(null)}>Done</Button>}>
        {created && (
          <>
            <p className="text-sm text-ink-2">The password is shown only now. Send it to them privately, and ask them to keep it to themselves.</p>
            <dl className="mt-4 space-y-2 rounded-lg bg-canvas p-3 text-sm">
              <div className="flex justify-between gap-3"><dt className="text-muted">Sign in at</dt><dd className="break-all font-medium">{window.location.origin}/login</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-muted">Email</dt><dd className="break-all font-medium">{created.email}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-muted">Password</dt><dd className="font-mono font-medium">{created.password}</dd></div>
            </dl>
            <div className="mt-3">
              <CopyButton text={`Sign in at ${window.location.origin}/login\nEmail: ${created.email}\nPassword: ${created.password}`} label="Copy all three" copied="Copied" />
            </div>
          </>
        )}
      </Modal>
    </>
  )
}

function MemberForm({ member, clients, onClose, onSaved }: {
  member: Member | null; clients: ClientRecord[]; onClose: () => void; onSaved: (created?: { email: string; password: string }) => void
}) {
  const [name, setName] = useState(member?.name ?? '')
  const [email, setEmail] = useState(member?.email ?? '')
  const [password, setPassword] = useState(member ? '' : makePassword())
  const [ids, setIds] = useState<number[]>(member?.client_ids ?? [])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const toggle = (id: number) => setIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      if (member) {
        await api.put(`/api/team/${member.id}`, { name, client_ids: ids, ...(password ? { password } : {}) })
        onSaved(password ? { email: member.email, password } : undefined)
      } else {
        await api.post('/api/team', { name, email, password, client_ids: ids })
        onSaved({ email, password })
      }
    } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false) }
  }

  return (
    <Modal open onClose={onClose} title={member ? `Edit ${member.name}` : 'Add a team member'} wide
      footer={<><Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={!name.trim() || (!member && (!email.trim() || password.length < 10))} onClick={save}>{member ? 'Save changes' : 'Create account'}</Button></>}>
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="Priya Sharma" /></Field>
          <Field label="Email (their sign-in)"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!!member} placeholder="priya@yourstudio.in" /></Field>
        </div>
        <Field label={member ? 'Set a new password (leave empty to keep theirs)' : 'Password'} hint="At least 10 characters. They can't change it themselves yet, so you can reset it here any time.">
          <div className="flex gap-2">
            <Input value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" className="font-mono" placeholder={member ? 'New password' : ''} />
            <Button type="button" onClick={() => setPassword(makePassword())} aria-label="Generate a password"><Shuffle className="size-4" /> Generate</Button>
          </div>
        </Field>
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium"><UserCog className="size-3.5 text-muted" /> Clients this person works on</div>
          {clients.length === 0 ? <p className="text-sm text-muted">Add a client first, then assign it here.</p> : (
            <ul className="max-h-56 divide-y divide-line-soft overflow-auto rounded-lg border border-line-soft">
              {clients.map((c) => (
                <li key={c.id}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2.5 text-sm hover:bg-canvas">
                    <input type="checkbox" checked={ids.includes(c.id)} onChange={() => toggle(c.id)} className="size-4 accent-[var(--brand)]" />
                    <span className="min-w-0 flex-1 truncate">{c.display_name}</span>
                    <span className="shrink-0 text-xs text-muted">{c.projects?.length ?? ''}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted"><KeyRound className="size-3" /> They see only the projects of the clients ticked here.</p>
        </div>
        <ErrorNote error={err} />
      </div>
    </Modal>
  )
}
