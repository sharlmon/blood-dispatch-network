<script setup lang="ts">
// The base of the landing hero: a soft teal wave that settles into the dark band below.
</script>

<template>
  <svg class="horizon" viewBox="0 0 1440 160" preserveAspectRatio="none" aria-hidden="true">
    <path d="M0 70C220 20 420 110 700 70S1160 20 1440 66V160H0Z" fill="#0a6b62" opacity="0.22" />
    <path d="M0 100C260 58 480 128 760 96S1180 62 1440 98V160H0Z" fill="#0a6b62" opacity="0.5" />
    <path d="M0 128C300 100 520 150 800 128S1200 108 1440 130V160H0Z" fill="#0c2b33" />
  </svg>
</template>

<style scoped>
.horizon { display: block; width: 100%; height: clamp(90px, 9vw, 150px); }
</style>
