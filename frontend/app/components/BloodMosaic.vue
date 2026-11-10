<script setup lang="ts">
// A skyline of blood-group blocks. One spare bag lifts off a tall column and lands in the gap
// next to it: sharing, shown in one loop.
const letters = ['AB−', 'O−', 'A−', 'B+', 'O+', 'AB+', 'A+', 'B−']
const heights = [3, 4, 2, 3, 4, 3, 2, 4]
const tones = ['#c8423b', '#b3171e', '#d65a50', '#9c1a1c', '#e06b60', '#a8201f']
const cols = heights.map((h, c) => ({
  c,
  tiles: Array.from({ length: h }, (_, r) => ({
    key: `${c}-${r}`,
    label: letters[(c * 3 + r * 5) % letters.length],
    tone: tones[(c * 2 + r * 3) % tones.length],
    delay: `${c * 70 + r * 90}ms`
  }))
}))
</script>

<template>
  <div class="mosaic" role="img" aria-label="Blocks of every blood group. A spare bag moves from one hospital to fill a gap at another.">
    <div class="cols">
      <div v-for="col in cols" :key="col.c" class="col">
        <span
          v-for="t in col.tiles" :key="t.key" class="tile" :style="{ background: t.tone, animationDelay: t.delay }"
        ><b>{{ t.label }}</b></span>
        <span v-if="col.c === 5" class="slot"><span class="fill"><b>B+</b></span></span>
      </div>
    </div>
    <span class="bag"><b>B+</b></span>
  </div>
</template>

<style scoped>
.mosaic { position: relative; width: 100%; aspect-ratio: 8 / 8; }
.cols { position: absolute; inset: auto 0 0 0; display: grid; grid-template-columns: repeat(8, 1fr); align-items: end; }
.col { display: flex; flex-direction: column-reverse; }
.tile, .slot, .bag { aspect-ratio: 1; display: grid; place-items: center; }
.tile { color: rgba(255, 255, 255, 0.55); font-size: clamp(9px, 1.6vw, 15px); animation: tileUp 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.tile b, .fill b, .bag b { font-weight: 800; letter-spacing: -0.01em; }
.slot { border: 2px dashed rgba(179, 23, 30, 0.55); border-radius: 4px; margin: 1px; order: 9; position: relative; }
.fill { position: absolute; inset: -2px; background: var(--blood-500); color: #fff; display: grid; place-items: center; font-size: clamp(9px, 1.6vw, 15px); animation: land 7s ease-in-out infinite; }
.bag {
  position: absolute; left: 0; bottom: 0; width: 12.5%; background: linear-gradient(180deg, #d12b31, #8c1015); color: #fff;
  border-radius: 6px; font-size: clamp(10px, 1.8vw, 16px); box-shadow: 0 10px 22px rgba(126, 16, 21, 0.4);
  animation: carry 7s ease-in-out infinite; opacity: 0;
}
@keyframes tileUp { from { opacity: 0; transform: translateY(40px); } to { opacity: 1; transform: none; } }
@keyframes carry {
  0% { opacity: 0; transform: translate(100%, -420%) rotate(-10deg); }
  10% { opacity: 1; transform: translate(100%, -460%) rotate(-6deg); }
  50% { opacity: 1; transform: translate(360%, -520%) rotate(8deg); }
  68% { opacity: 1; transform: translate(500%, -250%) rotate(2deg); }
  74%, 100% { opacity: 0; transform: translate(500%, -200%) rotate(0deg); }
}
@keyframes land {
  0%, 66% { opacity: 0; transform: scale(0.5); }
  74% { opacity: 1; transform: scale(1.06); }
  80%, 94% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .fill { opacity: 1; }
  .bag { display: none; }
}
</style>
