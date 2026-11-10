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
    <NuxtLink v-for="i in items" :key="i.label" :to="i.to" :aria-label="i.label" class="it">
      <AppIcon :name="i.icon" :size="22" />
    </NuxtLink>
  </nav>
</template>

<style scoped>
.dock {
  position: fixed; left: 16px; right: 16px; bottom: calc(14px + env(safe-area-inset-bottom)); z-index: 20;
  display: flex; justify-content: space-between; padding: 8px 14px; border-radius: 99px; max-width: 420px; margin: 0 auto;
  background: linear-gradient(180deg, #c3282c, var(--blood-600)); box-shadow: 0 14px 30px rgba(126, 16, 21, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}
.it { width: 52px; height: 48px; border-radius: 99px; display: grid; place-items: center; color: #fff; transition: background 0.2s ease, transform 0.2s ease; }
.it:active { transform: scale(0.92); }
.it.router-link-exact-active { background: #fff; color: var(--blood-600); }
@media (min-width: 900px) { .dock { display: none; } }
</style>
