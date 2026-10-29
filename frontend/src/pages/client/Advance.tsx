import { CircleCheck, Clock } from 'lucide-react'
import { useEffect, useState } from 'react'
import PaymentProof from '../../components/PaymentProof'
import UpiApps from '../../components/UpiApps'
import { CopyButton } from '../../components/ui'
import { api } from '../../services/api'
import type { ClientView } from '../../types'
import { dateTime, money } from '../../utils/format'
import { usePortal } from './Portal'

/** Paying the advance: scan or tap to pay by UPI, then share a screenshot or the transaction ID for the studio to confirm. */
export default function AdvancePage() {
  const { view, token, refresh } = usePortal()
  const a = view.advance
  const waiting = a?.status === 'submitted'
  useEffect(() => {
    if (!waiting) return
    const t = window.setInterval(refresh, 15000)
    return () => window.clearInterval(t)
  }, [waiting, refresh])

  const [uri, setUri] = useState<string | null>(null)
  const needsPayment = a?.status === 'requested'
  useEffect(() => {
    if (needsPayment && a?.has_qr) api.get<{ uri: string | null }>(`/api/r/${token}/upi-uri?for=advance`).then((r) => setUri(r.uri)).catch(() => {})
  }, [needsPayment, a?.has_qr, token])

  if (!a) return <p className="text-ink-2">No advance is needed for this project.</p>

  return (
    <div className="mx-auto max-w-xl">
      {a.status === 'paid' ? (
        <Box>
          <h2 className="flex items-center gap-2 text-lg font-semibold"><CircleCheck className="size-5 text-ok" /> Advance received</h2>
          <p className="mt-1 text-ink-2">Thank you! Your advance has been received and your project is moving ahead. It is already counted, so the final invoice will only ask for the balance.</p>
        </Box>
      ) : a.status === 'submitted' && a.pending ? (
        <Box>
          <h2 className="flex items-center gap-2 text-lg font-semibold"><Clock className="size-5 text-warn" /> Payment details received</h2>
          <p className="mt-1 text-ink-2">Thank you. The studio will confirm your advance shortly and carry on with your work.</p>
          <dl className="mt-4 space-y-1 text-[13px]">
            <Row k="Reference" v={a.pending.reference || 'Screenshot uploaded'} />
            <Row k="Submitted" v={dateTime(a.pending.submitted_at)} />
          </dl>
        </Box>
      ) : (
        <Box>
          <h2 className="text-lg font-semibold">Pay the advance</h2>
          <p className="mt-1 text-ink-2">This keeps your project moving. It is part of your total and is taken off the final invoice.</p>
          <div className="mt-4 flex items-baseline justify-between border-y border-line-soft py-3">
            <span className="text-sm text-muted">Advance</span>
            <span className="text-2xl font-semibold tabular-nums">{money(a.due)}</span>
          </div>

          {a.last_rejected && (
            <p className="mt-4 rounded-md bg-bad-soft px-3 py-2 text-[13px] text-bad">
              The studio couldn't match your last payment details{a.last_rejected.reference ? ` (${a.last_rejected.reference})` : ''}.{a.last_rejected.admin_note ? ` ${a.last_rejected.admin_note}` : ''} Please check and submit again.
            </p>
          )}

          <ol className="mt-5 space-y-6">
            <li>
              <Step n={1}>Pay with any UPI app</Step>
              {a.has_qr ? (
                <>
                  {uri && <UpiApps uri={uri} className="mt-3" />}
                  <div>
                    <div className="mt-3 flex justify-center rounded-lg border border-line-soft p-3">
                      <img src={`/api/r/${token}/advance-qr.png`} alt="UPI QR code for the advance" className="size-48" />
                    </div>
                    <p className="mt-2 text-center text-xs text-muted">Scan with Google Pay, PhonePe, Paytm or your bank app. The amount is filled in for you. On this phone? Take a screenshot and pick it from your gallery inside the app's scanner.</p>
                  </div>
                </>
              ) : (
                <p className="mt-2 text-sm text-ink-2">The studio will share payment details with you.</p>
              )}
              {a.upi_id && (
                <div className="mt-3 flex items-center justify-between gap-2 rounded-md bg-canvas px-3 py-2">
                  <div className="min-w-0">
                    <div className="text-xs text-muted">UPI ID, {a.payee}</div>
                    <div className="truncate text-sm font-medium">{a.upi_id}</div>
                  </div>
                  <CopyButton text={a.upi_id} copied="UPI ID copied" />
                </div>
              )}
            </li>
            <li>
              <Step n={2}>Show us your payment</Step>
              <PaymentProof whatsapp={view.brand.whatsapp}
                waText={`Hi, I've paid the advance of ${money(a.due)} for ${view.name} (#${view.code}). Sharing the payment screenshot here.`}
                onSubmit={async (fd) => { await api.post<ClientView>(`/api/r/${token}/advance`, fd); await refresh() }} />
            </li>
          </ol>
        </Box>
      )}
    </div>
  )
}

const Row = ({ k, v }: { k: string; v: string }) => (
  <div className="flex justify-between gap-4"><dt className="text-muted">{k}</dt><dd className="font-medium tabular-nums">{v}</dd></div>
)
const Box = ({ children }: { children: React.ReactNode }) => <div className="rounded-xl border border-line bg-surface p-5 sm:p-6">{children}</div>
const Step = ({ n, children }: { n: number; children: React.ReactNode }) => (
  <div className="flex items-center gap-2.5 text-sm font-medium">
    <span className="flex size-5 items-center justify-center rounded-full bg-ink text-[11px] text-white tabular-nums">{n}</span>
    {children}
  </div>
)
