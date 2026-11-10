<script setup lang="ts">
import { GROUPS } from '~/utils/mock'

const model = defineModel<string>({ required: true })
</script>

<template>
  <div class="grid" role="radiogroup" aria-label="Patient blood group">
    <button
      v-for="g in GROUPS" :key="g" type="button" role="radio" :aria-checked="model === g"
      class="g" :class="{ on: model === g }" @click="model = g"
    >{{ g }}</button>
  </div>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.g { min-height: 52px; border-radius: 14px; transition: transform 0.15s ease, background 0.2s ease; border: 1px solid var(--line); background: var(--white); font-size: 17px; font-weight: 800; }
.g:active { transform: scale(0.94); }
.g.on { box-shadow: 0 8px 18px rgba(179, 23, 30, 0.3); background: var(--blood-500); border-color: var(--blood-500); color: #fff; }
</style>
