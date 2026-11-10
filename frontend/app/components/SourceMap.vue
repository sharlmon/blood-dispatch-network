<script setup lang="ts">
import type { Option } from '~/utils/engine'

const props = withDefaults(defineProps<{
  options: Option[]
  selectedId: string | null
  /** the requesting hospital's name, under the centre marker */
  youLabel?: string
  padTop?: number
  padBottom?: number
  padX?: number
  maxZoom?: number
  panels?: boolean
}>(), {
  youLabel: 'Your hospital', padTop: 96, padBottom: 36, padX: 56, maxZoom: 2, panels: false
})
const emit = defineEmits<{ select: [id: string] }>()

const YOU = { x: 200, y: 150 }
const CIRCLE_PIN = 'M0 0C-9-10-14-16-14-23a14 14 0 0 1 28 0c0 7-5 13-14 23z'
const SQUARE_PIN = 'M-12-36h24a3 3 0 0 1 3 3v21a3 3 0 0 1-3 3h-8L0 0l-4-9h-8a3 3 0 0 1-3-3v-21a3 3 0 0 1 3-3z'
const DROP_SMALL = 'M0-31c3.5 4 5.5 6.5 5.5 9a5.5 5.5 0 0 1-11 0c0-2.5 2-5 5.5-9z'
// Named apart from the auto-imported DROP icon: a clashing name breaks template type checks.
const TRAVEL_DROP = 'M0-10C4-4 7.5 0 7.5 3.5a7.5 7.5 0 0 1-15 0C-7.5 0-4-4 0-10z'

const chipW = (o: Option) => Math.max(54, fmtHours(o.p50).length * 7.6 + 20)
// Road distance from the routes table, else the map driving time.
const distance = (o: Option) => (o.roadKm != null ? fmtKm(o.roadKm) : o.travelHoursMap != null ? `${fmtHours(o.travelHoursMap)} drive` : '')
const distW = (o: Option) => Math.max(52, distance(o).length * 7 + 18)
const ctrl = (o: Option) => ({ x: (YOU.x + o.x) / 2, y: (YOU.y + o.y) / 2 - 24 })
const routePath = (o: Option) => `M${YOU.x} ${YOU.y} Q${ctrl(o).x} ${ctrl(o).y} ${o.x} ${o.y}`
const mid = (o: Option) => ({ x: 0.25 * YOU.x + 0.5 * ctrl(o).x + 0.25 * o.x, y: 0.25 * YOU.y + 0.5 * ctrl(o).y + 0.25 * o.y })

const root = ref<HTMLElement | null>(null)
const svg = ref<SVGSVGElement | null>(null)
const box = reactive({ w: 400, h: 300 })
onMounted(() => {
  if (!root.value) return
  const ro = new ResizeObserver(([e]) => { box.w = e!.contentRect.width || 400; box.h = e!.contentRect.height || 300 })
  ro.observe(root.value)
  onBeforeUnmount(() => ro.disconnect())
})

// Fit a set of points into the free part of the map (the middle, when the side panels float over it).
function fit(pts: { x: number; y: number }[]) {
  const minX = Math.min(...pts.map(p => p.x)), maxX = Math.max(...pts.map(p => p.x))
  const minY = Math.min(...pts.map(p => p.y)), maxY = Math.max(...pts.map(p => p.y))
  const bw = Math.max(maxX - minX, 40), bh = Math.max(maxY - minY, 40)
  const insetL = props.panels && box.w >= 900 ? 510 : 0
  const insetR = props.panels && box.w >= 900 ? 390 : 0
  const availW = box.w - insetL - insetR - 2 * props.padX
  const availH = box.h - props.padTop - props.padBottom
  const s = Math.min(Math.max(Math.min(availW / bw, availH / bh), 0.2), props.maxZoom)
  const vw = box.w / s, vh = box.h / s
  const cx = (minX + maxX) / 2
  const x0 = cx - (insetL + (box.w - insetL - insetR) / 2) / s
  const y0 = minY - (props.padTop + (availH - bh * s) / 2) / s
  return { s, x0, y0, vw, vh, cx: x0 + vw / 2, cy: y0 + vh / 2 }
}
const base = computed(() => fit([YOU, ...props.options]))

// Zoom (z) and pan (in map units, from the base centre). Both animate when the view flies somewhere.
const z = ref(1)
const pan = reactive({ x: 0, y: 0 })
const view = computed(() => {
  const b = base.value
  const cx = b.cx + pan.x, cy = b.cy + pan.y
  const vw = b.vw / z.value, vh = b.vh / z.value
  return { x: cx - vw / 2, y: cy - vh / 2, vw, vh, k: 1 / (b.s * z.value) }
})
const viewBox = computed(() => `${view.value.x} ${view.value.y} ${view.value.vw} ${view.value.vh}`)

