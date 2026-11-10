<script setup lang="ts">
const { public: { apiBase } } = useRuntimeConfig()
const { data: health, error } = useFetch<{ status: string }>(`${apiBase}/api/health`, { lazy: true, server: false })
const online = computed(() => health.value?.status === 'ok' && !error.value)
const { request } = useDispatch()
</script>

<template>
  <div class="shell">
    <header class="bar">
      <NuxtLink to="/" class="brand" aria-label="Blood Dispatch home">
        <span class="logo"><AppIcon name="drop" :size="20" /></span>
        <span>Blood Dispatch</span>
      </NuxtLink>
      <nav class="nav" aria-label="Main">
        <NuxtLink to="/">New request</NuxtLink>
        <NuxtLink v-if="request" to="/results">Results</NuxtLink>
      </nav>
      <span class="site">Hillside Hospital · Lab</span>
      <span class="status" :class="online ? 'ok' : 'down'" role="status">
        <i /> {{ online ? 'Live' : 'Offline' }}
      </span>
    </header>
    <div v-if="!online" class="fallback" role="alert">
      <AppIcon name="call" :size="18" /> Tool not reachable. Use the phone process: call the blood centre directly.
    </div>
    <main class="main"><slot /></main>
  </div>
</template>

<style scoped>
.shell { min-height: 100dvh; display: flex; flex-direction: column; }
.bar { height: var(--header-h); display: flex; align-items: center; gap: 16px; padding: 0 16px; background: var(--white); border-bottom: 1px solid var(--line); flex-shrink: 0; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 16px; text-decoration: none; color: var(--ink); }
.logo { width: 32px; height: 32px; border-radius: 10px; background: var(--blood-500); color: #fff; display: grid; place-items: center; }
.nav { display: none; gap: 4px; flex: 1; margin-left: 12px; }
.nav a { padding: 8px 14px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 14px; color: var(--slate); }
.nav a.router-link-exact-active { background: var(--blood-50); color: var(--blood-700); }
.site { display: none; font-size: 13px; font-weight: 600; color: var(--slate); }
.status { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 800; padding: 6px 12px; border-radius: 99px; }
.status i { width: 8px; height: 8px; border-radius: 99px; background: currentColor; }
.status.ok { color: var(--teal-600); background: var(--teal-50); }
.status.down { color: var(--amber-700); background: var(--amber-50); }
.fallback { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: var(--amber-50); color: var(--amber-900); font-size: 13px; font-weight: 700; border-bottom: 1px solid var(--amber-500); }
.main { flex: 1; min-height: 0; display: flex; flex-direction: column; }
@media (min-width: 900px) {
  .nav { display: flex; }
  .site { display: block; }
  .status { margin-left: 0; }
}
</style>
