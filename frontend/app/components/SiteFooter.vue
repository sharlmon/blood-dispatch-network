<script setup lang="ts">
// Closing section: four drops fly in and lock into the logo, rings pulse out, a ribbon of blood groups scrolls by.
const groups = ['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−']
const links = [
  { label: 'How it works', to: { path: '/', hash: '#how' } },
  { label: 'The data', to: { path: '/', hash: '#data' } },
  { label: 'Who uses it', to: { path: '/', hash: '#phone' } },
  { label: 'Built to be safe', to: { path: '/', hash: '#safe' } }
]
const D = 'M32 5 C40 16 50 27 50 39 A18 18 0 0 1 14 39 C14 27 24 16 32 5 Z'
const petals = [
  { r: 0, x: 0, y: -56, fill: '#cfeae6' },
  { r: 90, x: 56, y: 0, fill: '#fff' },
  { r: 180, x: 0, y: 56, fill: '#fff' },
  { r: 270, x: -56, y: 0, fill: '#fff' }
]
</script>

<template>
  <footer class="sf">
    <div class="ribbon" aria-hidden="true">
      <div class="track">
        <span v-for="n in 4" :key="n" class="set"><b v-for="g in groups" :key="g + n">{{ g }}</b></span>
      </div>
    </div>

    <div class="stage">
      <span class="cell c1" aria-hidden="true" /><span class="cell c2" aria-hidden="true" /><span class="cell c3" aria-hidden="true" />

      <div class="mark" role="img" aria-label="Blood Dispatch Network logo">
        <i class="ring r1" /><i class="ring r2" /><i class="ring r3" />
        <svg viewBox="0 0 64 64" aria-hidden="true">
          <g v-for="(p, i) in petals" :key="p.r" class="pet" :style="{ '--x': p.x + 'px', '--y': p.y + 'px', '--i': i }">
            <path :d="D" :fill="p.fill" :transform="`rotate(${p.r} 32 32) translate(32 35.5) scale(.41) translate(-32 -5)`" />
          </g>
        </svg>
      </div>

      <p class="word"><strong>Blood Dispatch</strong><small>Network</small></p>
      <h2>Ready when the next request comes in.</h2>
      <p class="sub">Spare blood is already nearby. Find it, and know when it will really arrive.</p>
      <NuxtLink to="/request" class="cta"><AppIcon name="drop" :size="22" /> Find blood now</NuxtLink>
    </div>

    <nav class="links" aria-label="Footer">
      <NuxtLink v-for="l in links" :key="l.label" :to="l.to">{{ l.label }}</NuxtLink>
      <NuxtLink to="/sign-in">Sign in</NuxtLink>
    </nav>
    <p class="fine">Hackathon prototype · Terumo BCT Africa Hackathon 2026 · All data is synthetic and does not describe real facilities.</p>
  </footer>
</template>

