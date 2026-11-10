import type { ApiErrorBody } from '~/utils/engine'

/** What went wrong with an API call, in a shape the screens can act on. */
export interface ApiFailure {
  /** HTTP status, or null when the API could not be reached */
  status: number | null
  /** the API's error code (invalid_request, engine_unavailable, ...), or network / aborted / http_<status> */
  code: string
  message: string
  network: boolean
}

const UNREACHABLE = 'Tool not reachable. Use the phone process.'

/** Pull {status, code, message} out of a $fetch error. The API answers {"error": {"code", "message"}}. */
export function apiFailure(e: unknown): ApiFailure {
  const err = (e ?? {}) as { status?: number; statusCode?: number; data?: unknown; name?: string; cause?: { name?: string } }
  const status = err.status ?? err.statusCode ?? null
  const body = err.data as Partial<ApiErrorBody> | null | undefined
  if (body && typeof body === 'object' && body.error && typeof body.error.code === 'string') {
    return { status, code: body.error.code, message: body.error.message ?? '', network: false }
  }
  if (err.name === 'AbortError' || err.cause?.name === 'AbortError') return { status: null, code: 'aborted', message: '', network: false }
  if (!status) return { status: null, code: 'network', message: UNREACHABLE, network: true }
  return { status, code: `http_${status}`, message: `The tool answered with error ${status}. If it keeps happening, use the phone process.`, network: false }
}

/** Signed out, no hospital chosen, or sign-in not available on the server. */
export function isAuthFailure(f: ApiFailure): boolean {
  return f.status === 401 || f.status === 403 || f.code === 'auth_not_configured' || f.code === 'auth_unavailable'
}

function toastFor(f: ApiFailure): { title: string; body: string } {
  if (f.network) return { title: 'Tool not reachable', body: 'Use the phone process: call the blood centre directly.' }
  if (f.code === 'engine_unavailable') return { title: 'Ranking engine not available', body: `${f.message} Use the phone process.`.trim() }
  if (f.code === 'auth_not_configured' || f.code === 'auth_unavailable') return { title: 'Sign-in not available', body: f.message }
  if (f.status === 401) return { title: 'Sign in needed', body: f.message || 'Sign in to use live data.' }
  if (f.code === 'forbidden') return { title: 'Not allowed', body: f.message }
  if (f.status === 403) return { title: 'Choose your hospital', body: f.message || 'Choose your hospital before making requests.' }
  if (f.status === 400) return { title: 'Check the request', body: f.message }
  if (f.status === 404) return { title: 'Not found', body: f.message }
  if (f.status === 409) return { title: 'That step is not possible now', body: f.message }
  return { title: 'Something went wrong', body: f.message }
}

/** Calls the Flask API, attaching the signed-in user's Clerk session token (verified server-side). */
export function useApi() {
  const { public: { apiBase, authEnabled } } = useRuntimeConfig()
  // useAuth only exists when the Clerk module is on (login enabled in this build).
  const getToken = authEnabled ? useAuth().getToken : null
  const { toast } = useToast()
  // Shared with the layout, which shows the phone-process banner.
  const unreachable = useState<boolean>('api.unreachable', () => false)
  const engineDown = useState<string | null>('engine.down', () => null)

  async function api<T>(path: string, opts: Record<string, unknown> = {}): Promise<T> {
    const headers: Record<string, string> = { ...((opts.headers as Record<string, string>) ?? {}) }
    const token = getToken ? await getToken.value() : null
    if (token) headers.Authorization = `Bearer ${token}`
    // The API wants a retry key on every change (POST/PUT): one per call, so a repeat of the same
    // call (a double tap, a network retry) can never repeat a stock change.
    const method = String(opts.method ?? 'GET').toUpperCase()
    if (method !== 'GET' && !headers['Idempotency-Key']) headers['Idempotency-Key'] = crypto.randomUUID()
    const res = await $fetch<T>(`${apiBase}${path}`, { ...opts, headers })
    unreachable.value = false
    return res
  }

  /** Record a failed call: set the shared fallback flags and, unless quiet, tell the user. */
  function fail(e: unknown, opts: { quiet?: boolean } = {}): ApiFailure {
    const f = apiFailure(e)
    if (f.code === 'aborted') return f
    unreachable.value = f.network
    if (f.code === 'engine_unavailable') engineDown.value = f.message || 'it could not load its data'
    if (!opts.quiet) toast({ tone: 'warn', ...toastFor(f), ms: 6500 })
    return f
  }

  /** A call that needed the engine worked, so drop the "engine not available" banner. */
  function engineUp() {
    engineDown.value = null
  }

  return { api, fail, engineUp, live: !!apiBase }
}
