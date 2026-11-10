/** Calls the Flask API, attaching the signed-in user's Clerk session token (verified server-side). */
export function useApi() {
  const { public: { apiBase, authEnabled } } = useRuntimeConfig()
  // useAuth only exists when the Clerk module is on (login enabled in this build).
  const getToken = authEnabled ? useAuth().getToken : null

  async function api<T>(path: string, opts: Record<string, unknown> = {}): Promise<T> {
    const headers: Record<string, string> = { ...((opts.headers as Record<string, string>) ?? {}) }
    const token = getToken ? await getToken.value() : null
    if (token) headers.Authorization = `Bearer ${token}`
    return $fetch<T>(`${apiBase}${path}`, { ...opts, headers })
  }

  return { api }
}
