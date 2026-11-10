<script setup lang="ts">
// The footer of the landing hero: hospitals and a blood centre on layered red hills, linked by
// routes, with spare bags (drops) travelling between them. Decorative; motion respects
// prefers-reduced-motion.
const hospitals = [
  { x: 150, y: 188, tag: '3× B+' },
  { x: 430, y: 198, tag: '2× O+' },
  { x: 1010, y: 178, tag: '2× O−' },
  { x: 1290, y: 196, tag: '4× A+' }
]
const arcs = [
  'M150 140 Q290 64 430 150',
  'M430 150 Q580 52 720 118',
  'M720 118 Q870 44 1010 132',
  'M1010 132 Q1150 60 1290 148',
  'M150 140 Q440 -10 720 118'
]
const drops = [
  { path: arcs[0], dur: '5.2s', begin: '0s' },
  { path: arcs[1], dur: '5.8s', begin: '1.4s' },
  { path: arcs[2], dur: '5.4s', begin: '0.6s' },
  { path: arcs[3], dur: '6s', begin: '2.2s' },
  { path: arcs[4], dur: '7.2s', begin: '3s' }
]
const DROP = 'M0-10C4-4 7.500 0 7.500 3.500a7.500 7.500 0 0 1-15 0C-7.500 0-4-4 0-10z'
</script>

<template>
  <svg class="horizon" viewBox="0 0 1440 260" preserveAspectRatio="xMidYMax slice" role="img" aria-label="Hospitals and a blood centre linked by routes, with spare blood moving between them">
    <defs>
      <linearGradient id="hz-deep" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#085a53" /><stop offset="1" stop-color="#0c2b33" />
      </linearGradient>
      <linearGradient id="hz-mid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#159084" /><stop offset="1" stop-color="#085a53" />
      </linearGradient>
    </defs>

    <!-- hills -->
    <path d="M0 170C160 120 330 190 560 150S960 100 1160 150S1380 170 1440 130V260H0Z" fill="#8fc7bf" opacity="0.55" />
    <path d="M0 200C220 160 400 215 640 185S1020 150 1240 190S1400 205 1440 180V260H0Z" fill="url(#hz-mid)" />

    <!-- routes -->
    <g fill="none" stroke="#0a6b62" stroke-opacity="0.7" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="2 9">
      <path v-for="a in arcs" :key="a" :d="a" />
    </g>

    <!-- hospitals -->
    <g v-for="h in hospitals" :key="h.x" :transform="`translate(${h.x} ${h.y})`">
      <rect x="-27" y="-46" width="54" height="46" rx="5" fill="#e4f2f0" />
      <path d="M0-40v18M-9-31h18" stroke="#b3171e" stroke-width="5" stroke-linecap="round" />
      <rect x="-7" y="-13" width="14" height="13" rx="2" fill="#159084" />
      <text x="0" y="-62" text-anchor="middle" class="tag">{{ h.tag }}</text>
    </g>

    <!-- regional blood centre -->
    <g transform="translate(720 192)">
      <rect x="-62" y="-52" width="124" height="52" rx="6" fill="#e4f2f0" />
      <rect x="-44" y="-84" width="88" height="40" rx="6" fill="#fff" />
      <path :d="DROP" fill="#b3171e" transform="translate(0 -56) scale(1.5)" />
      <rect x="-9" y="-16" width="18" height="16" rx="2" fill="#159084" />
      <rect x="-50" y="-34" width="14" height="12" rx="2" fill="#b5dcd6" /><rect x="36" y="-34" width="14" height="12" rx="2" fill="#b5dcd6" />
      <text x="0" y="-100" text-anchor="middle" class="tag big">12 spare</text>
    </g>

    <!-- drops on the move -->
    <g v-for="d in drops" :key="d.path + d.begin" class="drop">
      <path :d="DROP" fill="#b3171e" stroke="#fff" stroke-width="2.500" />
      <animateMotion :path="d.path" :dur="d.dur" :begin="d.begin" repeatCount="indefinite" />
      <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.12;0.88;1" :dur="d.dur" :begin="d.begin" repeatCount="indefinite" />
    </g>

    <!-- front ground -->
    <path d="M0 225C260 200 520 235 780 215S1200 200 1440 222V260H0Z" fill="url(#hz-deep)" />
  </svg>
</template>

<style scoped>
.horizon { display: block; width: 100%; height: clamp(200px, 18vw, 270px); }
.tag { font-family: Caveat, cursive; font-weight: 700; font-size: 26px; fill: #064a44; stroke: #fff; stroke-width: 6; paint-order: stroke; stroke-linejoin: round; }
.tag.big { font-size: 32px; }
@media (prefers-reduced-motion: reduce) { .drop { display: none; } }
</style>
