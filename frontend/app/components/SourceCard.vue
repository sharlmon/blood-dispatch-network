<script setup lang="ts">
import type { Option } from '~/utils/mock'

const props = defineProps<{ option: Option; rank: number; selected: boolean; limitH: number; fastest?: boolean }>()
defineEmits<{ select: [] }>()

const label = computed(() => `${props.rank}. ${props.option.name}, ${fmtHours(props.option.p50)} most likely`)
</script>

<template>
  <button type="button" class="source" :class="{ selected }" :aria-pressed="selected" :aria-label="label" @click="$emit('select')">
    <span v-if="fastest" class="ribbon">FASTEST</span>
    <span class="row">
      <span class="badge" :class="[option.kind, { first: selected }]">{{ rank }}</span>
      <span class="who">
        <strong>{{ option.name }}</strong>
        <small>{{ option.kind === 'hospital' ? 'Hospital' : 'Centre' }} · {{ option.spare }} · {{ option.km }} km</small>
      </span>
      <span class="when">
        <strong class="tnum">{{ fmtHours(option.p50) }}</strong>
        <small>{{ fmtRange(option.p10, option.p90) }}</small>
      </span>
    </span>
    <WindowBar :p10="option.p10" :p50="option.p50" :p90="option.p90" :limit="limitH" :max="Math.max(4, Math.ceil(option.p90))" />
  </button>
</template>

<style scoped>
.source { position: relative; width: 100%; text-align: left; background: var(--white); border: 1.5px solid var(--line); border-radius: 28px; padding: 15px 17px 17px; display: flex; flex-direction: column; gap: 14px; transition: transform 0.2s ease, box-shadow 0.2s ease; }
.source:hover { transform: translateY(-2px); box-shadow: 0 12px 24px rgba(126, 16, 21, 0.12); }
.source.selected { border: 2px solid var(--blood-500); background: linear-gradient(180deg, #fff, var(--blood-50)); padding: 14px 16px 16px; box-shadow: 0 12px 26px rgba(179, 23, 30, 0.16); }
.ribbon { position: absolute; right: 16px; top: -11px; padding: 4px 11px; border-radius: 99px; background: var(--blood-500); color: #fff; font-size: 10.5px; font-weight: 800; letter-spacing: 0.08em; }
.row { display: flex; align-items: center; gap: 11px; }
.badge { width: 32px; height: 32px; border-radius: 99px; background: var(--slate); color: #fff; font-weight: 800; font-size: 14px; display: grid; place-items: center; flex-shrink: 0; }
.badge.centre { border-radius: 9px; }
.badge.first { background: var(--blood-500); }
.who { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.who strong { font-size: 15px; color: #12202b; }
.who small, .when small { font-size: 12px; font-weight: 600; color: #5a3c3f; margin-top: 2px; }
.when { text-align: right; display: flex; flex-direction: column; }
.when strong { font-size: 27px; line-height: 1; letter-spacing: -0.02em; color: var(--blood-500); }
@media (max-width: 899px) {
  .source { padding: 12px 14px 14px; gap: 10px; border-radius: 24px; }
  .source.selected { padding: 11px 13px 13px; }
  .when strong { font-size: 24px; }
  .who strong { font-size: 14.5px; }
}
</style>
