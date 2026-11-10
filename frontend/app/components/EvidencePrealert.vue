<script setup lang="ts">
// Section 3: did the evening zero-stock alert come before a shortage? Precision, recall and alert
// burden are shown together, with their denominators and what was left out.
import type { PrealertEvaluation } from '~/composables/useResults'

const props = defineProps<{ data: PrealertEvaluation }>()

const m = computed(() => props.data.metrics)
const s = computed(() => props.data.settings)
const hour = computed(() => (Number.isInteger(s.value?.run_hour) ? `${String(s.value.run_hour).padStart(2, '0')}:00` : 'the set hour'))
const groups = computed(() => (s.value?.blood_groups ?? []).map(toDisplayGroup).join(' or ') || 'a checked group')
const products = computed(() => (s.value?.components ?? []).map(c => `${componentText(c).toLowerCase()} (${c})`).join(' or ') || 'a checked product')
const horizon = computed(() => hoursText(s.value?.horizon_hours).replace(/ h$/, ' hours'))

// Alerts per evaluated evening: the load a person reviewing the list would carry.
const burden = computed(() => rateText(m.value.evaluated_alert_count, m.value.evaluated_window_count))
const noisy = computed(() => m.value.precision !== null && m.value.precision < 0.5)
const plural = (n: number | null | undefined, one: string, many = `${one}s`) => `${countText(n)} ${n === 1 ? one : many}`

const DENOMINATORS: Record<string, string> = {
  scheduled_window_count: 'Evenings scheduled',
  evaluated_window_count: 'Evenings evaluated (next 24 hours fully observed)',
  known_snapshot_exposure_count: 'Hospital-product evenings with a known count',
  evaluated_alert_count: 'Alerts evaluated (precision denominator)',
  false_positive_alert_count: 'Alerts not followed by a shortage',
  evaluated_request_count: 'Matching requests evaluated',
  observed_unmet_request_count: 'Shortages among them (recall denominator)',
  missed_unmet_request_count: 'Shortages with no alert'
}
const IGNORED: Record<string, string> = {
  outside_observation_period: 'Outside the evaluation period',
  outside_configured_groups_or_components: 'Other blood group or product',
  other_urgency: 'Not emergency or urgent',
  unknown_blood_group: 'Unknown blood group',
  not_a_known_hospital: 'Not at a known hospital',
  invalid_time_or_quantity: 'Invalid time or quantity',
  missing_request_id: 'No request id',
  duplicate_request_id: 'Duplicate request id'
}
const denominators = computed(() => {
  const all = m.value as unknown as Record<string, number | null>
  return Object.fromEntries(Object.keys(DENOMINATORS).filter(k => k in all).map(k => [k, all[k] ?? null]))
})
</script>

<template>
  <div class="evq">
    <p class="ev-p">
      At <b>{{ hour }}</b> each evening, every hospital whose closing count from the day before showed zero <b>{{ groups }}</b>
      {{ products }} gets an alert. Products are checked separately, not pooled. Each alert is then checked against the next
      {{ horizon }}: did a matching emergency or urgent request at that hospital get fewer units than it asked for (a shortage)?
      Evaluated {{ periodText(data.evaluation_period?.start, data.evaluation_period?.end_exclusive) }}.
    </p>
    <p class="ev-callout">
      <AppIcon name="warning" :size="20" />
      <span>
        <b>{{ noisy ? 'A noisy review rule, not a forecast.' : 'A review rule, not a forecast.' }}</b>
        It caught {{ countText(m.detected_unmet_request_count) }} of {{ plural(m.recall_denominator_unmet_requests, 'shortage') }};
        {{ countText(m.false_positive_alert_count) }} of {{ plural(m.precision_denominator_alerts, 'alert') }} were not followed by one.
        Read precision, recall and alert burden together. The rule needs expert review before operational use.
      </span>
    </p>

    <ul class="tiles">
      <li class="ev-panel">
        <span class="tl">Precision</span>
        <b class="tnum">{{ pctText(m.precision) }}</b>
        <EvidenceBar :value="m.precision" :max="1" :label="`Precision ${pctText(m.precision)}`" />
        <small>{{ countText(m.true_positive_alert_count) }} of {{ plural(m.precision_denominator_alerts, 'alert') }} were followed by a shortage</small>
      </li>
      <li class="ev-panel">
        <span class="tl">Recall</span>
        <b class="tnum">{{ pctText(m.recall) }}</b>
        <EvidenceBar :value="m.recall" :max="1" :label="`Recall ${pctText(m.recall)}`" />
        <small>{{ countText(m.detected_unmet_request_count) }} of {{ plural(m.recall_denominator_unmet_requests, 'shortage') }} came after an alert</small>
      </li>
      <li class="ev-panel">
        <span class="tl">Alert burden</span>
        <b class="tnum">{{ burden }}</b>
        <small>alerts per evaluated evening: {{ plural(m.evaluated_alert_count, 'alert') }} over {{ plural(m.evaluated_window_count, 'evening') }}</small>
      </li>
    </ul>

    <div class="ev-grid two">
      <div class="ev-panel">
        <h3 class="ev-h3">Denominators</h3>
        <EvidenceCounts :counts="denominators" :labels="DENOMINATORS" :order="Object.keys(DENOMINATORS)" />
      </div>
      <div class="ev-panel">
        <h3 class="ev-h3">Left out, not guessed</h3>
        <ul class="out">
          <li>
            <b class="tnum">{{ plural(m.censored_window_count, 'censored evening') }}</b>: the next 24 hours were not fully observed.
            Left out: {{ plural(m.censored_alert_count, 'alert') }} and {{ plural(m.requests_excluded_censoring, 'request') }}
            ({{ plural(m.unmet_requests_excluded_censoring, 'shortage') }}).
          </li>
          <li>
            <b class="tnum">{{ plural(m.unknown_snapshot_exposure_count, 'hospital-product evening') }}</b> with no closing count:
            unknown, not zero. Left out: {{ plural(m.requests_excluded_missing_snapshot, 'request') }}
            ({{ plural(m.unmet_requests_excluded_missing_snapshot, 'shortage') }}).
          </li>
        </ul>
      </div>
    </div>

    <details v-if="Object.keys(data.ignored_requests ?? {}).length" class="ev-details">
      <summary>Requests not in the evaluation <small>other urgency, group, product or period</small></summary>
      <EvidenceCounts :counts="data.ignored_requests" :labels="IGNORED" :order="Object.keys(IGNORED)" />
    </details>
  </div>
</template>

<style scoped>
.evq { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.tiles { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(138px, 1fr)); }
.tiles li { display: flex; flex-direction: column; gap: 8px; }
.tl { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #5d6d78; }
.tiles b { font-size: 26px; line-height: 1; font-weight: 800; color: var(--teal-600); }
@media (min-width: 900px) { .tiles { gap: 12px; grid-template-columns: repeat(3, minmax(0, 1fr)); } .tiles b { font-size: 32px; } }
.tiles small { font-size: 12.5px; font-weight: 600; color: #44545f; line-height: 1.45; }
.out { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.out li { font-size: 13.5px; font-weight: 600; color: #2c3d48; line-height: 1.5; }
.out li + li { padding-top: 12px; border-top: 1px solid #e2ece9; }
.out b { color: var(--ink-deep); font-weight: 800; }
</style>
