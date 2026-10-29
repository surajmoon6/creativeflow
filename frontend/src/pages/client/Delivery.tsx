import { CircleCheck, Download, FileText, Image as ImageIcon } from 'lucide-react'
import { useState } from 'react'
import { Button, ErrorNote } from '../../components/ui'
import { api, ApiError } from '../../services/api'
import type { FileInfo } from '../../types'
import { bytes, date, fileKind } from '../../utils/format'
import { usePortal } from './Portal'

export default function Delivery() {
  const { view, token, refresh } = usePortal()
  const d = view.delivery
  if (!d) return <p className="text-ink-2">Final files are available after payment confirmation.</p>
  const confirmed = view.payment?.confirmed

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-10">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-[-0.01em]">
          <CircleCheck className="size-5 text-ok" aria-hidden /> Payment received
        </h2>
        <p className="mt-1 text-[15px] text-ink-2">Your final files are ready.</p>

        <ul className="mt-6 divide-y divide-line-soft rounded-xl border border-line bg-surface">
          {d.files.map((f) => <FileRow key={f.id} f={f} token={token} max={d.max_downloads} onDone={refresh} />)}
        </ul>
        <p className="mt-3 text-xs text-muted">
          {d.expires_at ? `Downloads are available until ${date(d.expires_at)}. ` : ''}
          Save your files somewhere safe once downloaded.
        </p>
      </div>

      <aside>
        <dl className="space-y-3 rounded-xl border border-line bg-surface p-5 text-sm">
          <Meta label="Project">{view.name}</Meta>
          {confirmed && <Meta label="Payment reference">{confirmed.reference}</Meta>}
          {view.invoice && <Meta label="Invoice">{view.invoice.number}</Meta>}
          <Meta label="Payment confirmed">{date(d.paid_at)}</Meta>
          {d.delivered_at && <Meta label="Delivered">{date(d.delivered_at)}</Meta>}
        </dl>
      </aside>
    </div>
  )
}

function FileRow({ f, token, max, onDone }: { f: FileInfo; token: string; max: number | null; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const kind = fileKind(f)
  const left = max ? max - (f.downloads ?? 0) : null
  const download = async () => {
    setBusy(true); setErr(null)
    try {
      const { url } = await api.post<{ url: string }>(`/api/r/${token}/files/${f.id}/link`)
      const a = document.createElement('a')
      a.href = url
      a.rel = 'noopener'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.setTimeout(onDone, 1500)
    } catch (e) {
      setErr((e as ApiError).message)
    } finally {
      setBusy(false)
    }
  }
  const Icon = f.mime.startsWith('image/') ? ImageIcon : FileText
  return (
    <li className="flex flex-wrap items-center gap-4 px-5 py-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-canvas text-ink-2"><Icon className="size-5" aria-hidden /></span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{f.label || f.name}</p>
        <p className="text-[13px] text-muted">
          {kind}
          {f.width && f.height ? `, ${f.width} × ${f.height}` : ''}
          {`, ${bytes(f.size)}`}
          {left !== null ? ` — ${left} download${left === 1 ? '' : 's'} left` : ''}
        </p>
        {err && <div className="mt-2"><ErrorNote error={err} /></div>}
      </div>
      <Button variant="primary" onClick={download} loading={busy} disabled={left === 0} className="w-full sm:w-auto">
        <Download className="size-4" aria-hidden /> Download {kind}
      </Button>
    </li>
  )
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="mt-0.5 break-words text-ink">{children}</dd>
    </div>
  )
}
