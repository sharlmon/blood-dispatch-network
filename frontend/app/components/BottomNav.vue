<script setup lang="ts">
const { request } = useDispatch()
const items = computed(() => [
  { to: '/', icon: 'home', label: 'Home' },
  { to: '/request', icon: 'edit', label: 'New request' },
  { to: request.value ? '/results' : '/request', icon: 'pin', label: 'Results' },
  { to: request.value ? '/track' : '/request', icon: 'clock', label: 'Track' }
])
</script>

<template>
  <nav class="dock" aria-label="Main">
    <NuxtLink v-for="i in items.slice(0, 2)" :key="i.label" :to="i.to" :aria-label="i.label" class="it"><AppIcon :name="i.icon" :size="22" /></NuxtLink>
    <NuxtLink to="/request?sos=1" class="sos" aria-label="SOS: patient group unknown, request group O only"><span>SOS</span></NuxtLink>
    <NuxtLink v-for="i in items.slice(2)" :key="i.label" :to="i.to" :aria-label="i.label" class="it"><AppIcon :name="i.icon" :size="22" /></NuxtLink>
  </nav>
</template>

<style scoped>
.dock {
  position: fixed; left: 16px; right: 16px; bottom: calc(14px + env(safe-area-inset-bottom)); z-index: 20;
  display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-radius: 99px; max-width: 420px; margin: 0 auto;
  background: linear-gradient(180deg, #c3282c, var(--blood-600)); box-shadow: 0 14px 30px rgba(126, 16, 21, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}
.it { width: 50px; height: 46px; border-radius: 99px; display: grid; place-items: center; color: #fff; transition: background 0.2s ease, transform 0.2s ease; }
.it:active { transform: scale(0.92); }
.it.router-link-exact-active { background: #fff; color: var(--blood-600); }
.sos { width: 62px; height: 62px; margin-top: -26px; border-radius: 99px; display: grid; place-items: center; text-decoration: none; background: radial-gradient(circle at 35% 30%, #ff6b63, #d12b31 60%, #a8141b); color: #fff; font-weight: 800; font-size: 15px; letter-spacing: 0.04em; border: 4px solid var(--paper); box-shadow: 0 12px 24px rgba(179, 23, 30, 0.5); animation: sosPulse 2.4s ease-out infinite; }
@keyframes sosPulse { 0% { box-shadow: 0 12px 24px rgba(179, 23, 30, 0.5), 0 0 0 0 rgba(209, 43, 49, 0.45); } 100% { box-shadow: 0 12px 24px rgba(179, 23, 30, 0.5), 0 0 0 16px rgba(209, 43, 49, 0); } }
@media (min-width: 900px) { .dock { display: none; } }
</style>
