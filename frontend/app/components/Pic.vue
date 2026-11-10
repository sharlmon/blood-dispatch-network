<script setup lang="ts">
// A fast-loading photo: WebP in a few sizes (the browser picks one), lazy by default, with its
// shape reserved up front. `eager` is for the first image on screen. `small` uses the smallest
// size only (for blurred backdrops).
const props = withDefaults(defineProps<{ name: string; sizes?: string; alt?: string; eager?: boolean; small?: boolean }>(), { sizes: '100vw', alt: '', eager: false, small: false })
const img = useImg()
const set = computed(() => IMAGE_SETS[props.name] ?? { widths: [800], ratio: [3, 2] as [number, number] })
const widths = computed(() => (props.small ? [set.value.widths[0]!] : set.value.widths))
const srcset = computed(() => widths.value.map(w => `${img(`${props.name}-${w}.webp`)} ${w}w`).join(', '))
const src = computed(() => img(`${props.name}-${widths.value[Math.min(1, widths.value.length - 1)]}.webp`))
const w = computed(() => widths.value[widths.value.length - 1]!)
const h = computed(() => Math.round((w.value * set.value.ratio[1]) / set.value.ratio[0]))
</script>

<template>
  <img
    :src="src" :srcset="srcset" :sizes="sizes" :alt="alt" :width="w" :height="h"
    :loading="eager ? 'eager' : 'lazy'" decoding="async" :fetchpriority="eager ? 'high' : 'auto'"
  >
</template>
