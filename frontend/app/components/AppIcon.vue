<script setup lang="ts">
import { ICONS } from '~/utils/icons'

withDefaults(defineProps<{ name: string; size?: number }>(), { size: 22 })
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
  >
    <path :d="ICONS[name]" />
  </svg>
</template>
