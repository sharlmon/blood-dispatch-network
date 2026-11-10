<script setup lang="ts">
// Section 1: how close the arrival estimates came on months the model never saw.
import type { ArrivalCheck, ArrivalValidation } from '~/composables/useResults'

const props = defineProps<{ data: ArrivalValidation }>()

const test = computed(() => props.data.test)
const val = computed(() => props.data.validation)
const m = computed(() => test.value.metrics)

const errMax = computed(() => Math.max(m.value.mean_absolute_error_hours ?? 0, m.value.baseline_map_plus_2_mean_absolute_error_hours ?? 0) * 1.08)
const nominal = computed(() => m.value.nominal_interval_probability)

// p10 <= arrival <= p90 is "inside" and arrival > p90 is "after", so "before" is what is left.
const early = computed(() => {
  const inside = m.value.p10_p90_coverage, late = m.value.fraction_after_p90
  return inside === null || late === null ? null : Math.max(0, 1 - inside - late)
})
const where = computed(() => {
  const inside = m.value.p10_p90_coverage, late = m.value.fraction_after_p90
  if (inside === null || late === null || early.value === null) return null
  return [
    { key: 'early', value: early.value, tone: 'light', label: `Before p10: ${pctText(early.value)}` },
    { key: 'inside', value: inside, tone: 'teal', label: `Inside p10–p90: ${pctText(inside)}` },
    { key: 'late', value: late, tone: 'amber', label: `After p90: ${pctText(late)}` }
  ]
})

const intro = computed(() => {
  const t = test.value
  const from = t.time_origin === 'request_submission' ? 'the request' : keyText(t.time_origin).toLowerCase()
  const to = t.arrival_endpoint === 'receiving_facility' ? 'arrival at the receiving facility, not to blood ready at the bedside' : keyText(t.arrival_endpoint).toLowerCase()
  return { from, to }
})

type Row = { label: string; note?: string; text: (c: ArrivalCheck) => string }
const rows = computed<Row[]>(() => {
  const list: Row[] = [
    { label: 'Deliveries scored', text: c => countText(c.sample_count) },
    { label: 'Mean absolute error', note: 'arrival model, p50', text: c => hoursText(c.metrics.mean_absolute_error_hours) },
    { label: 'Mean absolute error', note: 'map time + 2 h', text: c => hoursText(c.metrics.baseline_map_plus_2_mean_absolute_error_hours) },
    { label: 'Median absolute error', note: 'arrival model, p50', text: c => hoursText(c.metrics.median_absolute_error_hours) },
    { label: 'Median absolute error', note: 'map time + 2 h', text: c => hoursText(c.metrics.baseline_map_plus_2_median_absolute_error_hours) },
    { label: 'Inside p10–p90', note: `nominal ${pctText(nominal.value)}`, text: c => pctText(c.metrics.p10_p90_coverage) },
    { label: 'After p90', note: 'later than the slow end', text: c => pctText(c.metrics.fraction_after_p90) },
    { label: 'Mean range width', note: 'p90 minus p10', text: c => hoursText(c.metrics.mean_interval_width_hours) }
  ]
  if (val.value.interval_sample_count !== val.value.sample_count || test.value.interval_sample_count !== test.value.sample_count) {
    list.splice(1, 0, { label: 'Deliveries with a range', note: 'the rest used the fallback estimate', text: c => countText(c.interval_sample_count) })
  }
  return list
})

const EXCLUSION_ORDER = [
  'input_transfer_rows', 'non_emergency_transfer_rows', 'emergency_transfer_rows', 'unlinked_or_ambiguous_request_rows',
  'grouped_shipments', 'collapsed_unit_rows', 'destination_mismatch_shipments', 'outside_request_window_shipments',
  'missing_or_invalid_timestamp_shipments', 'receipt_at_or_after_cutoff_shipments', 'invalid_chronology_shipments',
  'missing_or_invalid_route_shipments', 'nonfinite_derived_multiplier_shipments', 'valid_shipments'
]
const EXCLUSIONS: Record<string, string> = {
  input_transfer_rows: 'Transfer rows in the data',
  non_emergency_transfer_rows: 'Not emergency transfers',
  emergency_transfer_rows: 'Emergency transfer rows',
  unlinked_or_ambiguous_request_rows: 'No clear request to link to',
  grouped_shipments: 'Deliveries (one request, one source)',
  collapsed_unit_rows: 'Extra unit rows folded into their delivery',
  destination_mismatch_shipments: 'Sent somewhere other than the requester',
  outside_request_window_shipments: 'Requested outside this period',
  missing_or_invalid_timestamp_shipments: 'Missing or invalid times',
  receipt_at_or_after_cutoff_shipments: 'Received after the period ended',
  invalid_chronology_shipments: 'Times out of order',
  missing_or_invalid_route_shipments: 'No usable route time',
  nonfinite_derived_multiplier_shipments: 'Road time could not be derived',
  valid_shipments: 'Scored'
}
const exclusionKeys = computed(() => {
  const keys = new Set([...Object.keys(val.value.exclusions ?? {}), ...Object.keys(test.value.exclusions ?? {})])
  return [...EXCLUSION_ORDER.filter(k => keys.has(k)), ...[...keys].filter(k => !EXCLUSION_ORDER.includes(k))]
})
</script>

