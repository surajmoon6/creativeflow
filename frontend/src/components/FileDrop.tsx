import { FileText, ImageUp, X } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import { bytes } from '../utils/format'
import { cx } from './ui'

/**
 * A drop zone around a normal file input. Dropping, tapping to browse and pasting all end up in `inputRef`,
 * so a form reads the file the same way it always did: `inputRef.current?.files?.[0]`.
 */
export default function FileDrop({ inputRef, accept, title = 'Drop your file here', hint, onPick, className }: {
  inputRef: React.RefObject<HTMLInputElement | null>
  accept: string
  title?: string
  hint?: string
  onPick?: (f: File | null) => void
  className?: string
}) {
  const id = useId()
  const [file, setFile] = useState<File | null>(null)
  const [over, setOver] = useState(false)
  const [warn, setWarn] = useState<string | null>(null)
  const [thumb, setThumb] = useState<string | null>(null)

  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) { setThumb(null); return }
    const url = URL.createObjectURL(file)
    setThumb(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const allowed = accept.split(',').map((a) => a.trim().toLowerCase())
  const ok = (f: File) => {
    const ext = '.' + (f.name.split('.').pop() ?? '').toLowerCase()
    return allowed.some((a) => a === ext || a === f.type || (a.endsWith('/*') && f.type.startsWith(a.slice(0, -1))))
  }
  const take = (f: File | null) => {
    const input = inputRef.current
    if (f && !ok(f)) { setWarn(`That file type isn't supported. Use ${allowed.filter((a) => a.startsWith('.')).join(', ').toUpperCase().replaceAll('.', '') || 'an image or PDF'}.`); return }
    setWarn(null)
    if (input) {
      if (f) { const dt = new DataTransfer(); dt.items.add(f); input.files = dt.files } else input.value = ''
    }
    setFile(f)
    onPick?.(f)
  }

  return (
    <div className={className}>
      <input ref={inputRef} id={id} type="file" accept={accept} className="sr-only"
        onChange={(e) => take(e.target.files?.[0] ?? null)} />
      <label htmlFor={id}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) take(f) }}
        className={cx('flex cursor-pointer items-center gap-3 rounded-lg border border-dashed px-4 py-5 text-left transition-colors focus-within:ring-2',
          over ? 'border-ink bg-surface ring-2 ring-ink/10' : 'border-line bg-canvas hover:border-ink-2')}>
        {thumb ? (
          <img src={thumb} alt="" className="size-14 shrink-0 rounded-md border border-line-soft bg-surface object-cover" />
        ) : file ? (
          <FileText className="size-6 shrink-0 text-ink-2" />
        ) : (
          <ImageUp className="size-6 shrink-0 text-ink-2" />
        )}
        <span className="min-w-0 flex-1 text-sm">
          {file ? (
            <>
              <span className="block truncate font-medium">{file.name}</span>
              <span className="block text-[13px] text-muted">{bytes(file.size)}. Drop another file or tap to replace it.</span>
            </>
          ) : (
            <>
              <span className="block font-medium">{over ? 'Release to add the file' : title}</span>
              <span className="block text-[13px] text-muted">{hint ?? 'or click to browse'}</span>
            </>
          )}
        </span>
        {file && (
          <button type="button" aria-label="Remove file" className="rounded-md p-1.5 text-muted hover:bg-line-soft hover:text-ink"
            onClick={(e) => { e.preventDefault(); take(null) }}><X className="size-4" /></button>
        )}
      </label>
      {warn && <p role="alert" className="mt-1.5 text-[13px] text-bad">{warn}</p>}
    </div>
  )
}