let raf = 0
const reduce = () => import.meta.client && matchMedia('(prefers-reduced-motion: reduce)').matches
function flyTo(zt: number, px: number, py: number, ms = 520) {
  cancelAnimationFrame(raf)
  if (reduce() || ms === 0) { z.value = zt; pan.x = px; pan.y = py; return }
  const z0 = z.value, x0 = pan.x, y0 = pan.y, t0 = performance.now()
  const step = (t: number) => {
    const p = Math.min(1, (t - t0) / ms)
    const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
    z.value = z0 + (zt - z0) * e; pan.x = x0 + (px - x0) * e; pan.y = y0 + (py - y0) * e
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}
const MAXZ = 4
function focusOn(o: Option | undefined) {
  const b = base.value
  if (!o) return flyTo(1, 0, 0)
  const f = fit([YOU, o])
  flyTo(Math.min(MAXZ, Math.max(1, f.s / b.s)), f.cx - b.cx, f.cy - b.cy)
}
function reset() { touched.value = false; flyTo(1, 0, 0) }
const selected = computed(() => props.options.find(o => o.id === props.selectedId))
// Picking a source never throws the others out of view: the map only pans (keeping your zoom)
// when the pick is outside the free area, or when you have already zoomed in.
const insets = () => ({ l: props.panels && box.w >= 900 ? 510 : 0, r: props.panels && box.w >= 900 ? 390 : 0 })
function centerOn(o: Option) {
  const v = view.value, { l, r } = insets()
  const fx = l + (box.w - l - r) / 2, fy = props.padTop + (box.h - props.padTop - props.padBottom) / 2
  const ux = v.x + (fx / box.w) * v.vw, uy = v.y + (fy / box.h) * v.vh
  flyTo(z.value, pan.x + (o.x - ux), pan.y + (o.y - 28 - uy), 420)
}
function visible(o: Option) {
  const v = view.value, { l, r } = insets()
  const px = ((o.x - v.x) / v.vw) * box.w, py = ((o.y - v.y) / v.vh) * box.h
  return px > l + 30 && px < box.w - r - 30 && py > props.padTop + 20 && py < box.h - props.padBottom
}
watch(() => props.selectedId, () => {
  const o = selected.value
  if (!o) return
  if (z.value > 1.05 || touched.value || !visible(o)) centerOn(o)
})
onBeforeUnmount(() => cancelAnimationFrame(raf))

// Pointer interaction: drag to pan, wheel or pinch to zoom around the pointer.
const touched = ref(false)
const dragging = ref(false)
const pts = new Map<number, { x: number; y: number }>()
let lastDist = 0
let moved = 0
const toUnits = (cx: number, cy: number) => {
  const r = svg.value!.getBoundingClientRect(), v = view.value
  return { x: v.x + ((cx - r.left) / r.width) * v.vw, y: v.y + ((cy - r.top) / r.height) * v.vh }
}
function zoomAt(nz: number, cx: number, cy: number) {
  cancelAnimationFrame(raf)
  nz = Math.min(MAXZ, Math.max(0.6, nz))
  const before = toUnits(cx, cy)
  z.value = nz
  const after = toUnits(cx, cy)
  pan.x += before.x - after.x; pan.y += before.y - after.y
  touched.value = true
}
function down(e: PointerEvent) {
  hover.value = null
  pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
  moved = 0
  if (pts.size === 2) { const [a, b] = [...pts.values()]; lastDist = Math.hypot(a!.x - b!.x, a!.y - b!.y) }
}
function move(e: PointerEvent) {
  const p = pts.get(e.pointerId)
  if (!p) return
  if (pts.size === 2) {
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const [a, b] = [...pts.values()]
    const d = Math.hypot(a!.x - b!.x, a!.y - b!.y)
    if (lastDist) zoomAt(z.value * (d / lastDist), (a!.x + b!.x) / 2, (a!.y + b!.y) / 2)
    lastDist = d
    return
  }
  const dx = e.clientX - p.x, dy = e.clientY - p.y
  moved += Math.abs(dx) + Math.abs(dy)
  if (moved < 4) return
  if (!dragging.value) { dragging.value = true; svg.value?.setPointerCapture(e.pointerId); cancelAnimationFrame(raf) }
  pan.x -= dx * view.value.k; pan.y -= dy * view.value.k
  touched.value = true
  pts.set(e.pointerId, { x: e.clientX, y: e.clientY })
}
function up(e: PointerEvent) {
  pts.delete(e.pointerId)
  if (pts.size < 2) lastDist = 0
  if (!pts.size) setTimeout(() => { dragging.value = false }, 0)
}
function wheel(e: WheelEvent) {
  e.preventDefault()
  zoomAt(z.value * Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY)
}
function dbl(e: MouseEvent) { zoomAt(z.value * 1.6, e.clientX, e.clientY) }
function key(e: KeyboardEvent) {
  const step = 40 * view.value.k
  if (e.key === '+' || e.key === '=') { zoomBy(1.4); e.preventDefault() }
  else if (e.key === '-') { zoomBy(1 / 1.4); e.preventDefault() }
  else if (e.key === '0') { reset(); e.preventDefault() }
  else if (e.key === 'ArrowLeft') { pan.x -= step; touched.value = true; e.preventDefault() }
  else if (e.key === 'ArrowRight') { pan.x += step; touched.value = true; e.preventDefault() }
  else if (e.key === 'ArrowUp') { pan.y -= step; touched.value = true; e.preventDefault() }
  else if (e.key === 'ArrowDown') { pan.y += step; touched.value = true; e.preventDefault() }
}
function zoomBy(f: number) {
  const r = svg.value!.getBoundingClientRect()
  zoomAt(z.value * f, r.left + r.width / 2, r.top + r.height / 2)
}
onMounted(() => svg.value?.addEventListener('wheel', wheel, { passive: false }))
onBeforeUnmount(() => svg.value?.removeEventListener('wheel', wheel))

// Hover card over a pin.
const hover = ref<string | null>(null)
const hovered = computed(() => props.options.find(o => o.id === hover.value))
const hoverPos = computed(() => {
  const o = hovered.value
  if (!o) return null
  const v = view.value
  return { x: ((o.x - v.x) / v.vw) * box.w, y: ((o.y - v.y) / v.vh) * box.h }
})
function pick(id: string) { if (!dragging.value) emit('select', id) }
const zoomPct = computed(() => Math.round(z.value * 100))
</script>

<template>
  <div ref="root" class="map-root" :class="{ grabbing: dragging }">
    <svg
      ref="svg" class="source-map" :viewBox="viewBox" preserveAspectRatio="xMidYMid slice" role="application" tabindex="0"
      :aria-label="`Map of ${youLabel} and nearby sources. Drag to move, scroll or pinch to zoom, plus and minus keys zoom, zero resets.`"
      @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @dblclick="dbl" @keydown="key"
    >
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
        v-for="o in options" :key="'r' + o.id" :d="routePath(o)" fill="none" stroke-linecap="round" class="route"
        :class="{ flow: o.id === selectedId }" :stroke="o.id === selectedId ? '#0a6b62' : '#7c909f'" :stroke-width="(o.id === selectedId ? 4 : 3) * view.k" :stroke-dasharray="`${view.k} ${9 * view.k}`"
      />

      <!-- blood on its way: a drop travels the selected route -->
      <g v-if="selected" :key="'t' + selected.id" class="trav" pointer-events="none">
        <animateMotion :path="routePath(selected)" dur="2.6s" repeatCount="indefinite" />
        <g :transform="`scale(${view.k})`"><path :d="TRAVEL_DROP" fill="#b3171e" stroke="#fff" stroke-width="2.5" /></g>
      </g>

      <!-- distance on the selected route -->
      <g v-if="selected && distance(selected)" :transform="`translate(${mid(selected).x} ${mid(selected).y}) scale(${view.k})`" pointer-events="none">
        <rect :x="-distW(selected) / 2" y="-11" :width="distW(selected)" height="22" rx="11" fill="#12202b" />
        <text y="4" text-anchor="middle" font-size="11.5" font-weight="800" fill="#fff" font-family="Manrope, sans-serif">{{ distance(selected) }}</text>
      </g>

      <g :transform="`translate(${YOU.x} ${YOU.y}) scale(${view.k})`" pointer-events="none">
        <circle r="24" fill="#1d6fd8" fill-opacity="0.16" />
        <circle r="9" fill="#1d6fd8" stroke="#fff" stroke-width="3" />
        <text y="28" text-anchor="middle" font-size="12" font-weight="800" fill="#12202b" stroke="#fff" stroke-width="4" paint-order="stroke" font-family="Manrope, sans-serif">{{ youLabel }}</text>
      </g>

      <g
        v-for="(o, i) in options" :key="o.id" class="pin" :class="{ sel: o.id === selectedId }" role="button" tabindex="0"
        :aria-label="`${i + 1}. ${o.name}, ${fmtHours(o.p50)}`" :transform="`translate(${o.x} ${o.y}) scale(${view.k})`"
        @click.stop="pick(o.id)" @keydown.enter.stop="pick(o.id)" @keydown.space.prevent.stop="pick(o.id)"
        @pointerenter="hover = o.id" @pointerleave="hover = null" @focus="hover = o.id" @blur="hover = null"
      >
        <g class="drop" :style="{ animationDelay: i * 120 + 'ms' }">
          <g class="body" :transform="o.id === selectedId ? 'scale(1.25)' : 'scale(1)'">
            <path v-if="o.kind === 'hospital'" :d="CIRCLE_PIN" :fill="o.id === selectedId ? '#0a6b62' : '#4a5b68'" stroke="#fff" stroke-width="3" />
            <path v-else :d="SQUARE_PIN" :fill="o.id === selectedId ? '#0a6b62' : '#4a5b68'" stroke="#fff" stroke-width="3" />
            <path v-if="o.kind === 'hospital'" d="M0-30v13M-6.5-23.5h13" stroke="#fff" stroke-width="3" stroke-linecap="round" />
            <path v-else :d="DROP_SMALL" fill="#fff" />
          </g>
          <g :transform="`translate(0 ${o.id === selectedId ? -54 : -46})`">
            <rect :x="-chipW(o) / 2" y="-12" :width="chipW(o)" height="22" rx="11" :fill="o.id === selectedId ? '#0a6b62' : '#fff'" :stroke="o.id === selectedId ? '#0a6b62' : '#d5dde3'" />
            <text x="0" y="3.5" text-anchor="middle" font-size="12" font-weight="800" :fill="o.id === selectedId ? '#fff' : '#12202b'" font-family="Manrope, sans-serif">{{ fmtHours(o.p50) }}</text>
          </g>
        </g>
      </g>
    </svg>

    <!-- hover card -->
    <Transition name="tip">
      <div v-if="hovered && hoverPos && hovered.id !== selectedId" class="tip" :style="{ left: hoverPos.x + 'px', top: hoverPos.y + 'px' }" role="tooltip">
        <b>{{ hovered.name }}</b>
        <span>{{ hovered.kind === 'hospital' ? 'Hospital' : 'Centre' }}<template v-if="distance(hovered)"> · {{ distance(hovered) }}</template> · {{ hovered.partial ? `${hovered.spare} spare (part)` : `${hovered.spare} spare` }}</span>
        <em>Most likely {{ fmtHours(hovered.p50) }} · 8 in 10: {{ fmtRange(hovered.p10, hovered.p90) }}</em>
        <i>Click to select</i>
      </div>
    </Transition>

    <!-- controls -->
    <div class="ctrls" role="group" aria-label="Map controls">
      <button type="button" aria-label="Zoom in" :disabled="z >= MAXZ - 0.01" @click="zoomBy(1.5)"><AppIcon name="plus" :size="20" /></button>
      <button type="button" aria-label="Zoom out" :disabled="z <= 0.61" @click="zoomBy(1 / 1.5)"><span class="minus" /></button>
      <button type="button" aria-label="Show all sources" title="Show all sources" @click="reset"><AppIcon name="pin" :size="20" /></button>
      <button v-if="selected" type="button" aria-label="Focus the selected source" title="Focus the selected source" @click="focusOn(selected)"><AppIcon name="route" :size="20" /></button>
    </div>

    <p class="legend" aria-hidden="true">
      <span><i class="you" /> You</span>
      <span><i class="h" /> Hospital</span>
      <span><i class="c" /> Centre</span>
    </p>
    <p class="hint" :class="{ gone: touched }" aria-hidden="true">Drag to move · scroll or pinch to zoom</p>
    <p class="sr-only" aria-live="polite">Zoom {{ zoomPct }} percent</p>
  </div>
</template>

<style scoped>
.map-root { position: absolute; inset: 0; overflow: hidden; }
.source-map { position: absolute; inset: 0; width: 100%; height: 100%; display: block; cursor: grab; touch-action: none; outline: none; user-select: none; -webkit-user-select: none; }
.grabbing .source-map { cursor: grabbing; }
.source-map:focus-visible { box-shadow: inset 0 0 0 3px rgba(29, 111, 216, 0.5); }
.pin { cursor: pointer; outline: none; }
.pin .body { transition: transform 0.25s cubic-bezier(0.3, 1.4, 0.5, 1); }
.pin:hover:not(.sel) .body { transform: scale(1.15); }
.route { transition: stroke 0.3s ease; }
.flow { animation: flow 1.2s linear infinite; }
@keyframes pinDrop { from { opacity: 0; transform: translateY(-26px); } to { opacity: 1; transform: none; } }
@keyframes bounce { 0% { transform: translateY(0); } 35% { transform: translateY(-14px); } 70% { transform: translateY(2px); } 100% { transform: none; } }
@keyframes flow { to { stroke-dashoffset: -30; } }
@keyframes pulse { 0% { transform: scale(0.6); opacity: 0.9; } 100% { transform: scale(1.5); opacity: 0; } }
.pin:focus-visible path:first-of-type { stroke: #1d6fd8; stroke-width: 4; }

.tip { position: absolute; z-index: 5; transform: translate(-50%, calc(-100% - 70px)); width: 230px; padding: 10px 14px; border-radius: 18px; background: rgba(255, 255, 255, 0.97); border: 1.5px solid #d8e4e2; box-shadow: 0 14px 30px rgba(4, 40, 38, 0.22); display: flex; flex-direction: column; gap: 2px; pointer-events: none; }
.tip b { font-size: 14px; color: var(--ink); }
.tip span { font-size: 12.5px; font-weight: 600; color: var(--slate); }
.tip em { font-style: normal; font-size: 13px; font-weight: 800; color: var(--primary-600); }
.tip i { font-style: normal; font-size: 11.5px; font-weight: 700; color: var(--teal-600); margin-top: 2px; }
.tip-enter-active, .tip-leave-active { transition: opacity 0.15s ease, translate 0.2s ease; }
.tip-enter-from, .tip-leave-to { opacity: 0; translate: 0 6px; }

.ctrls { position: absolute; z-index: 4; display: flex; flex-direction: column; gap: 8px; right: 12px; top: 64px; }
.ctrls button { width: 46px; height: 46px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: rgba(255, 255, 255, 0.96); color: var(--primary-700); display: grid; place-items: center; box-shadow: 0 8px 18px rgba(4, 40, 38, 0.14); transition: transform 0.2s ease, background 0.2s ease, opacity 0.2s ease; }
.ctrls button:hover:not(:disabled) { transform: translateY(-2px); background: var(--primary-50); }
.ctrls button:active:not(:disabled) { transform: scale(0.94); }
.ctrls button:disabled { opacity: 0.4; }
.minus { width: 16px; height: 2.5px; border-radius: 99px; background: currentColor; }
.legend { position: absolute; z-index: 3; left: 12px; top: 64px; margin: 0; display: none; gap: 14px; padding: 8px 14px; border-radius: 99px; background: rgba(255, 255, 255, 0.94); font-size: 12.5px; font-weight: 700; color: var(--ink); box-shadow: 0 8px 18px rgba(4, 40, 38, 0.12); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 12px; height: 12px; display: inline-block; }
.legend .you { border-radius: 99px; background: #1d6fd8; }
.legend .h { border-radius: 99px; background: #4a5b68; }
.legend .c { border-radius: 4px; background: #4a5b68; }
.hint { position: absolute; z-index: 3; left: 50%; transform: translateX(-50%); top: 14px; margin: 0; padding: 7px 14px; border-radius: 99px; background: rgba(18, 32, 43, 0.82); color: #fff; font-size: 12.5px; font-weight: 700; white-space: nowrap; transition: opacity 0.5s ease, transform 0.5s ease; animation: hintin 0.6s ease 1.2s both; }
.hint.gone { opacity: 0; transform: translate(-50%, -8px); pointer-events: none; animation: none; }
@keyframes hintin { from { opacity: 0; transform: translate(-50%, -8px); } to { opacity: 1; transform: translateX(-50%); } }
@media (min-width: 900px) {
  .ctrls { right: 410px; top: auto; bottom: 28px; }
  .legend { display: inline-flex; left: 530px; top: auto; bottom: 28px; }
  .hint { top: auto; bottom: 90px; left: calc(510px + (100% - 900px) / 2); }
}
@media (max-width: 899px) {
  .hint { display: none; }
  .ctrls { top: 62px; right: 10px; gap: 6px; }
  .ctrls button { width: 40px; height: 40px; }
  .ctrls button:nth-child(4) { display: none; }
}
</style>
