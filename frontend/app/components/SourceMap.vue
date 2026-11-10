<script setup lang="ts">
import type { Option } from '~/utils/mock'

const props = withDefaults(defineProps<{ options: Option[]; selectedId: string | null; padTop?: number; padBottom?: number; padX?: number; maxZoom?: number }>(), {
  padTop: 96, padBottom: 36, padX: 56, maxZoom: 2
})
defineEmits<{ select: [id: string] }>()

const YOU = { x: 200, y: 150 }
const CIRCLE_PIN = 'M0 0C-9-10-14-16-14-23a14 14 0 0 1 28 0c0 7-5 13-14 23z'
const SQUARE_PIN = 'M-12-36h24a3 3 0 0 1 3 3v21a3 3 0 0 1-3 3h-8L0 0l-4-9h-8a3 3 0 0 1-3-3v-21a3 3 0 0 1 3-3z'
const DROP_SMALL = 'M0-31c3.5 4 5.5 6.5 5.5 9a5.5 5.5 0 0 1-11 0c0-2.5 2-5 5.5-9z'

const routePath = (o: Option) => `M${YOU.x} ${YOU.y} Q${(YOU.x + o.x) / 2} ${(YOU.y + o.y) / 2 - 24} ${o.x} ${o.y}`

// Fit the pins into whatever size the map is drawn at, keeping pin size constant in px.
const svg = ref<SVGSVGElement | null>(null)
const box = reactive({ w: 400, h: 300 })
onMounted(() => {
  if (!svg.value) return
  const ro = new ResizeObserver(([e]) => {
    box.w = e!.contentRect.width || 400
    box.h = e!.contentRect.height || 300
  })
  ro.observe(svg.value)
  onBeforeUnmount(() => ro.disconnect())
})

const view = computed(() => {
  const pts = [YOU, ...props.options]
  const minX = Math.min(...pts.map(p => p.x)), maxX = Math.max(...pts.map(p => p.x))
  const minY = Math.min(...pts.map(p => p.y)), maxY = Math.max(...pts.map(p => p.y))
  const bw = Math.max(maxX - minX, 40), bh = Math.max(maxY - minY, 40)
  const availW = box.w - 2 * props.padX
  const availH = box.h - props.padTop - props.padBottom
  const s = Math.min(Math.max(Math.min(availW / bw, availH / bh), 0.2), props.maxZoom)
  const vw = box.w / s, vh = box.h / s
  const cx = (minX + maxX) / 2
  const x0 = cx - vw / 2
  const y0 = minY - (props.padTop + (availH - bh * s) / 2) / s
  return { box: `${x0} ${y0} ${vw} ${vh}`, k: 1 / s, x0, y0, vw, vh }
})
</script>

<template>
  <svg ref="svg" class="source-map" :viewBox="view.box" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Map of your hospital and nearby sources">
    <rect x="-1500" y="-1500" width="3400" height="3300" fill="#e9eef1" />
    <path d="M-1500 260 C-800 230 -300 330 200 290 S800 240 1900 270 L1900 900 L-1500 900Z" fill="#cfe3ee" />
    <rect x="236" y="14" width="110" height="62" rx="14" fill="#dceadf" />
    <rect x="-40" y="160" width="68" height="56" rx="12" fill="#dceadf" />
    <rect x="420" y="170" width="120" height="70" rx="14" fill="#dceadf" />
    <path d="M-1500 100 C-600 60 -200 140 250 108 S800 40 1900 90" stroke="#fff" stroke-width="13" fill="none" />
    <path d="M62 -900 C82 78 46 150 92 214 S144 280 134 900" stroke="#fff" stroke-width="11" fill="none" />
    <path d="M296 -900 C282 64 320 132 284 190 S330 400 320 900" stroke="#fff" stroke-width="9" fill="none" />
    <path d="M520 -900 C500 100 560 200 520 900" stroke="#fff" stroke-width="9" fill="none" />
    <path d="M-1500 180 C-300 170 100 192 300 176 S800 160 1900 170" stroke="#f8fafb" stroke-width="6" fill="none" />

    <path
      v-for="o in options" :key="'r' + o.id" :d="routePath(o)" fill="none" stroke-linecap="round"
      :stroke="o.id === selectedId ? '#c4122f' : '#7c909f'" :stroke-width="(o.id === selectedId ? 4 : 3) * view.k" :stroke-dasharray="`${view.k} ${9 * view.k}`"
    />

    <g :transform="`translate(${YOU.x} ${YOU.y}) scale(${view.k})`">
      <circle r="24" fill="#1d6fd8" fill-opacity="0.16" />
      <circle r="9" fill="#1d6fd8" stroke="#fff" stroke-width="3" />
    </g>

    <g
      v-for="(o, i) in options" :key="o.id" class="pin" role="button" tabindex="0"
      :aria-label="`${i + 1}. ${o.name}, ${fmtHours(o.p50)}`" :transform="`translate(${o.x} ${o.y}) scale(${view.k})`"
      @click="$emit('select', o.id)" @keydown.enter="$emit('select', o.id)"
    >
      <g :transform="o.id === selectedId ? 'scale(1.25)' : 'scale(1)'">
        <path v-if="o.kind === 'hospital'" :d="CIRCLE_PIN" :fill="o.id === selectedId ? '#c4122f' : '#4a5b68'" stroke="#fff" stroke-width="3" />
        <path v-else :d="SQUARE_PIN" :fill="o.id === selectedId ? '#c4122f' : '#4a5b68'" stroke="#fff" stroke-width="3" />
        <path v-if="o.kind === 'hospital'" d="M0-30v13M-6.5-23.5h13" stroke="#fff" stroke-width="3" stroke-linecap="round" />
        <path v-else :d="DROP_SMALL" fill="#fff" />
      </g>
      <g :transform="`translate(0 ${o.id === selectedId ? -54 : -46})`">
        <rect x="-26" y="-12" width="52" height="22" rx="11" fill="#fff" stroke="#d5dde3" />
        <text x="0" y="3.5" text-anchor="middle" font-size="12" font-weight="800" fill="#12202b" font-family="Manrope, sans-serif">{{ fmtHours(o.p50) }}</text>
      </g>
    </g>
  </svg>
</template>

<style scoped>
.source-map { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.pin { cursor: pointer; outline: none; }
.pin:focus-visible path:first-of-type { stroke: #1d6fd8; stroke-width: 4; }
</style>
