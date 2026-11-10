<script setup lang="ts">
// "One request, in a minute": a little map with the requesting hospital in the middle and each
// source placed by distance. Tap a source (or let it cycle) to see its arrival window.
import type { Option } from '~/utils/mock'
import { GLOBE } from '~/utils/globe'

const props = defineProps<{ options: Option[]; limit: number; group: string; units: number; product: string; hospital: string }>()
const img = useImg()

const C = { x: GLOBE.me[0], y: GLOBE.me[1] }
// where each source's ETA tag sits relative to its pin
const TAGS: [number, number][] = [[0, -34], [0, 40], [0, -34]]
const pins = computed(() => props.options.slice(0, 3).map((o, i) => {
  const [x, y] = GLOBE.pins[i]!
  // lift each route into an arc so it reads as a flight over the globe
  const mx = (x + C.x) / 2
  const my = Math.min(y, C.y) - 46
  return { o, i, x, y, path: `M${x} ${y} Q${mx} ${my} ${C.x} ${C.y}`, tag: TAGS[i]! }
}))

const sel = ref(0)
const current = computed(() => pins.value[sel.value]!)
function pick(i: number) { sel.value = i }

const verdict = computed(() => {
  const o = current.value.o
  if (o.p90 > props.limit) return { tone: 'warn', text: `Could run past your ${props.limit} h limit at the slow end. Worth a call.` }
  return { tone: 'ok', text: `Inside your ${props.limit} h limit, even at the slow end.` }
})
const DROP = 'M0-10C4-4 7.500 0 7.500 3.500a7.500 7.500 0 0 1-15 0C-7.500 0-4-4 0-10z'
</script>

