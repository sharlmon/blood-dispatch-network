<script setup lang="ts">
// One measured value as a bar on a 0..max scale. `tick` marks a reference value, such as the
// nominal 80%. A missing value draws an empty track, never a zero bar.
const props = withDefaults(defineProps<{ value: number | null; max: number; label: string; tone?: 'teal' | 'primary' | 'slate' | 'amber'; tick?: number | null }>(), { tone: 'teal', tick: null })

const pct = (v: number) => (props.max > 0 ? Math.min(100, Math.max(0, (v / props.max) * 100)) : 0)
</script>

<template>
  <div class="evb" role="img" :aria-label="label">
    <i v-if="value !== null" class="fill" :class="`ev-t-${tone}`" :style="{ width: pct(value) + '%' }" />
    <b v-if="tick !== null" class="tick" :style="{ left: pct(tick) + '%' }" />
  </div>
</template>

<style scoped>
.evb { position: relative; height: 12px; border-radius: 99px; background: #e2ece9; }
.fill { position: absolute; left: 0; top: 0; bottom: 0; min-width: 4px; border-radius: 99px; transform-origin: left; animation: grow 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.tick { position: absolute; top: -5px; bottom: -5px; width: 2px; margin-left: -1px; border-radius: 2px; background: var(--ink); opacity: 0.7; }
</style>
