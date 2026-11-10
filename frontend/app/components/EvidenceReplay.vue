<script setup lang="ts">
// Section 2: the replay ladder. Past requests replayed one by one against the previous day's stock,
// searching wider on each rung. Counts are opportunities, not patients served.
import type { PolicyName, ReplayPolicy, ReplaySummary, ResultSettings } from '~/composables/useResults'

const props = defineProps<{ data: ReplaySummary; settings: ResultSettings }>()

const RUNGS: { key: PolicyName; name: string; sub: string }[] = [
  { key: 'baseline', name: 'Today\'s centre search', sub: 'Supply centre, then the 2 nearest regional centres' },
  { key: 'all_centres', name: 'All centres', sub: 'Every regional centre' },
  { key: 'centres_and_hospitals', name: 'Centres + hospitals', sub: 'Centres, plus hospitals with stock to spare' }
]

const dl = computed(() => hoursText(props.data.deadline_hours))
const rungs = computed(() => RUNGS.map(r => ({ ...r, p: props.data.policies?.[r.key] ?? null })))

function parts(p: ReplayPolicy) {
  const within = p.full_source_p50_within_deadline
  return [
    { key: 'within', value: within, tone: 'teal', label: `Full source, p50 within ${dl.value}: ${countText(within)}` },
    { key: 'later', value: Math.max(0, p.full_source_found - within), tone: 'light', label: `Full source, p50 later: ${countText(Math.max(0, p.full_source_found - within))}` },
    { key: 'partial', value: p.partial_source_only, tone: 'amber', label: `Part of the units only: ${countText(p.partial_source_only)}` },
    { key: 'none', value: p.no_source_found, tone: 'grey', label: `No source: ${countText(p.no_source_found)}` }
  ]
}

const notFulfilled = computed(() => props.data.observed_outcomes_same_cohort?.not_fulfilled ?? null)
type Metric = { label: string; note?: string; text: (p: ReplayPolicy) => string }
const metrics = computed<Metric[]>(() => [
  { label: 'Requests evaluated', text: p => countText(p.evaluated_requests) },
  { label: 'Full source found', note: 'one site with every unit', text: p => countText(p.full_source_found) },
  { label: `Full source, p50 within ${dl.value}`, note: 'most likely time', text: p => countText(p.full_source_p50_within_deadline) },
  { label: `Full source, p90 within ${dl.value}`, note: 'slow end of the range', text: p => countText(p.full_source_p90_within_deadline) },
  { label: 'Part of the units only', text: p => countText(p.partial_source_only) },
  { label: 'No source', text: p => countText(p.no_source_found) },
  { label: 'Median p50, full sources', note: 'each column covers different requests', text: p => hoursText(p.median_p50_hours_full_sources) },
  { label: 'Hospital chosen as the source', text: p => countText(p.hospital_sources_selected) },
  {
    label: `Not fulfilled at the time, p50 within ${dl.value} here`,
    note: notFulfilled.value !== null ? `of ${countText(notFulfilled.value)} recorded as not fulfilled` : undefined,
    text: p => countText(p.previously_unfulfilled_p50_opportunities)
  },
  { label: 'Today\'s quote, median', note: 'map time + 2 h, no range', text: p => hoursText(p.median_map_plus_two_quote_hours) }
])

const PROVIDERS: Record<string, string> = {
  ReferenceCandidateProvider: 'exact group and product only',
  DS1CandidateProvider: 'DS1\'s compatibility table and spare-stock rules'
}
const provider = computed(() => PROVIDERS[props.data.candidate_provider] ?? null)

const scenarioNote = computed(() => {
  const name = props.data.candidate_provider
  if (name === 'DS1CandidateProvider') return 'Sources follow DS1\'s compatibility table and spare-stock rules (see the limitations below).'
  if (name !== 'ReferenceCandidateProvider') return `Sources come from ${name}.`
  if (props.settings.lending?.enabled === false) return 'Hospital lending is off in these settings, so no hospital lends: the third rung equals the second.'
  const reserves = Object.entries(props.settings.replay?.hospital_reserve_units ?? {})
  if (!reserves.length) return 'No hospital reserve is assumed, so no hospital lends here: the third rung equals the second.'
  const sizes = new Set(reserves.map(([, n]) => n))
  const kept = sizes.size === 1 ? `${reserves[0]?.[1]} units of the patient's group` : reserves.map(([g, n]) => `${toDisplayGroup(g)} ${n}`).join(', ')
  return `Research assumption: a hospital lends only what it holds above ${kept}, and never O−. Not an approved clinical threshold.`
})

const paired = computed(() => props.data.paired_comparison)

