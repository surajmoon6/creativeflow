import { buttonCls } from './ui'

/**
 * A plain upi:// link is handed to whichever app claims it, which on an iPhone is often WhatsApp. Each payment app
 * also has its own link scheme taking the same parameters, so the client picks the app they actually use.
 */
const APPS = [
  { name: 'Google Pay', prefix: 'gpay://upi/pay?' },
  { name: 'PhonePe', prefix: 'phonepe://pay?' },
  { name: 'Paytm', prefix: 'paytmmp://pay?' },
]

export default function UpiApps({ uri, className = '' }: { uri: string; className?: string }) {
  const query = uri.slice(uri.indexOf('?') + 1)
  return (
    <div className={`sm:hidden ${className}`}>
      <div className="grid grid-cols-3 gap-2">
        {APPS.map((a) => (
          <a key={a.name} href={a.prefix + query} className={buttonCls('brand', 'lg', 'px-2 text-[13px]')}>{a.name}</a>
        ))}
      </div>
      <p className="mt-2 text-center text-[13px] text-muted">
        Another app? <a href={uri} className="font-medium text-ink underline underline-offset-2">Choose any UPI app</a>
      </p>
      <p className="mt-1 text-center text-xs text-muted">If nothing opens, copy the UPI ID below and pay from your app.</p>
    </div>
  )
}
