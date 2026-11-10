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
.g { min-height: 48px; border-radius: 12px; border: 1px solid var(--line); background: var(--white); font-size: 17px; font-weight: 800; }
.g.on { background: var(--blood-500); border-color: var(--blood-500); color: #fff; }
</style>
