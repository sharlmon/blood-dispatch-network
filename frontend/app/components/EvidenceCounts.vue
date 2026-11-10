<script setup lang="ts">
// Named counts from a results file (exclusions, flags, corrections), in plain words.
// Keys in `order` come first; keys the page has no label for are still shown.
const props = withDefaults(defineProps<{ counts: Record<string, number | null>; labels?: Record<string, string>; order?: string[] }>(), {
  labels: () => ({}),
  order: () => []
})

const rows = computed(() => {
  const keys = Object.keys(props.counts)
  const sorted = [...props.order.filter(k => keys.includes(k)), ...keys.filter(k => !props.order.includes(k))]
  return sorted.map(k => ({ key: k, label: keyText(k, props.labels), value: props.counts[k] ?? null }))
})
</script>

<template>
  <dl class="evc">
    <div v-for="r in rows" :key="r.key"><dt>{{ r.label }}</dt><dd class="tnum">{{ countText(r.value) }}</dd></div>
  </dl>
</template>

<style scoped>
.evc { margin: 0; display: grid; gap: 0; }
.evc div { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; padding: 9px 0; border-bottom: 1px solid #e2ece9; }
.evc div:last-child { border-bottom: 0; }
dt { font-size: 13.5px; font-weight: 600; color: #2c3d48; line-height: 1.4; min-width: 0; }
dd { margin: 0; font-size: 14px; font-weight: 800; color: var(--ink); white-space: nowrap; }
</style>