<style scoped>
.sf { position: relative; overflow: hidden; margin-top: 40px; color: #fff; background: radial-gradient(900px 420px at 50% 22%, #1a9a8d 0%, #0a6b62 45%, #053b36 100%); text-align: center; }
.ribbon { overflow: hidden; border-bottom: 1px solid rgba(255, 255, 255, 0.14); padding: 8px 0; }
.track { display: flex; width: max-content; animation: scroll 38s linear infinite; }
.set { display: flex; gap: 38px; padding-right: 38px; }
.set b { font-family: Caveat, cursive; font-size: 22px; font-weight: 700; color: rgba(255, 255, 255, 0.34); white-space: nowrap; }
.set b::after { content: '•'; margin-left: 38px; color: rgba(255, 255, 255, 0.2); }
@keyframes scroll { to { transform: translateX(-25%); } }

.stage { position: relative; padding: 32px 20px 20px; display: flex; flex-direction: column; align-items: center; }
.cell { position: absolute; border-radius: 50%; background: radial-gradient(ellipse at 35% 30%, #4fb5a8 0%, #0a6b62 58%, #064a44 100%); box-shadow: inset -6px -8px 14px rgba(4, 40, 38, 0.4); filter: blur(1.5px); opacity: 0.55; animation: bob 7s ease-in-out infinite; }
.c1 { width: 120px; height: 66px; left: -30px; top: 70px; transform: rotate(-24deg); }
.c2 { width: 90px; height: 50px; right: -16px; top: 150px; transform: rotate(28deg); animation-delay: -2s; }
.c3 { width: 70px; height: 38px; left: 12%; bottom: 150px; transform: rotate(14deg); animation-delay: -4s; opacity: 0.4; }
@keyframes bob { 50% { translate: 0 -12px; } }

.mark { position: relative; width: 84px; height: 84px; display: grid; place-items: center; }
.mark svg { position: relative; width: 84px; height: 84px; overflow: visible; filter: drop-shadow(0 10px 22px rgba(4, 40, 38, 0.45)); }
.pet { transform-box: view-box; transform-origin: 32px 32px; animation: lock 5s cubic-bezier(0.2, 0.9, 0.2, 1) infinite; animation-delay: calc(var(--i) * 0.12s); }
@keyframes lock {
  0% { opacity: 0; transform: translate(var(--x), var(--y)) scale(0.4) rotate(40deg); }
  12% { opacity: 1; }
  26%, 84% { opacity: 1; transform: none; }
  96%, 100% { opacity: 0; transform: translate(var(--x), var(--y)) scale(0.4) rotate(-40deg); }
}
.ring { position: absolute; inset: 0; border-radius: 50%; border: 2px solid rgba(255, 255, 255, 0.55); opacity: 0; animation: ping 5s ease-out infinite; }
.r2 { animation-delay: 0.25s; }
.r3 { animation-delay: 0.5s; }
@keyframes ping { 0%, 24% { opacity: 0; transform: scale(0.6); } 28% { opacity: 0.9; } 52%, 100% { opacity: 0; transform: scale(2.3); } }

.word { margin: 10px 0 0; display: flex; flex-direction: column; align-items: center; line-height: 1; }
.word strong { font-size: clamp(20px, 4vw, 34px); font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; background: linear-gradient(90deg, #fff 0%, #cfeae6 40%, #fff 80%); background-size: 200% 100%; -webkit-background-clip: text; background-clip: text; color: transparent; animation: shine 6s ease-in-out infinite; }
.word small { margin-top: 6px; font-size: clamp(10px, 1.2vw, 12px); font-weight: 700; letter-spacing: 0.5em; text-transform: uppercase; color: #bfe3de; padding-left: 0.5em; }
@keyframes shine { 0%, 100% { background-position: 100% 0; } 50% { background-position: 0 0; } }

h2 { margin: 18px 0 0; font-size: clamp(18px, 2.6vw, 26px); line-height: 1.1; letter-spacing: -0.02em; text-transform: uppercase; max-width: 720px; }
.sub { margin: 6px 0 0; font-size: 14.5px; font-weight: 500; color: #cfeae6; max-width: 460px; line-height: 1.5; }
.cta { margin-top: 16px; display: inline-flex; align-items: center; gap: 10px; min-height: 50px; padding: 0 26px; border-radius: 99px; background: #fff; color: var(--primary-700); font-weight: 800; font-size: 16px; text-decoration: none; box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.5), 0 16px 30px rgba(3, 30, 28, 0.4); animation: halo 2.6s ease-out infinite; transition: transform 0.2s ease; }
.cta:hover { transform: translateY(-3px) scale(1.03); }
@keyframes halo { to { box-shadow: 0 0 0 18px rgba(255, 255, 255, 0), 0 16px 30px rgba(3, 30, 28, 0.4); } }

.links { display: flex; flex-wrap: wrap; justify-content: center; gap: 2px 6px; padding: 4px 16px; margin-top: 8px; border-top: 1px solid rgba(255, 255, 255, 0.14); margin: 0 16px; }
.links a { min-height: 44px; display: inline-flex; align-items: center; padding: 0 14px; border-radius: 99px; color: #dff1ee; font-weight: 700; font-size: 14px; text-decoration: none; transition: background 0.2s ease; }
.links a:hover { background: rgba(255, 255, 255, 0.14); }
.fine { margin: 0; padding: 2px 20px 16px; font-size: 12px; font-weight: 600; color: rgba(255, 220, 216, 0.7); }
@media (max-width: 520px) { .set b { font-size: 20px; } .mark, .mark svg { width: 72px; height: 72px; } }
</style>
