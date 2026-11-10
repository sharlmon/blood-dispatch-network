<script setup lang="ts">
// Login splash: two hands place blood-group blocks into gaps in a mosaic skyline.
const T = 50
const heights = [3, 4, 2, 3, 3, 2, 4, 3]
const letters = ['AB−', 'O−', 'A−', 'B+', 'O+', 'AB+', 'A+', 'B−']
const tones = ['#c8423b', '#b3171e', '#d65a50', '#9c1a1c', '#e06b60', '#a8201f']
const H = 440
const tiles = heights.flatMap((h, c) =>
  Array.from({ length: h }, (_, r) => ({
    x: c * T, y: H - (r + 1) * T, label: letters[(c * 3 + r * 5) % letters.length]!, tone: tones[(c * 2 + r * 3) % tones.length]!,
    d: `${c * 70 + r * 80}ms`
  }))
)
const gaps = [{ c: 2, label: 'AB+', flip: false, delay: '0s' }, { c: 5, label: 'B−', flip: true, delay: '1.4s' }].map(g => ({
  ...g, x: g.c * T, y: H - (heights[g.c]! + 1) * T
}))
</script>

<template>
  <svg class="splash" viewBox="0 0 400 440" role="img" aria-label="Two hands place blocks of blood groups into gaps, completing a wall">
    <g v-for="t in tiles" :key="`${t.x}-${t.y}`" class="tile" :style="{ animationDelay: t.d }">
      <rect :x="t.x + 0.5" :y="t.y + 0.5" :width="T - 1" :height="T - 1" :fill="t.tone" />
      <text :x="t.x + T / 2" :y="t.y + T / 2 + 5" text-anchor="middle" font-size="14" font-weight="800" fill="rgba(255,255,255,0.5)" font-family="Manrope, sans-serif">{{ t.label }}</text>
    </g>
    <g v-for="g in gaps" :key="g.c">
      <rect :x="g.x + 3" :y="g.y + 3" :width="T - 6" :height="T - 6" fill="none" stroke="#b3171e" stroke-width="2" stroke-dasharray="5 5" opacity="0.55" />
      <g :transform="`translate(${g.x} ${g.y})`">
        <g class="drop" :style="{ animationDelay: g.delay }">
          <rect x="1" y="1" :width="T - 2" :height="T - 2" fill="#b3171e" />
          <text :x="T / 2" :y="T / 2 + 6" text-anchor="middle" font-size="16" font-weight="800" fill="#fff" font-family="Manrope, sans-serif">{{ g.label }}</text>
        </g>
      </g>
      <g :transform="`translate(${g.x + T / 2} ${g.y + 2})`">
        <g class="lift" :style="{ animationDelay: g.delay }"><HandHold :flip="g.flip" :angle="g.flip ? 30 : 34" /></g>
      </g>
    </g>
  </svg>
</template>

<style scoped>
.splash { width: 100%; height: auto; display: block; overflow: hidden; }
.tile { animation: tileUp 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.drop { animation: drop 7s ease-in-out infinite both; }
.lift { animation: lift 7s ease-in-out infinite both; }
@keyframes tileUp { from { opacity: 0; transform: translateY(40px); } to { opacity: 1; transform: none; } }
@keyframes drop {
  0% { translate: 0 -120px; opacity: 0; }
  6% { opacity: 1; }
  34% { translate: 0 0; }
  88% { translate: 0 0; opacity: 1; }
  100% { translate: 0 0; opacity: 0; }
}
@keyframes lift {
  0% { translate: 0 -120px; }
  34% { translate: 0 0; }
  58%, 100% { translate: 0 -150px; }
}
@media (prefers-reduced-motion: reduce) { .drop { opacity: 1; translate: none; } .lift { display: none; } }
</style>
