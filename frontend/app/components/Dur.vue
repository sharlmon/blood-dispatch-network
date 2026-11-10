<script setup lang="ts">
// A duration with the digits big and the unit letters small: 1h 30m
const props = defineProps<{ h: number }>()
const parts = computed(() => fmtParts(props.h))
</script>

<template>
  <span class="dur tnum" :aria-label="fmtHours(h)"><template v-for="p in parts" :key="p.u"><b>{{ p.n }}</b><i>{{ p.u }}</i></template></span>
</template>

<style scoped>
.dur { display: inline-flex; align-items: baseline; white-space: nowrap; }
.dur b { font-weight: 800; }
.dur i { font-style: normal; font-weight: 700; font-size: 0.5em; margin: 0 0.22em 0 0.06em; opacity: 0.75; letter-spacing: 0.01em; }
.dur i:last-child { margin-right: 0; }
</style>
