<script setup lang="ts">
// Convergence mark: four drops closing in on one point. Three red drops are the sources,
// the dark drop is your hospital. `reverse` is for dark and red backgrounds.
// The drops fly in and lock together on mount when `intro` is set, and again every time the
// shared logo tick changes (every 5 s, see plugins/brand-motion.client.ts).
const props = withDefaults(defineProps<{ size?: number; reverse?: boolean; intro?: boolean; still?: boolean }>(), { size: 32 })
const DROP = 'M32 5 C40 16 50 27 50 39 A18 18 0 0 1 14 39 C14 27 24 16 32 5 Z'
const OUT = 46
const petals = [
  { a: 0, x: 0, y: -OUT }, { a: 90, x: OUT, y: 0 }, { a: 180, x: 0, y: OUT }, { a: 270, x: -OUT, y: 0 }
].map((p, i) => ({ ...p, fill: props.reverse ? '#fff' : i === 0 ? '#1b1b1f' : 'var(--blood-500)', i }))

const tick = useState('logo-tick', () => 0)
const playing = ref(false)
let t: ReturnType<typeof setTimeout> | undefined
function play() {
  if (props.still) return
  playing.value = false
  requestAnimationFrame(() => { playing.value = true; clearTimeout(t); t = setTimeout(() => { playing.value = false }, 1800) })
}
onMounted(() => { if (props.intro) play() })
watch(tick, play)
onBeforeUnmount(() => clearTimeout(t))
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 64 64" role="img" aria-label="Blood Dispatch Network" :class="{ play: playing }" style="overflow: visible">
    <g v-for="p in petals" :key="p.a" class="pet" :style="{ '--x': p.x + 'px', '--y': p.y + 'px', '--i': p.i }">
      <path :d="DROP" :fill="p.fill" :transform="`rotate(${p.a} 32 32) translate(32 35.5) scale(.41) translate(-32 -5)`" />
    </g>
  </svg>
</template>

<style scoped>
.pet { transform-box: view-box; transform-origin: 32px 32px; }
.play .pet { animation: gather 1.5s cubic-bezier(0.2, 0.9, 0.25, 1) both; animation-delay: calc(var(--i) * 0.09s); }
@keyframes gather {
  0% { opacity: 0; transform: translate(var(--x), var(--y)) scale(0.35) rotate(50deg); }
  18% { opacity: 1; }
  70% { transform: scale(1.12) rotate(-4deg); }
  100% { opacity: 1; transform: none; }
}
</style>
