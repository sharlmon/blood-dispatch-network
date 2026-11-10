<script setup lang="ts">
// Lockups: `inline` (header) and `stacked` (hero, footer, splash).
withDefaults(defineProps<{ layout?: 'inline' | 'stacked'; size?: number; reverse?: boolean }>(), { layout: 'inline', size: 34 })
</script>

<template>
  <span class="logo" :class="[layout, { reverse }]">
    <BrandMark :size="size" :reverse="reverse" />
    <span class="word">
      <strong>Blood Dispatch</strong>
      <small>Network</small>
    </span>
  </span>
</template>

<style scoped>
.logo { display: inline-flex; align-items: center; gap: 10px; color: #1b1b1f; }
.word { display: flex; flex-direction: column; line-height: 1; }
.word strong { font-weight: 800; font-size: 15px; letter-spacing: 0.14em; text-transform: uppercase; }
.word small { margin-top: 4px; font-weight: 700; font-size: 9px; letter-spacing: 0.32em; text-transform: uppercase; color: var(--blood-500); }
.stacked { flex-direction: column; gap: 14px; text-align: center; }
.stacked .word { align-items: center; }
.stacked .word strong { font-size: clamp(18px, 3vw, 26px); }
.stacked .word small { font-size: 11px; }
@media (max-width: 440px) {
  .inline .word strong { font-size: 12.5px; letter-spacing: 0.1em; }
  .inline .word small { letter-spacing: 0.26em; }
  .inline { gap: 8px; }
}
.reverse { color: #fff; }
.reverse .word small { color: #ffd2cf; }
</style>
