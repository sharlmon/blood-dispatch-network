// Public: landing, sign in/up, and demo links (?demo=1). Everything else needs a signed-in user
// who belongs to a hospital (a Clerk organization).
const PUBLIC = ['/', '/sign-in', '/sign-up']

export default defineNuxtRouteMiddleware(async (to) => {
  const { authEnabled, demoAuth } = useRuntimeConfig().public
  if (!authEnabled && !demoAuth) return // static demo build: no login
  const isPublic = PUBLIC.some(p => to.path === p || to.path.startsWith(p + '/')) || to.query.demo === '1'
  if (isPublic) return
  if (demoAuth) {
    // Local demo accounts: signed in means an account exists in this browser. No hospital step.
    const { account } = useDemoAccount()
    if (!account.value) return navigateTo('/sign-in')
    if (to.path === '/onboarding') return navigateTo('/request')
    return
  }

  const { isLoaded, isSignedIn, orgId } = useAuth()
  // Static (SPA) build: Clerk loads in the browser, so wait for it before deciding.
  if (import.meta.client && !isLoaded.value) {
    await new Promise<void>((resolve) => {
      const stop = watch(isLoaded, (v) => { if (v) { stop(); resolve() } }, { immediate: true })
    })
  }
  if (!isSignedIn.value) return navigateTo('/sign-in')
  if (!orgId.value && to.path !== '/onboarding') return navigateTo('/onboarding')
})
