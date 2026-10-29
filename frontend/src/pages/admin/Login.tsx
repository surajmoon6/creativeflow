import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, ErrorNote, Field, Input } from '../../components/ui'
import { api, ApiError, setCsrf } from '../../services/api'

export default function Login() {
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: string } }
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [canSignUp, setCanSignUp] = useState(false)
  const [signUp, setSignUp] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.get<{ signup: boolean }>('/api/auth/options').then((o) => setCanSignUp(o.signup)).catch(() => {}) }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const r = await api.post<{ csrf: string; user: { role: string } }>(signUp ? '/api/auth/signup' : '/api/auth/login', signUp ? { name, email, password } : { email, password })
      setCsrf(r.csrf)
      if (r.user.role === 'client') nav('/c', { replace: true })
      else nav(loc.state?.from && loc.state.from !== '/login' ? loc.state.from : r.user.role === 'staff' ? '/projects' : '/', { replace: true })
    } catch (e2) {
      setErr((e2 as ApiError).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="flex flex-col justify-center px-6 py-12 sm:px-16">
        <div className="mx-auto w-full max-w-sm">
          <svg viewBox="0 0 32 32" className="size-8" aria-hidden><rect width="32" height="32" rx="8" fill="#15171C" /><path d="M9 9h4M9 9v4M23 9h-4M23 9v4M9 23h4M9 23v-4M23 23h-4M23 23v-4" stroke="#fff" strokeWidth="2" strokeLinecap="round" /></svg>
          <h1 className="mt-8 text-[26px] font-semibold tracking-[-0.02em]">{signUp ? 'Create a test account' : 'Sign in to CreativeFlow'}</h1>
          <p className="mt-1 text-ink-2">{signUp ? 'Try the whole tool with sample data. Use any name and a made-up email.' : "Review, approval and delivery for your studio's work."}</p>
          <form onSubmit={submit} className="mt-8 space-y-4">
            {signUp && <Field label="Your name"><Input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus maxLength={120} /></Field>}
            <Field label="Email"><Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus={!signUp} /></Field>
            <Field label="Password"><Input type="password" autoComplete={signUp ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={signUp ? 8 : undefined} /></Field>
            <ErrorNote error={err} />
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}>{signUp ? 'Create account and open the demo' : 'Sign in'}</Button>
          </form>
          {canSignUp && (
            <p className="mt-5 text-sm text-ink-2">
              {signUp ? 'Already have an account? ' : 'Just trying it out? '}
              <button type="button" className="font-medium text-ink underline underline-offset-2" onClick={() => { setSignUp(!signUp); setErr(null) }}>
                {signUp ? 'Sign in' : 'Create a test account'}
              </button>
            </p>
          )}
        </div>
      </div>
      <div className="hidden items-center justify-center bg-stage p-16 lg:flex" aria-hidden>
        <div className="crop-stage">
          <span className="crop tl" /><span className="crop tr" /><span className="crop bl" /><span className="crop br" />
          <div className="flex h-[420px] w-[336px] flex-col justify-between bg-[#122046] p-8 text-white shadow-[0_12px_32px_-12px_rgba(21,23,28,.35)]">
            <div className="text-[44px] leading-[1.02] font-semibold tracking-[-0.03em]">Brief.<br />Review.<br />Approve.<br />Deliver.</div>
            <div className="text-sm text-white/60">One link for your client, from first draft to final files.</div>
          </div>
        </div>
      </div>
    </div>
  )
}