<template>
  <div class="story">
    <header class="req">
      <span class="clock"><AppIcon name="clock" :size="16" /> 01:04</span>
      <span class="grp">{{ group }}</span>
      <span class="rt"><b>{{ units }} units · {{ product.toLowerCase() }}</b><small>{{ hospital }} · limit {{ limit }} h</small></span>
    </header>

    <div class="body">
      <div class="map organic" aria-label="Sources placed by distance from the requesting hospital">
        <svg viewBox="0 0 560 410" role="img" :aria-label="`${pins.length} sources around ${hospital}, drawn on a globe`">
          <defs>
            <linearGradient id="gl-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" /><stop offset="1" stop-color="#e3efed" /></linearGradient>
            <radialGradient id="gl-ball" :cx="GLOBE.cx" :cy="GLOBE.cy - GLOBE.r * 0.55" :r="GLOBE.r * 1.15" gradientUnits="userSpaceOnUse">
              <stop offset="0" stop-color="#f6faf9" /><stop offset="0.7" stop-color="#c4dcd8" /><stop offset="1" stop-color="#9fcfc8" />
            </radialGradient>
            <radialGradient id="gl-halo" :cx="GLOBE.cx" :cy="GLOBE.cy" :r="GLOBE.r + 46" gradientUnits="userSpaceOnUse">
              <stop :offset="GLOBE.r / (GLOBE.r + 46)" stop-color="#7fd6c9" stop-opacity="0.55" /><stop offset="1" stop-color="#7fd6c9" stop-opacity="0" />
            </radialGradient>
            <clipPath id="gl-clip"><circle :cx="GLOBE.cx" :cy="GLOBE.cy" :r="GLOBE.r" /></clipPath>
          </defs>
          <rect width="560" height="410" fill="url(#gl-sky)" />
          <!-- atmosphere, the globe, then land as dots -->
          <circle :cx="GLOBE.cx" :cy="GLOBE.cy" :r="GLOBE.r + 46" fill="url(#gl-halo)" />
          <circle :cx="GLOBE.cx" :cy="GLOBE.cy" :r="GLOBE.r" fill="url(#gl-ball)" />
          <g clip-path="url(#gl-clip)">
            <path :d="GLOBE.dots" class="land" />
            <ellipse :cx="GLOBE.cx" :cy="GLOBE.cy - GLOBE.r" :rx="GLOBE.r * 0.9" ry="70" fill="#fff" opacity="0.28" />
          </g>
          <circle :cx="GLOBE.cx" :cy="GLOBE.cy" :r="GLOBE.r" fill="none" stroke="#fff" stroke-width="2.5" opacity="0.8" />

          <!-- routes -->
          <g v-for="p in pins" :key="p.o.id" fill="none" stroke-linecap="round">
            <path :d="p.path" class="route" :class="{ on: p.i === sel }" />
          </g>
          <g v-if="current" :key="'d' + sel" class="drop">
            <path :d="DROP" fill="#b3171e" stroke="#fff" stroke-width="2.5" />
            <animateMotion :path="current.path" dur="2.4s" repeatCount="indefinite" />
          </g>

          <!-- your hospital -->
          <g :transform="`translate(${C.x} ${C.y})`">
                        <circle r="20" fill="#1b1b1f" stroke="#fff" stroke-width="3" />
            <path d="M0-9v18M-9 0h18" stroke="#fff" stroke-width="4.5" stroke-linecap="round" />
            <text y="38" text-anchor="middle" class="me">Your hospital</text>
          </g>

          <!-- sources -->
          <g v-for="p in pins" :key="'p' + p.o.id" class="pin" :class="{ on: p.i === sel }" :transform="`translate(${p.x} ${p.y})`" tabindex="0" role="button" :aria-label="`${p.o.name}, about ${fmtHours(p.o.p50)}`" @click="pick(p.i)" @keydown.enter="pick(p.i)" @keydown.space.prevent="pick(p.i)">
            <circle r="30" fill="transparent" />
            <circle r="15" class="dot" />
            <text y="5" text-anchor="middle" class="num">{{ p.i + 1 }}</text>
            <g :transform="`translate(${p.tag[0]} ${p.tag[1]})`">
              <rect x="-46" y="-15" width="92" height="28" rx="14" class="tagbg" />
              <text y="4.500" text-anchor="middle" class="tagtx">{{ fmtHours(p.o.p50) }}</text>
            </g>
          </g>
        </svg>
        <span class="hint">Tap a source</span>
      </div>

      <div class="side">
        <ul class="pick" role="tablist" aria-label="Sources">
          <li v-for="p in pins" :key="p.o.id">
            <button type="button" role="tab" :aria-selected="p.i === sel" :class="{ on: p.i === sel }" @click="pick(p.i)">
              <span class="n">{{ p.i + 1 }}</span>
              <span class="nm">{{ p.o.name.split(' ').slice(0, 2).join(' ') }}</span>
              <span class="tm"><Dur :h="p.o.p50" /></span>
            </button>
          </li>
        </ul>

        <Transition name="swap" mode="out-in">
          <article :key="current.o.id" class="detail">
            <p class="kind"><IconBadge size="sm" tone="solid" :square="current.o.kind === 'centre'"><AppIcon :name="current.o.kind" :size="18" /></IconBadge>{{ current.o.kind === 'hospital' ? 'Hospital' : 'Blood centre' }} · {{ current.o.km }} km<span v-if="current.i === 0" class="fast">Fastest</span></p>
            <h3>{{ current.o.name }}</h3>
            <p class="big"><Dur :h="current.o.p50" /><small>most likely</small></p>
            <p class="range">Almost certainly between <b>{{ fmtRange(current.o.p10, current.o.p90).replace(' to ', ' and ') }}</b></p>
            <WindowBar :p10="current.o.p10" :p50="current.o.p50" :p90="current.o.p90" :limit="limit" :max="4" />
            <p class="spare"><AppIcon name="drop" :size="16" /> {{ current.o.spare }} · {{ current.o.avail }} units can be spared</p>
            <p class="verdict" :class="verdict.tone"><AppIcon :name="verdict.tone === 'ok' ? 'check' : 'warning'" :size="16" /> {{ verdict.text }}</p>
          </article>
        </Transition>

        <NuxtLink to="/results?group=B%2B&units=2&limit=3&demo=1" class="btn btn-primary go">Open this example on the map</NuxtLink>
      </div>
    </div>

    <figure class="road organic">
      <img :src="img('ambulance.jpg')" alt="An ambulance driving along a road through green hills">
      <figcaption><b>01:06</b> You pick. The supplier checks the shelf. Then the blood is on its way.</figcaption>
    </figure>
  </div>
</template>

