<script setup lang="ts">
// Primary navigation on phones: five top-level destinations, each with an icon AND a label,
// the current one highlighted. Results/Track are dimmed until there is a request, and say why.
const { request } = useDispatch()
const has = computed(() => !!request.value)
</script>

<template>
  <nav class="dock" aria-label="Main">
    <NuxtLink to="/" class="it" exact-active-class="here"><AppIcon name="home" :size="22" /><span>Home</span></NuxtLink>
    <NuxtLink to="/request" class="it" exact-active-class="here"><AppIcon name="edit" :size="22" /><span>Request</span></NuxtLink>
    <NuxtLink to="/request?sos=1" class="sos" aria-label="SOS: patient group unknown, request group O only"><i>SOS</i><span>Unknown</span></NuxtLink>
    <NuxtLink :to="has ? '/results' : '/request?need=results'" class="it" :class="{ off: !has }" exact-active-class="here" :aria-disabled="!has" :title="has ? '' : 'Make a request first'"><AppIcon name="pin" :size="22" /><span>Results</span></NuxtLink>
    <NuxtLink :to="has ? '/track' : '/request?need=track'" class="it" :class="{ off: !has }" exact-active-class="here" :aria-disabled="!has" :title="has ? '' : 'Make a request first'"><AppIcon name="clock" :size="22" /><span>Track</span></NuxtLink>
  </nav>
</template>

<style scoped>
.dock {
  position: fixed; left: 12px; right: 12px; bottom: calc(10px + env(safe-area-inset-bottom)); z-index: 20; max-width: 440px; margin: 0 auto;
  display: grid; grid-template-columns: repeat(5, 1fr); align-items: end; padding: 8px 6px 8px; border-radius: 28px;
  background: linear-gradient(180deg, #c3282c, var(--blood-600)); box-shadow: var(--sh-2), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}
.it { min-height: 56px; border-radius: 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; color: rgba(255, 255, 255, 0.92); text-decoration: none; transition: background 0.2s ease, transform 0.15s ease; }
.it span { font-size: 11.5px; font-weight: 800; letter-spacing: 0.01em; }
.it:active { transform: scale(0.94); }
.it.here { background: #fff; color: var(--blood-600); }
.it.off { opacity: 0.6; }
.sos { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 3px; text-decoration: none; color: rgba(255, 255, 255, 0.92); min-height: 56px; }
.sos i { width: 60px; height: 60px; margin-top: -30px; border-radius: 99px; display: grid; place-items: center; font-style: normal; font-weight: 800; font-size: 15px; letter-spacing: 0.04em; color: #fff; background: radial-gradient(circle at 35% 30%, #ff6b63, #d12b31 60%, #a8141b); border: 4px solid var(--paper); box-shadow: 0 12px 24px rgba(179, 23, 30, 0.5); animation: sosPulse 2.4s ease-out infinite; }
.sos span { font-size: 11.5px; font-weight: 800; }
@keyframes sosPulse { 0% { box-shadow: 0 12px 24px rgba(179, 23, 30, 0.5), 0 0 0 0 rgba(209, 43, 49, 0.45); } 100% { box-shadow: 0 12px 24px rgba(179, 23, 30, 0.5), 0 0 0 16px rgba(209, 43, 49, 0); } }
@media (min-width: 900px) { .dock { display: none; } }
</style>
