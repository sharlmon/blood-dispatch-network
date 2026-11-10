<script setup lang="ts">
// A whole split into parts (requests by outcome, arrivals by where they fell), drawn as one bar.
// `ticks` are reference points as shares of the whole (0.1 = 10%).
const props = withDefaults(defineProps<{
  parts: { key: string; value: number; tone: string; label: string }[]
  label: string
  ticks?: number[]
}>(), { ticks: () => [] })

const shown = computed(() => props.parts.filter(p => Number.isFinite(p.value) && p.value > 0))
</script>

<template>
  <div class="evst" role="img" :aria-label="label">
    <div class="bars">
      <i v-for="p in shown" :key="p.key" :class="`ev-t-${p.tone}`" :style="{ flexGrow: p.value }" :title="p.label" />
    </div>
    <b v-for="t in ticks" :key="t" class="tick" :style="{ left: Math.min(100, Math.max(0, t * 100)) + '%' }" />
  </div>
</template>

<style scoped>
.evst { position: relative; }
.bars { display: flex; height: 22px; border-radius: 8px; overflow: hidden; background: #e2ece9; transform-origin: left; animation: grow 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.bars i { flex-basis: 0; min-width: 3px; }
.bars i + i { border-left: 2px solid #fff; }
.tick { position: absolute; top: -5px; bottom: -5px; width: 2px; margin-left: -1px; border-radius: 2px; background: var(--ink); opacity: 0.75; }
</style>