<template>
  <div class="eva">
    <p class="ev-p">
      Each range runs from {{ intro.from }} to {{ intro.to }}. The model was fitted on
      <b class="tnum">{{ countText(test.training_sample_count) }}</b> completed deliveries before
      <b>{{ dayText(test.trained_before) }}</b>, then frozen and scored on later months it never saw.
    </p>

    <div class="ev-grid two">
      <div class="ev-panel">
        <h3 class="ev-h3">Mean absolute error · held-out test</h3>
        <div class="err">
          <span class="nm">Arrival model<small>most likely time (p50)</small></span>
          <b class="v tnum">{{ hoursText(m.mean_absolute_error_hours) }}</b>
          <EvidenceBar class="bar" :value="m.mean_absolute_error_hours" :max="errMax" tone="primary" :label="`Arrival model: mean absolute error ${hoursText(m.mean_absolute_error_hours)}`" />
        </div>
        <div class="err">
          <span class="nm">Map time + 2 h<small>today's quote, no range</small></span>
          <b class="v tnum">{{ hoursText(m.baseline_map_plus_2_mean_absolute_error_hours) }}</b>
          <EvidenceBar class="bar" :value="m.baseline_map_plus_2_mean_absolute_error_hours" :max="errMax" tone="slate" :label="`Map time plus 2 hours: mean absolute error ${hoursText(m.baseline_map_plus_2_mean_absolute_error_hours)}`" />
        </div>
        <p class="ev-small">
          Smaller is better. Median absolute error: {{ hoursText(m.median_absolute_error_hours) }} for the model,
          {{ hoursText(m.baseline_map_plus_2_median_absolute_error_hours) }} for map time + 2 h.
        </p>
      </div>

      <div class="ev-panel">
        <h3 class="ev-h3">Where test arrivals fell · p10–p90 range</h3>
        <p class="big"><b class="tnum">{{ pctText(m.p10_p90_coverage) }}</b><span>arrived inside the range, against a nominal {{ pctText(nominal) }}</span></p>
        <template v-if="where">
          <EvidenceStack :parts="where" :ticks="[0.1, 0.9]" :label="`Test arrivals: ${where.map(p => p.label).join(', ')}.`" />
          <ul class="ev-legend">
            <li><i class="ev-t-light" /> Before p10 (the rest) {{ pctText(early) }}</li>
            <li><i class="ev-t-teal" /> Inside {{ pctText(m.p10_p90_coverage) }}</li>
            <li><i class="ev-t-amber" /> After p90 {{ pctText(m.fraction_after_p90) }}</li>
          </ul>
        </template>
        <p class="ev-small">
          The ticks mark a perfectly calibrated range: 1 in 10 before it, 1 in 10 after it.
          Mean range width {{ hoursText(m.mean_interval_width_hours) }}, over
          {{ countText(test.interval_sample_count) }} test deliveries.
        </p>
      </div>
    </div>

    <div>
      <h3 class="ev-h3">Validation and held-out test, side by side</h3>
      <div class="ev-scroll">
        <table class="ev-tbl">
          <caption>Same frozen model ({{ test.model_type }}) in both periods. A value that is not in the file shows as —.</caption>
          <thead>
            <tr>
              <th scope="col" class="ev-first">Measure</th>
              <th scope="col">Validation<small>{{ periodText(val.evaluation_period.start_inclusive, val.evaluation_period.end_exclusive) }}</small></th>
              <th scope="col">Held-out test<small>{{ periodText(test.evaluation_period.start_inclusive, test.evaluation_period.end_exclusive) }}</small></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="i">
              <th scope="row" class="ev-first">{{ r.label }}<small v-if="r.note">{{ r.note }}</small></th>
              <td>{{ r.text(val) }}</td>
              <td>{{ r.text(test) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <details class="ev-details">
      <summary>How deliveries were chosen <small>exclusions, by period</small></summary>
      <div class="ev-scroll">
        <table class="ev-tbl">
          <caption>Only completed emergency deliveries with every time recorded are scored. Nothing missing is guessed.</caption>
          <thead><tr><th scope="col" class="ev-first">Step</th><th scope="col">Validation</th><th scope="col">Test</th></tr></thead>
          <tbody>
            <tr v-for="k in exclusionKeys" :key="k">
              <th scope="row" class="ev-first">{{ keyText(k, EXCLUSIONS) }}</th>
              <td>{{ countText(val.exclusions?.[k]) }}</td>
              <td>{{ countText(test.exclusions?.[k]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
  </div>
</template>

<style scoped>
.eva { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.err { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 6px 12px; margin-bottom: 14px; }
.nm { display: flex; flex-direction: column; font-size: 14px; font-weight: 800; color: var(--ink-deep); line-height: 1.3; }
.nm small { font-size: 12px; font-weight: 600; color: #5d6d78; }
.v { font-size: 22px; font-weight: 800; color: var(--ink); line-height: 1; }
.bar { grid-column: 1 / -1; }
.big { margin: 0 0 12px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.big b { font-size: 32px; line-height: 1; font-weight: 800; color: var(--teal-600); }
.big span { font-size: 13.5px; font-weight: 600; color: #44545f; }
.ev-panel .ev-small { margin-top: 12px; }
/* Two periods side by side: fits a phone, never stretched across a desktop card. */
.eva .ev-tbl { max-width: 760px; }
@media (max-width: 599px) { .eva .ev-tbl th, .eva .ev-tbl td { padding: 9px 8px; } }
</style>
