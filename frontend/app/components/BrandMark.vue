<script setup lang="ts">
// Convergence mark: four drops closing in on one point. Three red drops are the sources,
// the dark drop is your hospital. `reverse` is for dark and red backgrounds.
const props = withDefaults(defineProps<{ size?: number; reverse?: boolean }>(), { size: 32 })
const DROP = 'M32 5 C40 16 50 27 50 39 A18 18 0 0 1 14 39 C14 27 24 16 32 5 Z'
const petals = [0, 90, 180, 270].map((a, i) => ({
  a, fill: props.reverse ? '#fff' : i === 0 ? '#1b1b1f' : 'var(--blood-500)'
}))
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 64 64" role="img" aria-label="Blood Dispatch Network">
    <path
      v-for="p in petals" :key="p.a" :d="DROP" :fill="p.fill"
      :transform="`rotate(${p.a} 32 32) translate(32 35.5) scale(.41) translate(-32 -5)`"
    />
  </svg>
</template>
