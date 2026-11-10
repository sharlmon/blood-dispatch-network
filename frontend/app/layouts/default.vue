<script setup lang="ts">
const { public: { apiBase, authEnabled, demoAuth } } = useRuntimeConfig()
const { account, signOut } = useDemoAccount()
const { toast } = useToast()
const leave = () => { signOut(); navigateTo('/'); toast({ title: 'Signed out', body: 'See you next time.' }) }
// No API configured (static demo): run on built-in demo data, never "Offline".
const demo = !apiBase
const health = useEngineStatus()
onMounted(() => { health.watchHealth() })

// Signed in: ask the server who it thinks we are (it verifies the Clerk session itself).
const verified = ref<'unknown' | 'ok' | 'no'>('unknown')
onMounted(() => {
  if (!authEnabled || demo) return
  const { isSignedIn, orgId } = useAuth()
  const { api } = useApi()
  watch([isSignedIn, orgId], async ([signed]) => {
    if (!signed) { verified.value = 'unknown'; return }
    try {
      const me = await api<{ org_id: string | null }>('/api/me')
      verified.value = me.org_id ? 'ok' : 'unknown'
    } catch { verified.value = 'no' }
  }, { immediate: true })
})
// Only shown when something is wrong or still loading; "demo data" and "live" are noise.
const chip = computed(() => {
  if (demo) return null
  if (health.unreachable.value) return { tone: 'down', text: 'Offline' }
  if (health.down.value || health.engine.value?.state === 'error') return { tone: 'down', text: 'Engine down' }
  if (verified.value === 'no') return { tone: 'down', text: 'Not verified' }
  if (health.engine.value?.state === 'loading') return { tone: 'wait', text: 'Loading data' }
  return null
})
const d = useDispatch()
</script>

<template>
  <div class="shell">
    <header class="barwrap">
      <div class="bar">
        <NuxtLink to="/" class="brand" aria-label="Blood Dispatch home"><BrandLogo :size="34" /></NuxtLink>
        <nav class="nav" aria-label="Main">
          <NuxtLink to="/request" class="newreq"><AppIcon name="plus" :size="18" /> New request</NuxtLink>
          <NuxtLink v-if="d.request.value" :to="d.resultsLink.value" :class="{ here: $route.path === '/results' }"><AppIcon name="results" :size="18" /> Results</NuxtLink>
          <NuxtLink v-if="d.canTrack.value" :to="d.trackLink.value" :class="{ here: $route.path === '/track' }"><AppIcon name="clock" :size="18" /> Track</NuxtLink>
          <NuxtLink to="/prealerts" class="tool" aria-label="Pre-alerts" title="Pre-alerts: hospitals to review for a top-up"><AppIcon name="bell" :size="18" /> <span>Pre-alerts</span></NuxtLink>
          <NuxtLink to="/evidence" class="tool" aria-label="Evidence" title="Evidence: how well the estimates held up"><AppIcon name="evidence" :size="18" /> <span>Evidence</span></NuxtLink>
        </nav>
        <span class="grow" />
        <span v-if="chip" class="status" :class="chip.tone" role="status"><i />{{ chip.text }}</span>
        <div class="who">
          <template v-if="authEnabled">
            <Show when="signed-in">
              <OrganizationSwitcher :hide-personal="true" after-select-organization-url="/request" />
              <UserButton />
            </Show>
            <Show when="signed-out">
              <NuxtLink to="/sign-in" class="signin">Sign in</NuxtLink>
              <NuxtLink to="/request" class="findbtn">Find blood</NuxtLink>
            </Show>
          </template>
          <template v-else-if="demoAuth">
            <template v-if="account">
              <span class="site">{{ account.hospital }}</span>
              <button type="button" class="signin" @click="leave">Sign out</button>
            </template>
            <template v-else>
              <NuxtLink to="/sign-in" class="signin">Sign in</NuxtLink>
              <NuxtLink to="/sign-up" class="findbtn">Create account</NuxtLink>
            </template>
          </template>
          <template v-else>
            <span class="site">Hillside Hospital · demo</span>
            <NuxtLink to="/request" class="findbtn">Find blood</NuxtLink>
          </template>
        </div>
        <MobileMenu />
      </div>
    </header>
    <div v-if="health.banner.value" class="fallback" role="alert">
      <AppIcon name="call" :size="18" /> <span>{{ health.banner.value }}</span>
    </div>
    <main class="main"><slot /></main>
    <BottomNav />
  </div>
