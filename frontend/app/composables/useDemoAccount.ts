/**
 * Demo accounts, kept in this browser only (localStorage). Nothing leaves the device and there is
 * no password: this exists so people can try the tool as "their" hospital.
 */
export interface DemoAccount { name: string; email: string; hospital: string; role: string }

const KEY = 'bdn-demo-accounts'
const CURRENT = 'bdn-demo-current'

function read<T>(key: string, fallback: T): T {
  try { const r = localStorage.getItem(key); return r ? JSON.parse(r) as T : fallback } catch { return fallback }
}

export function useDemoAccount() {
  const account = useState<DemoAccount | null>('demo-account', () => null)
  const loaded = useState('demo-account-loaded', () => false)
  if (import.meta.client && !loaded.value) {
    const all = read<Record<string, DemoAccount>>(KEY, {})
    const cur = read<string>(CURRENT, '')
    account.value = (cur && all[cur]) || null
    loaded.value = true
  }
  const norm = (e: string) => e.trim().toLowerCase()
  const find = (email: string) => read<Record<string, DemoAccount>>(KEY, {})[norm(email)] ?? null
  function persist(a: DemoAccount) {
    try {
      const all = read<Record<string, DemoAccount>>(KEY, {})
      all[a.email] = a
      localStorage.setItem(KEY, JSON.stringify(all))
      localStorage.setItem(CURRENT, JSON.stringify(a.email))
    } catch { /* private mode: the session still works until reload */ }
    account.value = a
  }
  function signUp(a: DemoAccount) { persist({ ...a, email: norm(a.email), name: a.name.trim(), hospital: a.hospital.trim() }) }
  function signIn(email: string) { const a = find(email); if (a) persist(a); return a }
  function signOut() {
    try { localStorage.removeItem(CURRENT) } catch { /* ignore */ }
    account.value = null
  }
  return { account, find, signUp, signIn, signOut }
}
