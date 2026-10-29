import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import FileDrop from '../../components/FileDrop'
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select, Spinner, Textarea } from '../../components/ui'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { ClientRecord, ProjectDetail } from '../../types'
import { money, toPaise, toRupees } from '../../utils/format'
import { ClientForm } from './Clients'

const TYPES = ['Instagram Poster', 'Instagram Post', 'Instagram Story', 'Event Banner', 'Poster', 'Flyer', 'Brochure',
  'Digital Advertisement', 'Social Media Pack', 'Video']
const SIZES: Record<string, [number, number]> = {
  'Instagram Poster': [1080, 1350], 'Instagram Post': [1080, 1080], 'Instagram Story': [1080, 1920], 'Event Banner': [1920, 1080],
}

type Form = Record<string, string | boolean>

export default function ProjectForm() {
  const { id } = useParams()
  const editing = !!id
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { settings } = useAdmin()
  const [clients, setClients] = useState<ClientRecord[] | null>(null)
  const [f, setF] = useState<Form | null>(null)
  const [newClient, setNewClient] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)

  useEffect(() => { api.get<ClientRecord[]>('/api/clients').then(setClients) }, [])
  // Load an existing project once. Depending on the form's own state here would re-run the load forever
  // and overwrite whatever you have just typed.
  useEffect(() => {
    if (!editing) return
    api.get<ProjectDetail>(`/api/projects/${id}`).then((p) => setF({
      client_id: String(p.client.id), name: p.name, project_type: p.project_type, description: p.description ?? '',
      internal_notes: p.internal_notes ?? '', width: p.width ? String(p.width) : '', height: p.height ? String(p.height) : '',
      format: p.format ?? '', quantity: String(p.quantity), deliverable_types: p.deliverable_types ?? '',
      amount: String(toRupees(p.amount)), discount: String(toRupees(p.discount)), gst_enabled: p.gst_enabled,
      gst_rate: String(p.gst_rate_bp / 100), due_date: p.due_date ?? '', payment_terms: p.payment_terms ?? '',
      revisions_included: String(p.revisions_included), extra_revision_price: String(toRupees(p.extra_revision_price)),
    }))
  }, [editing, id])

  // Starting values for a new project, once the settings are known.
  useEffect(() => {
    if (editing || !settings) return
    setF((cur) => cur ?? {
      client_id: params.get('client') ?? '', name: '', project_type: 'Instagram Poster', description: '', internal_notes: '',
      width: '1080', height: '1350', format: 'JPG + PNG', quantity: '1', deliverable_types: 'JPG, PNG', amount: '',
      discount: '0', gst_enabled: !!settings.gst_enabled_default, gst_rate: String(Number(settings.gst_rate_bp_default) / 100),
      due_date: '', payment_terms: String(settings.payment_terms ?? ''), revisions_included: String(settings.default_revisions),
      extra_revision_price: String(toRupees(Number(settings.default_extra_revision_price))),
    })
  }, [editing, settings, params])

  const totals = useMemo(() => {
    if (!f) return null
    const amount = toPaise(f.amount as string), discount = Math.max(0, Math.min(toPaise(f.discount as string), amount))
    const taxable = amount - discount
    const tax = f.gst_enabled ? Math.round((taxable * Number(f.gst_rate || 0)) / 100) : 0
    return { amount, discount, tax, total: taxable + tax }
  }, [f])

  if (!f || !clients) return <Spinner />
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const v = e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value
    const next = { ...f, [k]: v }
    if (k === 'project_type' && SIZES[v as string] && !editing) [next.width, next.height] = SIZES[v as string].map(String)
    setF(next)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    const body = {
      ...f,
      client_id: Number(f.client_id),
      amount: toPaise(f.amount as string), discount: toPaise(f.discount as string),
      extra_revision_price: toPaise(f.extra_revision_price as string),
      gst_rate_bp: Math.round(Number(f.gst_rate || 0) * 100),
    }
    try {
      const p = editing ? await api.put<ProjectDetail>(`/api/projects/${id}`, body) : await api.post<ProjectDetail>('/api/projects', body)
      const first = file.current?.files?.[0]
      let uploadError: string | undefined
      if (!editing && first) {
        const fd = new FormData()
        fd.set('file', first)
        await api.post(`/api/projects/${p.id}/versions`, fd).catch((e2: ApiError) => { uploadError = `The project was created, but the design file could not be uploaded: ${e2.message} Upload it again below.` })
      }
      nav(`/projects/${p.id}`, { state: uploadError ? { uploadError } : undefined })
    } catch (e2) {
      setErr((e2 as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <PageHeader title={editing ? 'Edit project' : 'New project'}
        actions={<><Button type="button" onClick={() => nav(-1)}>Cancel</Button><Button type="submit" variant="primary" loading={busy}>{editing ? 'Save changes' : 'Create project'}</Button></>} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <Panel title="Basics">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Project name" className="sm:col-span-2"><Input value={f.name as string} onChange={set('name')} required placeholder="Nagpur Marathon 2026" autoFocus={!editing} /></Field>
              <Field label="Client">
                <div className="flex gap-2">
                  <Select value={f.client_id as string} onChange={set('client_id')} required>
                    <option value="">Choose a client</option>
                    {clients.map((c) => <option key={c.id} value={c.id}>{c.display_name}</option>)}
                  </Select>
                  <Button type="button" onClick={() => setNewClient(true)}>New</Button>
                </div>
              </Field>
              <Field label="Project type">
                <Input list="types" value={f.project_type as string} onChange={set('project_type')} required />
                <datalist id="types">{TYPES.map((t) => <option key={t} value={t} />)}</datalist>
              </Field>
              <Field label="Description" className="sm:col-span-2"><Textarea rows={2} value={f.description as string} onChange={set('description')} /></Field>
              <Field label="Internal notes" hint="Never shown to the client." className="sm:col-span-2"><Textarea rows={2} value={f.internal_notes as string} onChange={set('internal_notes')} /></Field>
            </div>
          </Panel>

          <Panel title="Creative">
            <div className="grid gap-4 sm:grid-cols-4">
              <Field label="Width (px)"><Input type="number" min={1} value={f.width as string} onChange={set('width')} /></Field>
              <Field label="Height (px)"><Input type="number" min={1} value={f.height as string} onChange={set('height')} /></Field>
              <Field label="Format"><Input value={f.format as string} onChange={set('format')} placeholder="JPG + PNG" /></Field>
              <Field label="Quantity"><Input type="number" min={1} value={f.quantity as string} onChange={set('quantity')} /></Field>
              <Field label="Deliverables" hint="What the client receives after payment." className="sm:col-span-4"><Input value={f.deliverable_types as string} onChange={set('deliverable_types')} placeholder="JPG, PNG, Print PDF" /></Field>
            </div>
          </Panel>

          {!editing && (
            <Panel title="First version">
              <Field label="Design file" hint="PNG, JPG, WEBP or PDF. A watermarked, reduced-resolution preview is generated from it; the client never receives this file. Final files are added after approval.">
                <FileDrop inputRef={file} accept=".png,.jpg,.jpeg,.webp,.pdf" title="Drag and drop the first design here" hint="or click to browse. PNG, JPG, WEBP or PDF" />
              </Field>
            </Panel>
          )}
        </div>

        <div className="space-y-6">
          <Panel title="Commercial">
            <div className="space-y-4">
              <Field label="Project amount (₹)"><Input type="number" min={0} step="0.01" value={f.amount as string} onChange={set('amount')} required /></Field>
              <Field label="Discount (₹)"><Input type="number" min={0} step="0.01" value={f.discount as string} onChange={set('discount')} /></Field>
              <div className="flex items-end gap-3">
                <label className="flex h-9 items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!f.gst_enabled} onChange={set('gst_enabled')} className="size-4 accent-[var(--brand)]" /> GST applies
                </label>
                {f.gst_enabled && <Field label="Rate (%)" className="w-24"><Input type="number" min={0} max={50} step="0.01" value={f.gst_rate as string} onChange={set('gst_rate')} /></Field>}
              </div>
              {totals && (
                <dl className="space-y-1 rounded-lg bg-canvas p-3 text-[13px] tabular-nums">
                  <div className="flex justify-between text-ink-2"><dt>Amount</dt><dd>{money(totals.amount)}</dd></div>
                  {totals.discount > 0 && <div className="flex justify-between text-ink-2"><dt>Discount</dt><dd>− {money(totals.discount)}</dd></div>}
                  {totals.tax > 0 && <div className="flex justify-between text-ink-2"><dt>GST</dt><dd>{money(totals.tax)}</dd></div>}
                  <div className="flex justify-between pt-1 font-semibold text-ink"><dt>Final amount</dt><dd>{money(totals.total)}</dd></div>
                </dl>
              )}
              <Field label="Due date"><Input type="date" value={f.due_date as string} onChange={set('due_date')} /></Field>
              <Field label="Payment terms"><Input value={f.payment_terms as string} onChange={set('payment_terms')} /></Field>
            </div>
          </Panel>
          <Panel title="Revisions">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Included"><Input type="number" min={0} max={50} value={f.revisions_included as string} onChange={set('revisions_included')} /></Field>
              <Field label="Each extra (₹)"><Input type="number" min={0} step="0.01" value={f.extra_revision_price as string} onChange={set('extra_revision_price')} /></Field>
            </div>
          </Panel>
          <div className="hidden sm:block"><ErrorNote error={err} /></div>
        </div>
      </div>
      <div className="sticky bottom-0 z-20 -mx-4 mt-6 border-t border-line bg-surface/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:hidden">
        {err && <div className="mb-2"><ErrorNote error={err} /></div>}
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}>{editing ? 'Save changes' : 'Create project'}</Button>
      </div>
      <ClientForm open={newClient} onClose={() => setNewClient(false)}
        onSaved={(c) => { setClients([...(clients ?? []), c]); setF({ ...f, client_id: String(c.id) }); setNewClient(false) }} />
    </form>
  )
}