</template>

<style scoped>
.shell { position: relative; min-height: 100dvh; display: flex; flex-direction: column; }
.shell > .main, .shell > .fallback { position: relative; z-index: 1; }
.barwrap { position: sticky; top: 0; z-index: 30; padding: 12px 14px 0; }
.bar { height: 58px; display: flex; align-items: center; gap: 14px; padding: 0 10px 0 16px; border-radius: 99px; background: rgba(255, 255, 255, 0.93); border: 1px solid #d8e4e2; box-shadow: 0 12px 30px rgba(6, 74, 68, 0.12); backdrop-filter: blur(10px); }
.brand { display: flex; align-items: center; text-decoration: none; }
.nav { display: none; gap: 4px; margin-left: 14px; }
.nav a { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 18px; border-radius: 99px; border: 1.5px solid transparent; text-decoration: none; font-weight: 800; font-size: 14px; color: #44545f; white-space: nowrap; transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease; }
.nav a:hover { background: var(--primary-50); color: var(--primary-700); transform: translateY(-1px); }
.nav a:focus-visible { outline: none; box-shadow: 0 0 0 4px rgba(10, 107, 98, 0.2); }
.nav a svg { color: var(--primary-500); transition: transform 0.3s cubic-bezier(0.2, 1.2, 0.3, 1); }
.nav a:hover svg { transform: scale(1.15) rotate(-6deg); }
.nav a.newreq { border-color: #b9d9d4; background: #fff; color: var(--primary-700); }
.nav a.newreq:hover { border-color: var(--primary-500); box-shadow: 0 8px 18px rgba(10, 107, 98, 0.16); }
.nav a.router-link-exact-active, .nav a.here, .nav a.tool.router-link-active { background: linear-gradient(180deg, #0e8277, #085a53); border-color: transparent; color: #fff; box-shadow: 0 8px 18px rgba(10, 107, 98, 0.3); }
.nav a.router-link-exact-active svg, .nav a.here svg, .nav a.tool.router-link-active svg { color: #fff; }
.grow { flex: 1; }
.status { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 800; padding: 7px 13px; border-radius: 99px; white-space: nowrap; }
.status i { width: 8px; height: 8px; border-radius: 99px; background: currentColor; }
.status.down { color: var(--amber-700); background: var(--amber-50); }
.status.wait { color: var(--primary-700); background: var(--primary-50); }
.who { display: flex; align-items: center; gap: 10px; }
.site, .findbtn { display: none; }
.site { display: none; font-size: 13px; font-weight: 700; color: #44545f; }
.signin { white-space: nowrap; padding: 9px 18px; border-radius: 99px; border: 1.5px solid var(--primary-500); color: var(--primary-700); font-weight: 800; font-size: 14px; text-decoration: none; background: #fff; }
.findbtn { display: none; padding: 10px 20px; border-radius: 99px; background: var(--primary-500); color: #fff; font-weight: 800; font-size: 14px; text-decoration: none; box-shadow: 0 8px 18px rgba(10, 107, 98, 0.3); }
.fallback { display: flex; align-items: center; gap: 8px; margin: 10px 14px 0; padding: 10px 16px; border-radius: 22px; background: var(--amber-50); color: var(--amber-900); font-size: 13px; font-weight: 700; line-height: 1.4; border: 1.5px solid var(--amber-500); }
.fallback svg { flex-shrink: 0; }
.main { flex: 1; min-height: 0; display: flex; flex-direction: column; padding-bottom: var(--dock-h); }
@media (max-width: 520px) { .status { display: none; } .signin { padding: 8px 14px; min-height: 40px; display: inline-flex; align-items: center; } .bar { gap: 8px; } }
@media (min-width: 900px) {
  .barwrap { padding: 16px 24px 0; }
  .bar { height: 62px; padding: 0 12px 0 20px; }
  .nav { display: flex; }
  .site { display: block; }
  .findbtn { display: inline-block; }
  .main { padding-bottom: 0; }
}
/* Tight desktop widths: the secondary links (Pre-alerts, Evidence) keep their icon only. */
@media (min-width: 900px) and (max-width: 1279px) {
  .nav { margin-left: 4px; }
  .nav a { padding: 0 14px; }
  .nav a.tool { padding: 0 12px; }
  .nav a.tool span { display: none; }
  .site { display: none; }
}
</style>
