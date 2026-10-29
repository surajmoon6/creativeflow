import { useEffect, useRef, useState } from 'react'
import { Button, ErrorNote, Field, Input, PageHeader, Panel, Select, Spinner, Textarea, useToast } from '../../components/ui'
import { useAdmin } from '../../layouts/AdminLayout'
import { api, ApiError } from '../../services/api'
import type { Settings as S } from '../../types'
import { toPaise, toRupees } from '../../utils/format'

export default function Settings() {
  const { reloadSettings } = useAdmin()
  const toast = useToast()
  const [s, setS] = useState<S | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.get<S>('/api/settings').then(setS) }, [])
  if (!s) return <Spinner />

  const v = (k: string) => (s[k] ?? '') as string
  const set = (k: string, val: string | number | boolean) => setS({ ...s, [k]: val })
  const text = (k: string) => ({ value: v(k), onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => set(k, e.target.value) })
  const num = (k: string) => ({ type: 'number', value: String(s[k] ?? ''), onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value) })

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    const body: S = { ...s }
    for (const k of ['gst_rate_bp_default', 'default_revisions', 'preview_max_px', 'delivery_days', 'max_downloads', 'project_next', 'invoice_next', 'quote_next', 'quote_valid_days', 'quote_advance_percent', 'advance_reminder_days']) body[k] = Number(s[k])
    for (const k of ['preview_scale', 'watermark_opacity']) body[k] = Number(s[k])
    delete body.logo_file_id; delete body.upi_qr_file_id
    try { setS(await api.put<S>('/api/settings', body)); reloadSettings(); toast('Settings saved') }
    catch (e2) { setErr((e2 as ApiError).message) } finally { setBusy(false) }
  }

  return (
    <form onSubmit={save}>
      <PageHeader title="Settings" actions={<Button type="submit" variant="primary" loading={busy}>Save settings</Button>} />
      <div className="mb-4 hidden sm:block"><ErrorNote error={err} /></div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Studio">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Studio name"><Input {...text('brand_name')} required /></Field>
            <Field label="Brand color" hint="Used for buttons and highlights on client pages.">
              <div className="flex gap-2">
                <input type="color" value={v('brand_color')} onChange={(e) => set('brand_color', e.target.value)} className="h-9 w-11 cursor-pointer rounded-md border border-line bg-surface p-1" aria-label="Pick brand color" />
                <Input {...text('brand_color')} pattern="#[0-9a-fA-F]{6}" />
              </div>
            </Field>
            <Field label="Email" hint="Shown to clients; also receives notifications when SMTP is set up."><Input type="email" {...text('studio_email')} /></Field>
            <Field label="Phone"><Input {...text('studio_phone')} /></Field>
            <Field label="WhatsApp number" hint="Clients can send their payment screenshot here. Include the country code, for example 919876543210."><Input {...text('studio_whatsapp')} inputMode="tel" /></Field>
            <Field label="Address" className="sm:col-span-2" hint="Printed on invoices."><Textarea rows={2} {...text('studio_address')} /></Field>
            <Field label="Studio GSTIN" hint="Printed on invoices when set."><Input {...text('studio_gstin')} maxLength={15} className="uppercase" /></Field>
            <ImageSetting label="Logo" kind="logo" has={!!s.logo_file_id} src="/api/brand/logo" onChange={setS} />
          </div>
        </Panel>

        <Panel title="UPI payments">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="UPI ID" hint="The invoice shows a QR with the exact amount and project reference filled in."><Input {...text('upi_id')} placeholder="studio@okaxis" /></Field>
            <Field label="Payee name"><Input {...text('upi_payee_name')} placeholder={v('brand_name')} /></Field>
            <div className="sm:col-span-2">
              <ImageSetting label="Static QR image (fallback)" kind="upi_qr" has={!!s.upi_qr_file_id} onChange={setS}
                hint="Only used when no UPI ID is set. Clients will have to type the amount themselves." />
            </div>
          </div>
        </Panel>

        <Panel title="Invoices and pricing">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input type="checkbox" checked={!!s.gst_enabled_default} onChange={(e) => set('gst_enabled_default', e.target.checked)} className="size-4 accent-[var(--brand)]" />
              Apply GST to new projects by default
            </label>
            <Field label="Default GST rate (%)"><Input type="number" step="0.01" value={String(Number(s.gst_rate_bp_default) / 100)} onChange={(e) => set('gst_rate_bp_default', Math.round(Number(e.target.value) * 100))} /></Field>
            <Field label="Currency"><Input value="INR (₹)" disabled /></Field>
            <Field label="Default payment terms" className="sm:col-span-2"><Input {...text('payment_terms')} /></Field>
            <Field label="Revisions per design" hint="Included on new quotes and projects."><Input {...num('default_revisions')} min={0} /></Field>
            <Field label="Each extra revision (₹)"><Input type="number" value={String(toRupees(Number(s.default_extra_revision_price)))} onChange={(e) => set('default_extra_revision_price', toPaise(e.target.value))} /></Field>
            <Field label="Invoice prefix"><Input {...text('invoice_prefix')} /></Field>
            <Field label="Next invoice number"><Input {...num('invoice_next')} min={1} /></Field>
            <Field label="Project prefix"><Input {...text('project_prefix')} /></Field>
            <Field label="Next project number"><Input {...num('project_next')} min={1} /></Field>
          </div>
        </Panel>

        <Panel title="Quotations">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Quote prefix"><Input {...text('quote_prefix')} /></Field>
            <Field label="Next quote number"><Input {...num('quote_next')} min={1} /></Field>
            <Field label="Advance (%)" hint="Asked for on new quotes. 0 for none."><Input {...num('quote_advance_percent')} min={0} max={100} /></Field>
            <Field label="Remind me about unpaid advances after (days)"><Input {...num('advance_reminder_days')} min={1} /></Field>
            <Field label="Valid for (days)" hint="Used for new quotes. A quote you already made keeps its own date; change it on the quote." className="sm:col-span-2"><Input {...num('quote_valid_days')} min={1} max={365} /></Field>
            <Field label="Invoice thank-you note" hint="Shown at the foot of every invoice until it is paid. Use {client} and {studio}." className="sm:col-span-2"><Textarea rows={3} {...text('invoice_closing')} /></Field>
            <Field label="Invoice note after payment" hint="Replaces it once the invoice is paid." className="sm:col-span-2"><Textarea rows={3} {...text('invoice_closing_paid')} /></Field>
            <Field label="Closing message" hint="A friendly note at the end of every new quote. Use {client} and {studio}. You can change it on each quote." className="sm:col-span-2"><Textarea rows={4} {...text('quote_closing')} /></Field>
            <Field label="Default terms" hint="Added to every new quote. You can change them on each quote." className="sm:col-span-2"><Textarea rows={5} {...text('quote_terms')} /></Field>
          </div>
        </Panel>

        <Panel title="Preview and watermark">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Watermark text" className="sm:col-span-2" hint="Repeated across the preview with the client name, project number and studio name."><Input {...text('watermark_text')} /></Field>
            <Field label="Longest side (px)" hint="Previews are never larger than this."><Input {...num('preview_max_px')} min={300} max={2400} /></Field>
            <Field label="Scale of original (%)" hint="And never more than this share of the original.">
              <Input type="number" min={20} max={95} value={String(Math.round(Number(s.preview_scale) * 100))} onChange={(e) => set('preview_scale', Number(e.target.value) / 100)} />
            </Field>
            <Field label={`Watermark opacity — ${Math.round(Number(s.watermark_opacity) * 100)}%`} className="sm:col-span-2" hint="Applies to versions uploaded after saving.">
              <input type="range" min={8} max={85} value={Math.round(Number(s.watermark_opacity) * 100)} onChange={(e) => set('watermark_opacity', Number(e.target.value) / 100)} className="w-full accent-[var(--brand)]" />
            </Field>
          </div>
        </Panel>

        <Panel title="Links and delivery">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New review links expire">
              <Select {...text('review_link_expiry')}>
                <option value="24h">After 24 hours</option><option value="3d">After 3 days</option><option value="7d">After 7 days</option>
                <option value="30d">After 30 days</option><option value="never">Never</option>
              </Select>
            </Field>
            <Field label="Downloads available for (days)" hint="0 keeps them available."><Input {...num('delivery_days')} min={0} /></Field>
            <Field label="Downloads per file" hint="0 for unlimited."><Input {...num('max_downloads')} min={0} /></Field>
          </div>
        </Panel>

        <Panel title="WhatsApp messages">
          <p className="mb-4 text-[13px] text-muted">Use {'{client}'}, {'{project}'} and {'{link}'}; the link is required. Quotes also have {'{number}'}, {'{total}'} and {'{valid_until}'}; advance reminders have {'{amount}'}.</p>
          <div className="space-y-4">
            <Field label="Ready for review"><Textarea rows={5} {...text('wa_review')} /></Field>
            <Field label="Approved, ready for payment"><Textarea rows={5} {...text('wa_payment')} /></Field>
            <Field label="Files delivered"><Textarea rows={5} {...text('wa_delivery')} /></Field>
            <Field label="Quotation"><Textarea rows={6} {...text('wa_quote')} /></Field>
            <Field label="Advance reminder"><Textarea rows={5} {...text('wa_advance')} /></Field>
          </div>
        </Panel>
      </div>
      <div className="sticky bottom-0 z-20 -mx-4 mt-6 border-t border-line bg-surface/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:hidden">
        {err && <div className="mb-2"><ErrorNote error={err} /></div>}
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}>Save settings</Button>
      </div>
    </form>
  )
}

function ImageSetting({ label, kind, has, src, hint, onChange }:
  { label: string; kind: 'logo' | 'upi_qr'; has: boolean; src?: string; hint?: string; onChange: (s: S) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [bust, setBust] = useState(0)
  const upload = async () => {
    const f = ref.current?.files?.[0]
    if (!f) return
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.set('file', f)
    try { onChange(await api.post<S>(`/api/settings/${kind}`, fd)); setBust(Date.now()) } catch (e) { setErr((e as ApiError).message) } finally { setBusy(false); if (ref.current) ref.current.value = '' }
  }
  return (
    <div>
      <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span>
      <div className="flex items-center gap-3">
        {has && src && <img src={`${src}?v=${bust}`} alt="" className="h-9 max-w-[120px] rounded border border-line object-contain p-1" />}
        <Button type="button" size="sm" loading={busy} onClick={() => ref.current?.click()}>{has ? 'Replace' : 'Upload'}</Button>
        {has && <Button type="button" size="sm" variant="ghost" onClick={async () => onChange(await api.del<S>(`/api/settings/${kind}`))}>Remove</Button>}
        <input ref={ref} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} />
      </div>
      {hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
      {err && <div className="mt-2"><ErrorNote error={err} /></div>}
    </div>
  )
}
