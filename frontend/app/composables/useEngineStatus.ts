import type { HealthResponse } from '~/utils/engine'

let timer: ReturnType<typeof setTimeout> | undefined

/**
 * API and ranking-engine health (GET /api/health, which never waits for the engine to load).
 * `banner` is the phone-process message the layout shows, or null when all is well. Client only.
 */
export function useEngineStatus() {
  const { public: { apiBase } } = useRuntimeConfig()
  const live = !!apiBase
  const health = useState<HealthResponse | null>('engine.health', () => null)
  const unreachable = useState<boolean>('api.unreachable', () => false)
  const down = useState<string | null>('engine.down', () => null)

  const engine = computed(() => health.value?.engine ?? null)
  const banner = computed<string | null>(() => {
    if (!live) return null
    if (unreachable.value) return 'Tool not reachable. Use the phone process: call the blood centre directly.'
    const why = down.value ?? (engine.value?.state === 'error' ? engine.value.message || 'its data could not be loaded' : null)
    return why ? `Ranking engine not available: ${why.trim().replace(/\.+$/, '')}. Use the phone process: call the blood centre directly.` : null
  })

  async function check() {
    if (!live || import.meta.server) return
    try {
      health.value = await $fetch<HealthResponse>(`${apiBase}/api/health`, { timeout: 8000 })
      unreachable.value = false
      if (health.value.engine?.state === 'ready') down.value = null
    } catch {
      unreachable.value = true
    }
  }

  /** Check now, then again while the engine loads (every 5 s) or while something is wrong (every 30 s). */
  async function watchHealth() {
    if (!live || import.meta.server) return
    clearTimeout(timer)
    await check()
    const state = engine.value?.state
    const wait = state === 'loading' ? 5000 : unreachable.value || state === 'error' || down.value ? 30_000 : 0
    if (wait) timer = setTimeout(watchHealth, wait)
  }

  return { live, health, engine, unreachable, down, banner, check, watchHealth }
}
