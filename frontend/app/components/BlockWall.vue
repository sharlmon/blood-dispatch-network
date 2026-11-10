<script setup lang="ts">
// A skyline of blood-group blocks with handwritten letters. One block floats above a gap:
// a spare bag about to be shared. Shows `max` columns (mobile always shows the first 6).
const props = withDefaults(defineProps<{ max?: number; gap?: number[]; mobileGap?: number; desktopGap?: number }>(), { max: 20, gap: () => [], mobileGap: -1, desktopGap: -1 })

const heights = [2, 1, 2, 1, 2, 2, 2, 1, 2, 2, 3, 2, 3, 1, 3, 2, 3, 2, 1, 2]
const letters = ['AB−', 'O−', 'A−', 'B+', 'O+', 'AB+', 'A+', 'B−']
const tones = ['#c8423b', '#b3171e', '#d65a50', '#9c1a1c', '#e06b60', '#a8201f', '#8f1519']

const cols = computed(() =>
  heights.slice(0, props.max).map((h, c) => ({
    c,
    tiles: Array.from({ length: h }, (_, r) => ({
      label: letters[(c * 3 + r * 5) % letters.length]!,
      tone: tones[(c * 2 + r * 3) % tones.length]!,
      delay: `${c * 50 + r * 80}ms`
    }))
  }))
)
</script>

<template>
  <div class="wall" aria-hidden="true">
    <div v-for="col in cols" :key="col.c" class="col">
      <span v-for="(t, i) in col.tiles" :key="i" class="tile hand" :style="{ background: t.tone, animationDelay: t.delay }">{{ t.label }}</span>
      <span v-if="gap.includes(col.c)" class="slot"><span class="block">B+</span></span>
      <span v-else-if="col.c === mobileGap" class="slot m"><span class="block">B+</span></span>
      <span v-else-if="col.c === desktopGap" class="slot d"><span class="block">B+</span></span>
    </div>
  </div>
</template>

<style scoped>
.wall { display: flex; align-items: flex-end; width: 100%; }
.col { flex: 1; min-width: 0; display: flex; flex-direction: column-reverse; }
.tile { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: clamp(18px, 2vw, 30px); color: rgba(255, 255, 255, 0.42); animation: tileUp 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.slot { position: relative; aspect-ratio: 1; box-sizing: border-box; border: 2.5px dashed rgba(179, 23, 30, 0.6); margin: 3px; }
.block {
  position: absolute; left: -3px; right: -3px; bottom: calc(100% + 26px); aspect-ratio: 1; display: grid; place-items: center;
  border-radius: 6px; background: linear-gradient(180deg, #d12b31, #8c1015); color: #fff; font-weight: 800; font-size: clamp(16px, 1.7vw, 24px);
  box-shadow: 0 16px 26px rgba(126, 16, 21, 0.45); transform: rotate(9deg); animation: bob 3.6s ease-in-out infinite;
}
@keyframes tileUp { from { opacity: 0; transform: translateY(36px); } to { opacity: 1; transform: none; } }
@keyframes bob { 0%, 100% { transform: translateY(0) rotate(9deg); } 50% { transform: translateY(-10px) rotate(4deg); } }
.slot.d { display: none; }
@media (min-width: 701px) { .slot.m { display: none; } .slot.d { display: block; } }
@media (max-width: 700px) { .col:nth-child(n + 7) { display: none; } }
</style>