const OUTCOMES: Record<string, string> = { fulfilled: 'Fulfilled', partially_fulfilled: 'Partly fulfilled', not_fulfilled: 'Not fulfilled' }
const OUTCOME_TONES: Record<string, string> = { fulfilled: 'teal', partially_fulfilled: 'amber', not_fulfilled: 'grey' }
const outcomes = computed(() => {
  const o = props.data.observed_outcomes_same_cohort ?? {}
  const keys = [...Object.keys(OUTCOMES).filter(k => k in o), ...Object.keys(o).filter(k => !(k in OUTCOMES))]
  return keys.map(k => ({ key: k, value: o[k] ?? 0, tone: OUTCOME_TONES[k] ?? 'light', label: `${keyText(k, OUTCOMES)}: ${countText(o[k])}` }))
})
const observedTotal = computed(() => outcomes.value.reduce((n, o) => n + o.value, 0))
const timingLeftOut = computed(() => Object.entries(props.data.observed_timing_exclusions ?? {})
  .map(([k, n]) => `${countText(n)} ${keyText(k, { completion_at_or_after_end: 'completed after the period ended', negative_duration: 'with a negative duration' }).toLowerCase()}`))

const EXCLUSIONS: Record<string, string> = {
  outside_configured_cohort: 'Outside the cohort (other urgency or product)',
  no_shortage_in_prior_day_exact_match_snapshot: 'Own count the day before was already enough',
  missing_requester_prior_day_snapshot: 'No count at the requesting hospital the day before',
  unknown_group_requires_human_review: 'Unknown blood group (needs a person)'
}
const cohort = computed(() => {
  const c = props.data.cohort
  return [c?.urgencies?.map(u => keyText(u)).join(', '), c?.components?.map(x => `${componentText(x)} (${x})`).join(', ')].filter(Boolean).join(' · ')
})
</script>

