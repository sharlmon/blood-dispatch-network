<script setup lang="ts">
// Counts up from 0 to `to`, and replays every `every` ms while it is on screen.
// Server render and reduced-motion show the final value, so nothing is hidden without JS.
const props = withDefaults(defineProps<{
  to: number; prefix?: string; suffix?: string; decimals?: number; duration?: number; every?: number
}>(), { prefix: '', suffix: '', decimals: 0, duration: 1600, every: 5000 })

const shown = ref(props.to)
const el = ref<HTMLElement | null>(null)
let raf = 0
let timer = 0
let io: IntersectionObserver | null = null

const fmt = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: props.decimals, maximumFractionDigits: props.decimals })

function run() {
  cancelAnimationFrame(raf)
  const t0 = performance.now()
  const step = (t: number) => {
    const p = Math.min(1, (t - t0) / props.duration)
    shown.value = props.to * (1 - Math.pow(1 - p, 3))
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

function stop() {
  clearInterval(timer)
  timer = 0
  cancelAnimationFrame(raf)
  shown.value = props.to
}

onMounted(() => {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !el.value) return
  io = new IntersectionObserver(([e]) => {
    if (e?.isIntersecting) {
      if (!timer) { run(); timer = window.setInterval(run, props.every) }
    } else stop()
  }, { threshold: 0.4 })
  io.observe(el.value)
})
onBeforeUnmount(() => { stop(); io?.disconnect() })
</script>

<template>
  <span ref="el" class="cu tnum"><span aria-hidden="true">{{ prefix }}{{ fmt(shown) }}{{ suffix }}</span><span class="sr">{{ prefix }}{{ fmt(to) }}{{ suffix }}</span></span>
</template>

<style scoped>
.cu { display: inline-block; font-variant-numeric: tabular-nums; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
