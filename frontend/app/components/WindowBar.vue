<script setup lang="ts">
const props = withDefaults(defineProps<{ p10: number; p50: number; p90: number; limit?: number; max?: number }>(), { max: 4 })

const warn = computed(() => props.limit !== undefined && props.p90 > props.limit)
const left = computed(() => (props.p10 / props.max) * 100)
const width = computed(() => ((Math.min(props.p90, props.max) - props.p10) / props.max) * 100)
const dot = computed(() => (Math.min(props.p50, props.max) / props.max) * 100)
const limitPos = computed(() => (props.limit !== undefined ? (props.limit / props.max) * 100 : null))
</script>

<template>
  <div class="track" role="img" :aria-label="`Arrival window ${p10} to ${p90} hours, most likely ${p50}`">
    <div class="range" :class="{ warn }" :style="{ left: left + '%', width: width + '%' }" />
    <div v-if="limitPos !== null" class="limit" :style="{ left: limitPos + '%' }" />
    <div class="dot" :style="{ left: dot + '%' }" />
  </div>
</template>

<style scoped>
.track { position: relative; height: 8px; border-radius: 99px; background: var(--fog); }
.range { position: absolute; top: 0; height: 8px; border-radius: 99px; background: var(--teal-600); }
.range.warn { background: var(--amber-500); }
.limit { position: absolute; top: -4px; width: 2px; height: 16px; background: var(--ink); opacity: 0.5; }
.dot { position: absolute; top: -3px; width: 14px; height: 14px; margin-left: -7px; border-radius: 99px; background: var(--ink); border: 3px solid #fff; }
</style>
