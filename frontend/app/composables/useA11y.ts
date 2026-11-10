export interface A11yPrefs { text: 0 | 1 | 2; contrast: boolean; readable: boolean; links: boolean; calm: boolean }
const DEFAULTS: A11yPrefs = { text: 0, contrast: false, readable: false, links: false, calm: false }
const KEY = 'bdn-a11y'

/** Accessibility preferences, saved on this device and applied as classes on <html>. */
export function useA11y() {
  const prefs = useState<A11yPrefs>('a11y', () => ({ ...DEFAULTS }))

  function apply() {
    if (!import.meta.client) return
    const c = document.documentElement.classList
    const p = prefs.value
    c.toggle('a11y-text-1', p.text === 1)
    c.toggle('a11y-text-2', p.text === 2)
    c.toggle('a11y-contrast', p.contrast)
    c.toggle('a11y-readable', p.readable)
    c.toggle('a11y-links', p.links)
    c.toggle('a11y-calm', p.calm)
  }
  function load() {
    try {
      const raw = localStorage.getItem(KEY)
      if (raw) prefs.value = { ...DEFAULTS, ...JSON.parse(raw) }
    } catch { /* storage blocked: defaults */ }
    apply()
  }
  function set<K extends keyof A11yPrefs>(k: K, v: A11yPrefs[K]) {
    prefs.value = { ...prefs.value, [k]: v }
    apply()
    try { localStorage.setItem(KEY, JSON.stringify(prefs.value)) } catch { /* ignore */ }
  }
  function reset() {
    prefs.value = { ...DEFAULTS }
    apply()
    try { localStorage.removeItem(KEY) } catch { /* ignore */ }
  }
  const changed = computed(() => JSON.stringify(prefs.value) !== JSON.stringify(DEFAULTS))
  return { prefs, load, set, reset, changed }
}
