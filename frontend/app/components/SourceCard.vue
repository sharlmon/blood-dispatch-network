<script setup lang="ts">
import type { Option } from '~/utils/mock'

const props = defineProps<{ option: Option; rank: number; selected: boolean; limitH: number }>()
defineEmits<{ select: [] }>()

const label = computed(() => `${props.rank}. ${props.option.name}, ${fmtHours(props.option.p50)} most likely`)
</script>

<template>
  <button type="button" class="source" :class="{ selected }" :aria-pressed="selected" :aria-label="label" @click="$emit('select')">
    <div class="row">
      <span class="badge" :class="[option.kind, { first: selected }]">{{ rank }}</span>
      <span class="who">
        <strong>{{ option.name }}</strong>
        <small>{{ option.kind === 'hospital' ? 'Hospital' : 'Centre' }} · {{ option.spare }} · {{ option.km }} km</small>
      </span>
      <span class="when">
        <strong class="tnum">{{ fmtHours(option.p50) }}</strong>
        <small>{{ fmtRange(option.p10, option.p90) }}</small>
      </span>
    </div>
    <WindowBar :p10="option.p10" :p50="option.p50" :p90="option.p90" :limit="limitH" :max="Math.max(4, Math.ceil(option.p90))" />
  </button>
</template>

<style scoped>
.source { width: 100%; text-align: left; background: var(--white); border: 1px solid var(--line); border-radius: 16px; padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 12px; }
.source.selected { border: 2px solid var(--blood-500); background: var(--blood-50); padding: 11px 13px 13px; }
.row { display: flex; align-items: center; gap: 10px; }
.badge { width: 28px; height: 28px; border-radius: 99px; background: var(--slate); color: #fff; font-weight: 800; font-size: 13px; display: grid; place-items: center; flex-shrink: 0; }
.badge.centre { border-radius: 8px; }
.badge.first { background: var(--blood-500); }
.who { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.who strong { font-size: 14.5px; }
.who small, .when small { font-size: 11.5px; font-weight: 600; color: var(--slate); margin-top: 1px; }
.when { text-align: right; display: flex; flex-direction: column; }
.when strong { font-size: 22px; line-height: 1; }
</style>
