<script setup lang="ts">
// Adds `.in` when scrolled into view so charts can animate. Visible without JS.
const el = ref<HTMLElement | null>(null)
onMounted(() => {
  const node = el.value
  if (!node) return
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return
  node.classList.add('armed')
  const io = new IntersectionObserver(([e]) => {
    if (e?.isIntersecting) { node.classList.add('in'); io.disconnect() }
  }, { threshold: 0.25 })
  io.observe(node)
  onBeforeUnmount(() => io.disconnect())
})
</script>

<template><div ref="el" class="reveal"><slot /></div></template>

<style>
.reveal .grow { transform-origin: left; transition: transform 1.1s cubic-bezier(0.2, 0.8, 0.2, 1); }
.reveal.armed:not(.in) .grow { transform: scaleX(0); }
</style>
