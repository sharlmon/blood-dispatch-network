/** URL for a file in /public that also works under a base path (GitHub Pages). */
export function useImg() {
  const base = useRuntimeConfig().app.baseURL || '/'
  return (name: string) => `${base}${base.endsWith('/') ? '' : '/'}images/${name}`
}
