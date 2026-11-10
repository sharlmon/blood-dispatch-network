<script setup lang="ts">
// Arrival window on a time axis from the request (0 h) to `max` hours. The bar is the p10-p90
// range (8 in 10 arrive inside it), the dot the most likely time, the tick the clinician's limit.
// Without `max` the axis fits this window and the limit; pass one `max` to compare several bars.
const props = defineProps<{ p10: number; p50: number; p90: number; limit?: number; max?: number }>()

const scale = computed(() => props.max ?? barMax(props.p90, props.limit ?? 0))
const pct = (h: number) => Math.min(100, Math.max(0, (h / scale.value) * 100))
const warn = computed(() => props.limit !== undefined && props.p90 > props.limit)
const left = computed(() => pct(props.p10))
const width = computed(() => Math.max(1.5, pct(props.p90) - pct(props.p10)))
const cut = computed(() => props.p90 > scale.value)
const limitPos = computed(() => (props.limit !== undefined && props.limit <= scale.value ? pct(props.limit) : null))
const label = computed(() => `Most likely ${fmtHours(props.p50)}. 8 in 10 arrive within ${fmtRange(props.p10, props.p90)}.${props.limit !== undefined ? ` Your limit is ${fmtHours(props.limit)}.` : ''}`)
</script>

<template>
  <div class="track" role="img" :aria-label="label">
    <div class="range" :class="{ warn, cut }" :style="{ left: left + '%', width: width + '%' }" />
    <div v-if="limitPos !== null" class="limit" :style="{ left: limitPos + '%' }" />
    <div class="dot" :style="{ left: pct(p50) + '%' }" />
  </div>
</template>

<style scoped>
.track { position: relative; height: 8px; border-radius: 99px; background: #e2ece9; }
.range { position: absolute; top: 0; height: 8px; border-radius: 99px; background: var(--teal-600); transform-origin: left; animation: grow 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) 0.15s both; }
.range.warn { background: var(--amber-500); }
.range.cut { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.limit { position: absolute; top: -4px; width: 2px; height: 16px; margin-left: -1px; background: var(--ink); opacity: 0.5; }
.dot { position: absolute; top: -3px; width: 14px; height: 14px; margin-left: -7px; border-radius: 99px; background: var(--ink); border: 3px solid #fff; animation: pop 0.4s ease 0.6s both; }
</style>
