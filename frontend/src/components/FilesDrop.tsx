import { FileText, ImageUp, X } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { bytes } from '../utils/format'
import { cx } from './ui'

const THUMB = (f: File) => f.type.startsWith('image/')

function Thumb({ file }: { file: File }) {
  const url = useMemo(() => (THUMB(file) ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  return url
    ? <img src={url} alt="" className="size-10 shrink-0 rounded object-cover" />
    : <span className="flex size-10 shrink-0 items-center justify-center rounded bg-canvas"><FileText className="size-4 text-muted" /></span>
}

/**
 * A drop zone for several files. Drag them in, tap to browse (a phone opens its gallery) or paste a screenshot.
 * The chosen files are kept in `files`; the caller sends them.
 */
export default function FilesDrop({ files, onChange, accept, max, maxMb = 10, title = 'Drag and drop photos or a PDF here', hint }: {
  files: File[]; onChange: (f: File[]) => void; accept: string; max: number; maxMb?: number; title?: string; hint?: string
}) {
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [warn, setWarn] = useState<string | null>(null)
  const allowed = accept.split(',').map((a) => a.trim().toLowerCase())
  const ok = (f: File) => {
    const ext = '.' + (f.name.split('.').pop() ?? '').toLowerCase()
    return allowed.some((a) => a === ext || a === f.type)
  }

  const take = (list: FileList | File[] | null) => {
    if (!list) return
    const next = [...files]
    const problems: string[] = []
    for (const f of Array.from(list)) {
      if (!ok(f)) problems.push(`${f.name}: only ${allowed.filter((a) => a.startsWith('.')).join(', ').replaceAll('.', '').toUpperCase()} files`)
      else if (f.size > maxMb * 1024 * 1024) problems.push(`${f.name}: over ${maxMb} MB`)
      else if (next.length >= max) problems.push(`Only ${max} files fit on one post`)
      else if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f)
    }
    setWarn(problems.length ? [...new Set(problems)].join('. ') + '.' : null)
    onChange(next)
    if (input.current) input.current.value = ''
  }

  return (
    <div>
      <label htmlFor={id} tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click() } }}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}
        onPaste={(e) => take(e.clipboardData.files)}
        className={cx('flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors',
          over ? 'border-ink bg-canvas' : 'border-line hover:border-faint')}>
        <ImageUp className="size-6 text-muted" aria-hidden />
        <span className="text-sm font-medium">{title}</span>
        <span className="text-[13px] text-muted">{hint ?? 'or tap to choose from your phone or computer'}</span>
      </label>
      <input ref={input} id={id} type="file" multiple accept={accept} className="sr-only" onChange={(e) => take(e.target.files)} />
      {warn && <p role="alert" className="mt-2 text-[13px] text-bad">{warn}</p>}
      {files.length > 0 && (
        <ul className="mt-2 space-y-2">
          {files.map((f, i) => (
            <li key={`${f.name}${f.size}`} className="flex items-center gap-2 rounded-lg border border-line-soft bg-surface p-2 text-sm">
              <Thumb file={f} />
              <span className="min-w-0 flex-1"><span className="block truncate">{f.name}</span><span className="text-xs text-muted">{bytes(f.size)}</span></span>
              <button type="button" aria-label={`Remove ${f.name}`} onClick={() => onChange(files.filter((_, n) => n !== i))} className="rounded p-1.5 text-muted hover:bg-line-soft"><X className="size-4" /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
