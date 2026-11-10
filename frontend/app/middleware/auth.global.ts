// Public: landing, sign in/up, and demo links (?demo=1). Everything else needs a signed-in user
// who belongs to a hospital (a Clerk organization).
const PUBLIC = ['/', '/sign-in', '/sign-up']

export default defineNuxtRouteMiddleware((to) => {
  if (!useRuntimeConfig().public.authEnabled) return // static demo build: no login
  const isPublic = PUBLIC.some(p => to.path === p || to.path.startsWith(p + '/')) || to.query.demo === '1'
  if (isPublic) return

  const { isSignedIn, orgId } = useAuth()
  if (!isSignedIn.value) return navigateTo('/sign-in')
  if (!orgId.value && to.path !== '/onboarding') return navigateTo('/onboarding')
})
