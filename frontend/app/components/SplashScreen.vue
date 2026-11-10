<script setup lang="ts">
// Shown once per visit: the drops gather into the logo, then the screen lifts away.
const show = ref(false)
const leaving = ref(false)
onMounted(() => {
  let seen = false
  try { seen = sessionStorage.getItem('bdn-splash') === '1' } catch { /* private mode */ }
  if (seen || matchMedia('(prefers-reduced-motion: reduce)').matches) return
  try { sessionStorage.setItem('bdn-splash', '1') } catch { /* ignore */ }
  show.value = true
  document.documentElement.style.overflow = 'hidden'
  setTimeout(() => { leaving.value = true }, 2300)
  setTimeout(() => { show.value = false; document.documentElement.style.overflow = '' }, 3000)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="splash" :class="{ leaving }" role="status" aria-label="Loading Blood Dispatch Network">
      <i class="ring r1" /><i class="ring r2" /><i class="ring r3" />
      <BrandMark :size="128" reverse intro class="mk" />
      <p class="w"><strong>Blood Dispatch</strong><small>Network</small></p>
      <span class="bar" aria-hidden="true"><i /></span>
    </div>
  </Teleport>
</template>

<style scoped>
.splash { position: fixed; inset: 0; z-index: 300; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 22px; color: #fff; background: radial-gradient(800px 500px at 50% 40%, #1a9a8d 0%, #0a6b62 50%, #042f2b 100%); transition: transform 0.7s cubic-bezier(0.7, 0, 0.2, 1), opacity 0.6s ease; overflow: hidden; }
.splash.leaving { transform: translateY(-100%); opacity: 0.9; }
.mk { position: relative; z-index: 1; filter: drop-shadow(0 12px 26px rgba(3, 30, 28, 0.5)); }
.ring { position: absolute; left: 50%; top: calc(50% - 44px); width: 128px; height: 128px; margin: -64px 0 0 -64px; border-radius: 50%; border: 2px solid rgba(255, 255, 255, 0.5); opacity: 0; animation: ping 2.2s ease-out 1.1s infinite; }
.r2 { animation-delay: 1.35s; }
.r3 { animation-delay: 1.6s; }
@keyframes ping { 0% { opacity: 0.9; transform: scale(0.7); } 100% { opacity: 0; transform: scale(3.2); } }
.w { margin: 0; display: flex; flex-direction: column; align-items: center; line-height: 1; opacity: 0; animation: up 0.7s ease 1.2s forwards; }
.w strong { font-size: clamp(22px, 5vw, 38px); font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; }
.w small { margin-top: 9px; font-size: 12px; font-weight: 700; letter-spacing: 0.5em; padding-left: 0.5em; text-transform: uppercase; color: #bfe3de; }
@keyframes up { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
.bar { width: 140px; height: 4px; border-radius: 99px; background: rgba(255, 255, 255, 0.2); overflow: hidden; opacity: 0; animation: up 0.5s ease 1.4s forwards; }
.bar i { display: block; height: 100%; width: 100%; background: #fff; transform-origin: left; transform: scaleX(0); animation: fill 1s ease-in-out 1.4s forwards; }
@keyframes fill { to { transform: scaleX(1); } }
</style>
