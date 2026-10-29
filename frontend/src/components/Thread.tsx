import { Images, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ThreadItem } from '../types'
import { dateTime } from '../utils/format'
import { ErrorNote, cx } from './ui'

/**
 * The conversation on one post, like a chat: the designs the team adds appear in it as they arrive,
 * and either side can write. Your own messages sit on the right.
 */
export default function Thread({ items, onSend, theirs, placeholder = 'Write a message…' }: {
  items: ThreadItem[]; onSend: (text: string) => Promise<void>; theirs: string; placeholder?: string
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)
  const last = items.length ? items[items.length - 1].id : 0

  useEffect(() => { end.current?.parentElement?.scrollTo({ top: end.current.offsetTop, behavior: 'smooth' }) }, [last])

  const send = async () => {
    const t = text.trim()
    if (!t || busy) return
    setBusy(true); setErr(null)
    try { await onSend(t); setText('') } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="max-h-[22rem] min-h-24 space-y-3 overflow-y-auto rounded-xl bg-canvas p-3 sm:p-4" aria-live="polite">
        {items.length === 0 && <p className="py-6 text-center text-sm text-muted">No messages yet. Say hello to {theirs}.</p>}
        {items.map((m) => m.type === 'version' ? (
          <div key={m.id} className="flex justify-center">
            <div className="max-w-[92%] rounded-xl border border-line-soft bg-surface px-3 py-2 text-center text-[13px] text-ink-2">
              <span className="inline-flex items-center gap-1.5 font-medium text-ink"><Images className="size-3.5" aria-hidden /> Version {m.number} added</span>
              {m.note && <span className="mt-0.5 block whitespace-pre-line text-muted">“{m.note}”</span>}
              <span className="mt-0.5 block text-[11px] text-faint">{dateTime(m.at)}</span>
            </div>
          </div>
        ) : (
          <div key={m.id} className={cx('flex', m.mine ? 'justify-end' : 'justify-start')}>
            <div className={cx('max-w-[86%] rounded-2xl px-3.5 py-2 text-sm', m.mine ? 'rounded-br-md bg-ink text-white' : 'rounded-bl-md border border-line-soft bg-surface text-ink')}>
              {!m.mine && <div className="mb-0.5 text-xs font-medium text-muted">{m.name}</div>}
              {m.changes && <div className={cx('mb-0.5 text-[11px] font-semibold tracking-wide uppercase', m.mine ? 'text-white/70' : 'text-bad')}>Asked for changes</div>}
              <p className="break-words whitespace-pre-line">{m.body}</p>
              <div className={cx('mt-1 text-right text-[11px]', m.mine ? 'text-white/60' : 'text-faint')}>{dateTime(m.at)}</div>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send() }} className="mt-2 flex items-end gap-2">
        <textarea data-noautofocus rows={1} value={text} maxLength={2000} placeholder={placeholder} aria-label="Message"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // On a computer Enter sends and Shift+Enter starts a new line. On a phone Enter is a new line; the arrow sends.
            const phone = window.matchMedia('(pointer: coarse)').matches
            if (e.key === 'Enter' && !e.nativeEvent.isComposing && (e.metaKey || e.ctrlKey || (!e.shiftKey && !phone))) { e.preventDefault(); send() }
          }}
          className="max-h-32 min-h-11 flex-1 resize-none rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[16px] outline-none focus:border-ink sm:text-sm" />
        <button type="submit" disabled={!text.trim() || busy} aria-label="Send message"
          className="flex size-11 shrink-0 items-center justify-center rounded-full bg-ink text-white transition-opacity disabled:opacity-40"><Send className="size-4" /></button>
      </form>
      <ErrorNote error={err} />
    </div>
  )
}