<template>
  <div class="evr">
    <p class="ev-p">
      Past requests from <b>{{ periodText(data.period?.start_inclusive, data.period?.end_exclusive) }}</b>, each replayed against
      the closing stock counts of the day before. A request is in when the requesting hospital's own count of the patient's
      exact group was short. On each rung the replay looks for one site with every unit (a full source), searching wider each time.
    </p>
    <p class="ev-callout teal">
      <AppIcon name="units" :size="20" />
      <span><b>Counts are opportunities, not patients served.</b> Each request is replayed on its own, so the same units can count for more than one request, and no site is asked to confirm its shelf.</span>
    </p>
    <p class="scen"><AppIcon name="hospital" :size="18" /><span>{{ scenarioNote }}</span></p>

    <div class="ev-panel">
      <h3 class="ev-h3">Best single source per request · deadline {{ dl }}</h3>
      <ol class="ladder">
        <li v-for="(r, i) in rungs" :key="r.key">
          <div class="rh">
            <span class="no">{{ i + 1 }}</span>
            <span class="pn"><b>{{ r.name }}</b><small>{{ r.sub }}</small></span>
            <span v-if="r.p" class="pv"><span><b class="tnum">{{ countText(r.p.full_source_p50_within_deadline) }}</b> of {{ countText(r.p.evaluated_requests) }}</span><small>p50 within {{ dl }}</small></span>
          </div>
          <EvidenceStack v-if="r.p" :parts="parts(r.p)" :label="`${r.name}, ${countText(r.p.evaluated_requests)} requests: ${parts(r.p).map(x => x.label).join(', ')}.`" />
          <p v-else class="ev-small">Not in this file.</p>
        </li>
      </ol>
      <ul class="ev-legend">
        <li><i class="ev-t-teal" /> Full source, p50 within {{ dl }}</li>
        <li><i class="ev-t-light" /> Full source, p50 later</li>
        <li><i class="ev-t-amber" /> Part of the units only</li>
        <li><i class="ev-t-grey" /> No source</li>
      </ul>
    </div>

    <!-- Phones get one card per measure; wider screens get the table. Only one is ever displayed. -->
    <ul class="mcards">
      <li v-for="(mt, i) in metrics" :key="i">
        <p class="ml">{{ mt.label }}<small v-if="mt.note">{{ mt.note }}</small></p>
        <dl>
          <div v-for="r in rungs" :key="r.key">
            <dt>{{ r.name }}</dt>
            <dd class="tnum" :class="{ 'ev-na': !r.p || mt.text(r.p) === '—' }">{{ r.p ? mt.text(r.p) : '—' }}</dd>
          </div>
        </dl>
      </li>
    </ul>
    <div class="ev-scroll wide">
      <table class="ev-tbl ladder-tbl">
        <caption>p50 is the most likely arrival time and p90 the slow end of the estimated range. — means not in the file or not applicable.</caption>
        <thead>
          <tr>
            <th scope="col" class="ev-first">Requests</th>
            <th v-for="r in rungs" :key="r.key" scope="col">{{ r.name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(mt, i) in metrics" :key="i">
            <th scope="row" class="ev-first">{{ mt.label }}<small v-if="mt.note">{{ mt.note }}</small></th>
            <td v-for="r in rungs" :key="r.key" :class="{ 'ev-na': !r.p || mt.text(r.p) === '—' }">{{ r.p ? mt.text(r.p) : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="ev-grid two">
      <div class="ev-panel">
        <h3 class="ev-h3">Paired comparison · same requests</h3>
        <p class="big"><b class="tnum">{{ hoursText(paired?.mean_p50_hours_saved) }}</b><span>mean p50 saved by centres + hospitals</span></p>
        <p class="ev-small">
          Median {{ hoursText(paired?.median_p50_hours_saved) }}. Compared one by one on the {{ countText(paired?.requests) }} requests
          where both today's search and centres + hospitals found a full source. Saved is today's p50 minus the centres + hospitals p50:
          above zero means sooner.
        </p>
      </div>
      <div class="ev-panel">
        <h3 class="ev-h3">What was recorded for the same {{ countText(observedTotal) }} requests</h3>
        <template v-if="outcomes.length">
          <EvidenceStack :parts="outcomes" :label="`Recorded outcomes: ${outcomes.map(o => o.label).join(', ')}.`" />
          <ul class="ev-legend">
            <li v-for="o in outcomes" :key="o.key"><i :class="`ev-t-${o.tone}`" /> {{ o.label }}</li>
          </ul>
        </template>
        <p class="ev-small">
          Fully served: median {{ hoursText(data.observed_fully_served_median_bedside_hours) }} from request to blood at the bedside
          ({{ countText(data.observed_fully_served_timing_count) }} timed<template v-if="timingLeftOut.length">; left out: {{ timingLeftOut.join(', ') }}</template>).
          That is a different endpoint from predicted arrival at the facility, so the two are not directly comparable.
        </p>
      </div>
    </div>

    <details class="ev-details">
      <summary>Who is in the replay <small>cohort and exclusions</small></summary>
      <p class="ev-small cohort">
        Cohort: {{ cohort }}<template v-if="data.cohort?.definition">; {{ data.cohort.definition }}</template>.
        Sources: {{ provider ? `${provider} (${data.candidate_provider})` : data.candidate_provider }}.
      </p>
      <h3 class="ev-h3">Left out before the replay</h3>
      <EvidenceCounts :counts="data.exclusions ?? {}" :labels="EXCLUSIONS" :order="Object.keys(EXCLUSIONS)" />
    </details>
  </div>
</template>

<style scoped>
.evr { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.scen { margin: 0; display: flex; align-items: flex-start; gap: 10px; font-size: 13.5px; font-weight: 700; color: var(--ink-deep); line-height: 1.5; }
.scen svg { flex-shrink: 0; color: var(--primary-500); margin-top: 1px; }
.ladder { list-style: none; margin: 0; padding: 0; display: grid; gap: 18px; }
.rh { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
.no { width: 26px; height: 26px; border-radius: 99px; flex-shrink: 0; display: grid; place-items: center; background: var(--primary-50); color: var(--primary-700); font-size: 13px; font-weight: 800; }
.pn { flex: 1; min-width: 0; display: flex; flex-direction: column; font-size: 14.5px; line-height: 1.3; }
.pn b { color: var(--ink-deep); }
.pn small { font-size: 12px; font-weight: 600; color: #5d6d78; }
.pv { display: flex; flex-direction: column; align-items: flex-end; font-size: 13px; font-weight: 700; color: #44545f; text-align: right; white-space: nowrap; }
.pv b { font-size: 20px; line-height: 1.1; color: var(--teal-600); }
.pv small { font-size: 11.5px; font-weight: 600; color: #5d6d78; }
.ladder-tbl { min-width: 520px; }
.ladder-tbl thead th:not(.ev-first) { min-width: 96px; }
.wide { display: none; }
.mcards { list-style: none; margin: 0; padding: 0; display: grid; }
.mcards li { padding: 12px 0; border-bottom: 1px solid #e2ece9; }
.mcards li:first-child { padding-top: 0; }
.mcards li:last-child { border-bottom: 0; }
.ml { margin: 0 0 8px; display: flex; flex-direction: column; font-size: 13.5px; font-weight: 800; color: var(--ink-deep); line-height: 1.35; }
.ml small { font-size: 12px; font-weight: 600; color: #5d6d78; }
.mcards dl { margin: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.mcards dl div { display: flex; flex-direction: column-reverse; justify-content: flex-end; gap: 2px; padding: 8px 10px; border-radius: 12px; background: var(--paper); }
.mcards dt { font-size: 11px; font-weight: 700; color: #5d6d78; line-height: 1.25; }
.mcards dd { margin: 0; font-size: 16px; font-weight: 800; color: var(--ink); }
@media (min-width: 600px) {
  .wide { display: block; }
  .mcards { display: none; }
}
.big { margin: 0 0 10px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.big b { font-size: 30px; line-height: 1; font-weight: 800; color: var(--teal-600); }
.big span { font-size: 13.5px; font-weight: 600; color: #44545f; }
.ev-panel .ev-small { margin-top: 10px; }
.cohort { margin-bottom: 14px; }
</style>
