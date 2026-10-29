let csrf = ''

export function setCsrf(token: string) {
  csrf = token
}

export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET' && csrf) headers['X-CSRF-Token'] = csrf
  const res = await fetch(url, { method, headers, body: payload, credentials: 'same-origin' })
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : null
  if (!res.ok) {
    if (res.status === 401 && data?.code === 'unauthenticated' && !url.startsWith('/api/auth')) {
      window.dispatchEvent(new Event('cf:logout'))
    }
    throw new ApiError(data?.error || 'Something went wrong. Please try again.', res.status, data?.code)
  }
  return data as T
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: unknown) => request<T>('PUT', url, body),
  del: <T>(url: string) => request<T>('DELETE', url),
}
