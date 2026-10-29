import { MessageCircle } from 'lucide-react'
import { useRef, useState } from 'react'
import { ApiError } from '../services/api'
import FileDrop from './FileDrop'
import { Button, ErrorNote, Field, Input, buttonCls } from './ui'

/** wa.me wants digits only with the country code; a bare 10-digit Indian number gets 91 in front. */
export function waLink(number: string, text: string) {
  let n = number.replace(/\D/g, '')
  if (n.length === 10) n = `91${n}`
  return `https://wa.me/${n}?text=${encodeURIComponent(text)}`
}

/**
 * How a client shows they paid: a screenshot of the payment, the UPI transaction ID, or both.
 * They can also send the screenshot to the studio on WhatsApp instead; the studio then marks the payment received.
 */
export default function PaymentProof({ onSubmit, whatsapp, waText }: {
  onSubmit: (fd: FormData) => Promise<void>
  whatsapp?: string
  waText: string
}) {
  const [ref, setRef] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const f = file.current?.files?.[0]
    if (!f && !ref.trim()) { setErr('Upload a screenshot of the payment, or enter the UPI transaction ID (UTR).'); return }
    if (f && f.size > 10 * 1024 * 1024) { setErr('The screenshot must be under 10 MB.'); return }
    setBusy(true); setErr(null)
    const fd = new FormData()
    fd.set('reference', ref)
    if (f) fd.set('proof', f)
    try {
      await onSubmit(fd)
    } catch (e2) {
      setErr((e2 as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-4">
      <FileDrop inputRef={file} accept="image/png,image/jpeg,image/webp,application/pdf,.png,.jpg,.jpeg,.webp,.pdf"
        title="Upload your payment screenshot" hint="Tap to choose a photo or PDF, or drop it here" onPick={() => setErr(null)} />

      <div className="flex items-center gap-3 text-xs text-muted"><span className="h-px flex-1 bg-line-soft" />or<span className="h-px flex-1 bg-line-soft" /></div>

      <Field label="UPI transaction ID (UTR)" hint="Find it in your UPI app under the payment's details, usually 12 digits.">
        <Input value={ref} onChange={(e) => { setRef(e.target.value); setErr(null) }} autoComplete="off" placeholder="e.g. 426815093317" maxLength={40} />
      </Field>

      <ErrorNote error={err} />
      <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}>Submit payment details</Button>

      {whatsapp && (
        <div className="border-t border-line-soft pt-4 text-center">
          <p className="text-[13px] text-muted">Easier on WhatsApp? Send the screenshot to us there.</p>
          <a href={waLink(whatsapp, waText)} target="_blank" rel="noreferrer" className={buttonCls('secondary', 'lg', 'mt-2 w-full')}>
            <MessageCircle className="size-4" /> Send screenshot on WhatsApp
          </a>
          <p className="mt-2 text-xs text-muted">We'll confirm your payment once we see it.</p>
        </div>
      )}
    </form>
  )
}
