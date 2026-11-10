<script setup lang="ts">
import type { Option, PassReason } from '~/utils/engine'

const props = defineProps<{
  option: Option
  rank: number
  selected: boolean
  limitH: number
  /** units the request needs, for "covers 2 of 6" */
  need: number
  /** shared axis for every card's arrival bar */
  max?: number
  /** ranked first (FASTEST only when nothing is quicker) */
  first?: boolean
  fastest?: boolean
  /** what was recorded when this site was passed over: it said not on the shelf, or it did not answer in time */
  passed?: PassReason | null
}>()
defineEmits<{ select: [] }>()

const o = computed(() => props.option)
const where = computed(() => (o.value.roadKm != null ? fmtKm(o.value.roadKm) : o.value.travelHoursMap != null ? `${fmtHours(o.value.travelHoursMap)} drive` : ''))
const spare = computed(() => (o.value.partial ? `covers ${o.value.spare} of ${props.need}` : `${o.value.spare} spare`))
const chips = computed(() => o.value.flags.filter(f => f !== 'partial').map(f => ({ f, label: flagShort(f) })))
const passedChip = computed(() => (props.passed === 'confirm_timeout' ? 'No answer' : props.passed ? 'Not on shelf' : ''))
// The aria-label replaces the button's content for screen readers, so it carries everything shown.
const label = computed(() => [
  `${props.rank}. ${o.value.name}`,
  props.first && !props.passed ? (props.fastest ? 'fastest' : 'ranked first') : null,
  props.passed === 'confirm_timeout' ? 'did not answer in time' : props.passed ? 'said not on the shelf' : null,
  `most likely ${fmtHours(o.value.p50)}`,
  `8 in 10 within ${fmtRange(o.value.p10, o.value.p90)}`,
  spare.value,
  ...chips.value.map(c => flagLabel(c.f))
].filter(Boolean).join(', '))
</script>

<template>
  <button type="button" class="source" :class="{ selected, passed: !!passed }" :aria-pressed="selected" :aria-label="label" @click="$emit('select')">
    <span v-if="first && !passed" class="ribbon">{{ fastest ? 'FASTEST' : 'RANKED FIRST' }}</span>
    <span class="row">
      <span class="badge" :class="[option.kind, { on: selected }]">{{ rank }}</span>
      <span class="who">
        <strong>{{ option.name }}</strong>
        <small>{{ option.kind === 'hospital' ? 'Hospital' : 'Centre' }} · <b :class="{ part: option.partial }">{{ spare }}</b><template v-if="where"> · {{ where }}</template></small>
        <span v-if="chips.length || passed" class="flags">
          <i v-if="passedChip" class="f-passed">{{ passedChip }}</i>
          <i v-for="c in chips" :key="c.f">{{ c.label }}</i>
        </span>
      </span>
      <span class="when">
        <strong><Dur :h="option.p50" /></strong>
        <small>8 in 10: {{ fmtRange(option.p10, option.p90) }}</small>
      </span>
    </span>
    <WindowBar :p10="option.p10" :p50="option.p50" :p90="option.p90" :limit="limitH" :max="max" />
  </button>
</template>

<style scoped>
.source { position: relative; width: 100%; text-align: left; background: var(--white); border: 1.5px solid var(--line); border-radius: 28px; padding: 15px 17px 17px; display: flex; flex-direction: column; gap: 14px; transition: transform 0.2s ease, box-shadow 0.2s ease; }
.source:hover { transform: translateY(-2px); box-shadow: 0 12px 24px rgba(6, 74, 68, 0.12); }
.source.selected { border: 2px solid var(--primary-500); background: linear-gradient(180deg, #fff, var(--primary-50)); padding: 14px 16px 16px; box-shadow: 0 12px 26px rgba(10, 107, 98, 0.16); }
.source.passed:not(.selected) { opacity: 0.62; }
.ribbon { position: absolute; right: 16px; top: -11px; padding: 4px 11px; border-radius: 99px; background: var(--primary-500); color: #fff; font-size: 10.5px; font-weight: 800; letter-spacing: 0.08em; }
.row { display: flex; align-items: center; gap: 11px; }
.badge { width: 32px; height: 32px; border-radius: 99px; background: var(--slate); color: #fff; font-weight: 800; font-size: 14px; display: grid; place-items: center; flex-shrink: 0; }
.badge.centre { border-radius: 9px; }
.badge.on { background: var(--primary-500); }
.who { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.who strong { font-size: 15px; color: #12202b; }
.who small, .when small { font-size: 12px; font-weight: 600; color: #44545f; margin-top: 2px; }
.who small b { font-weight: 800; color: var(--teal-600); }
.who small b.part { color: var(--amber-700); }
.flags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.flags i { font-style: normal; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 99px; background: var(--amber-50); color: var(--amber-900); }
.flags i.f-passed { background: #eceff1; color: var(--slate); }
.when { text-align: right; display: flex; flex-direction: column; flex-shrink: 0; }
.when strong { font-size: 27px; line-height: 1; letter-spacing: -0.02em; color: var(--primary-500); }
@media (max-width: 899px) {
  .source { padding: 12px 14px 14px; gap: 10px; border-radius: 24px; }
  .source.selected { padding: 11px 13px 13px; }
  .when strong { font-size: 24px; }
  .who strong { font-size: 14.5px; }
}
</style>