<style scoped>
.story { display: grid; gap: 18px; }
.req { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.clock { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 99px; background: var(--ink-deep); color: #fff; font-weight: 800; font-size: 13px; letter-spacing: 0.04em; }
.grp { font-size: 34px; font-weight: 800; color: var(--blood-500); line-height: 1; }
.rt { display: flex; flex-direction: column; }
.rt b { font-size: 16px; }
.rt small { font-size: 13px; font-weight: 600; color: var(--slate); }
.body { display: grid; gap: 18px; align-items: stretch; }
.map { position: relative; overflow: hidden; border: 1.5px solid var(--primary-500); min-height: 280px; background: #fff; }
.map svg { display: block; width: 100%; height: 100%; }
.hint { position: absolute; left: 14px; bottom: 12px; padding: 5px 12px; border-radius: 99px; background: rgba(255, 255, 255, 0.92); font-size: 12px; font-weight: 800; color: var(--primary-700); box-shadow: 0 6px 14px rgba(6, 74, 68, 0.14); }
.land { stroke: #2f8f84; stroke-width: 3.6; stroke-linecap: round; fill: none; opacity: 0.72; }
.route { stroke: #d9aaa5; stroke-width: 3; stroke-dasharray: 2 9; transition: stroke 0.3s ease; }
.route.on { stroke: #0a6b62; stroke-width: 4; stroke-dasharray: 3 10; animation: flow 1s linear infinite; }
@keyframes flow { to { stroke-dashoffset: -26; } }
.pulse { fill: none; stroke: #1b1b1f; stroke-opacity: 0.5; stroke-width: 2; transform-box: fill-box; transform-origin: center; animation: ping 2.6s ease-out infinite; }
.p2 { animation-delay: 1.3s; }
@keyframes ping { from { transform: scale(1); opacity: 0.7; } to { transform: scale(2.8); opacity: 0; } }
.me { font-size: 13px; font-weight: 800; fill: #1b1b1f; paint-order: stroke; stroke: #fff; stroke-width: 4px; }
.pin { cursor: pointer; outline: none; }
.pin .dot { fill: #4a5b68; stroke: #fff; stroke-width: 3; transition: fill 0.25s ease; }
.pin .num { font-size: 15px; font-weight: 800; fill: #fff; }
.pin .tagbg { fill: #fff; stroke: #d8e4e2; stroke-width: 1.5; transition: fill 0.25s ease, stroke 0.25s ease; }
.pin .tagtx { font-size: 14px; font-weight: 800; fill: #12202b; }
.pin.on .dot { fill: #0a6b62; }
.pin.on .tagbg { fill: #0a6b62; stroke: #0a6b62; }
.pin.on .tagtx { fill: #fff; }
.pin:hover .dot, .pin:focus-visible .dot { fill: #0a6b62; }
.pin { transition: transform 0.2s ease; }
.drop { filter: drop-shadow(0 3px 4px rgba(4, 40, 38, 0.35)); }

.side { display: flex; flex-direction: column; gap: 14px; }
.pick { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.pick button { width: 100%; min-height: 64px; padding: 8px 6px; border-radius: 22px; border: 1.5px solid #d8e4e2; background: #fff; display: flex; flex-direction: column; align-items: center; gap: 2px; font: inherit; transition: all 0.25s ease; }
.pick button:hover { transform: translateY(-2px); }
.pick .n { width: 22px; height: 22px; border-radius: 99px; background: var(--slate); color: #fff; font-size: 12px; font-weight: 800; display: grid; place-items: center; }
.pick .nm { font-size: 11.5px; font-weight: 700; color: var(--slate); max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pick .tm { font-size: 15px; }
.pick button.on { background: var(--primary-50); border-color: var(--primary-500); box-shadow: 0 8px 18px rgba(10, 107, 98, 0.18); }
.pick button.on .n { background: var(--primary-500); }
.detail { padding: 18px 20px; border-radius: 26px; background: #fff; border: 1.5px solid #d8e4e2; display: flex; flex-direction: column; gap: 8px; }
.kind { margin: 0; display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: var(--slate); }
.fast { margin-left: auto; padding: 3px 10px; border-radius: 99px; background: var(--teal-50); color: var(--teal-600); font-size: 11.5px; font-weight: 800; }
.detail h3 { margin: 0; font-size: 19px; }
.big { margin: 0; display: flex; align-items: baseline; gap: 10px; font-size: 40px; font-weight: 800; color: var(--primary-600); line-height: 1; }
.big small { font-size: 13px; font-weight: 700; color: var(--slate); }
.range { margin: 0; font-size: 14px; font-weight: 500; color: #44545f; }
.spare { margin: 4px 0 0; display: flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 700; }
.spare svg { color: var(--primary-500); }
.verdict { margin: 0; display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; border-radius: 16px; font-size: 13.5px; font-weight: 700; line-height: 1.4; }
.verdict.ok { background: var(--teal-50); color: var(--teal-600); }
.verdict.warn { background: var(--amber-50); color: var(--amber-900); }
.verdict svg { flex-shrink: 0; margin-top: 2px; }
.go { min-height: 54px; }
.swap-enter-active { transition: opacity 0.3s ease, transform 0.4s cubic-bezier(0.2, 1, 0.3, 1); }
.swap-leave-active { transition: opacity 0.15s ease; }
.swap-enter-from { opacity: 0; transform: translateY(12px); }
.swap-leave-to { opacity: 0; }

.road { position: relative; margin: 0; overflow: hidden; height: 190px; background: #cfe4e1; }
.road img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: 50% 62%; filter: saturate(1.05) contrast(1.02); }
.road::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, rgba(6, 74, 68, 0.78) 0%, rgba(6, 74, 68, 0.2) 70%); }
.road figcaption { position: absolute; z-index: 1; left: 20px; right: 20px; bottom: 18px; color: #fff; font-weight: 700; font-size: 16px; line-height: 1.4; max-width: 460px; text-shadow: 0 2px 10px rgba(3, 30, 28, 0.5); }
.road figcaption b { display: inline-block; margin-right: 8px; padding: 3px 10px; border-radius: 99px; background: #fff; color: var(--primary-700); font-size: 13px; text-shadow: none; }
@media (min-width: 900px) {
  .body { grid-template-columns: 1.2fr 0.8fr; gap: 28px; }
  .map { min-height: 440px; }
  .road { height: 220px; }
  .road figcaption { font-size: 18px; left: 32px; bottom: 26px; }
}
@media (max-width: 899px) { .map { aspect-ratio: 560 / 410; min-height: 0; } }
</style>
