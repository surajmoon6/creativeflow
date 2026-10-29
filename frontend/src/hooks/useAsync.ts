import { useCallback, useEffect, useRef, useState } from 'react'

interface Options {
  /** Re-fetch quietly every N ms while the tab is visible, and again when the tab regains focus. */
  poll?: number
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = [], opts: Options = {}) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)
  const reload = useCallback(async () => {
    try {
      const d = await run()
      setData(d)
      setError(null)
      return d
    } catch (e) {
      setError(e as Error)
    } finally {
      setLoading(false)
    }
  }, [run])
  useEffect(() => {
    setLoading(true)
    reload()
  }, [reload])

  // Background refresh: never shows a spinner or an error, and leaves state alone when nothing changed.
  const busy = useRef(false)
  const { poll } = opts
  useEffect(() => {
    if (!poll) return
    let alive = true
    const refresh = async () => {
      if (busy.current || document.visibilityState !== 'visible') return
      busy.current = true
      try {
        const d = await run()
        if (alive) setData((prev) => (JSON.stringify(prev) === JSON.stringify(d) ? prev : d))
      } catch {
        /* keep showing what we have; the next tick retries */
      } finally {
        busy.current = false
      }
    }
    const t = window.setInterval(refresh, poll)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      alive = false
      window.clearInterval(t)
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [poll, run])

  return { data, setData, error, loading, reload }
}
