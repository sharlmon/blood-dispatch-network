<script setup lang="ts">
// One frame for every icon in the product: a round badge. Sizes 36 / 44 / 52, tones soft / solid / teal / amber.
// Functional UI puts a stroke icon (AppIcon) inside; marketing tiles may put an illustration (ServiceIcon).
withDefaults(defineProps<{ size?: 'sm' | 'md' | 'lg'; tone?: 'soft' | 'solid' | 'teal' | 'amber'; square?: boolean }>(), { size: 'md', tone: 'soft' })
</script>

<template>
  <span class="ib" :class="[`s-${size}`, `t-${tone}`, { sq: square }]" aria-hidden="true"><slot /></span>
</template>

<style scoped>
.ib { flex-shrink: 0; display: grid; place-items: center; border-radius: var(--r-pill); }
.s-sm { width: 36px; height: 36px; } .s-md { width: 44px; height: 44px; } .s-lg { width: 52px; height: 52px; }
.sq { border-radius: 14px; }
.t-soft { background: radial-gradient(circle at 30% 25%, #fff, #f6d3ce); color: var(--blood-500); }
.t-solid { background: var(--blood-500); color: #fff; }
.t-teal { background: var(--teal-50); color: var(--teal-600); }
.t-amber { background: var(--amber-50); color: var(--amber-700); }
</style>
