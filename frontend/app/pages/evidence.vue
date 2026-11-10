<script setup lang="ts">
// Evidence for expert reviewers, read from DS2's committed results files. Public: the files are
// aggregate and synthetic, with no personal fields.
import type { ResultEnvelope, ResultName } from '~/composables/useResults'

useHead({ title: 'Evidence · Blood Dispatch' })

const route = useRoute()
const router = useRouter()
const ev = useEvidence()

const asked = () => (typeof route.query.scenario === 'string' && route.query.scenario ? route.query.scenario : null)

async function load() {
  const wanted = asked()
  await ev.load(wanted)
  // A scenario that does not exist falls back to the default; say so in the address too.
  if (wanted && ev.state.value === 'ready' && ev.scenario.value !== wanted) router.replace({ query: { ...route.query, scenario: undefined }, hash: route.hash })
  // The sections only exist now, so a link to one of them (/evidence#replay) is followed here.
  if (ev.state.value === 'ready' && route.hash) {
    await nextTick()
    document.getElementById(decodeURIComponent(route.hash.slice(1)))?.scrollIntoView()
  }
}
onMounted(load)

// Back/Forward only change the query, and Nuxt keeps this page mounted: follow the address.
watch(() => route.query.scenario, () => {
  if (ev.state.value !== 'ready') return
  const s = asked()
  const want = s && ev.scenarios.value.includes(s) ? s : null
  if (want !== ev.scenario.value) ev.showScenario(want)
})

const options = computed(() => [null, ...ev.scenarios.value])
function choose(s: string | null) {
  if (s === ev.scenario.value && ev.replayState.value === 'ready') return
  ev.showScenario(s)
  // Dropping an anchor from the address scrolls to the top, so keep one: the replay section, where
  // this switch is. With no anchor the page stays where it is.
  router.replace({ query: { ...route.query, scenario: s ?? undefined }, hash: route.hash ? '#replay' : undefined })
}

const TOC = [
  { id: 'arrival', label: 'Arrival ranges' },
  { id: 'replay', label: 'Replay ladder' },
  { id: 'prealerts', label: 'Evening alerts' },
  { id: 'limits', label: 'Assumptions' },
  { id: 'provenance', label: 'Provenance' }
]

const synthetic = computed(() => [ev.arrival.value, ev.replay.value, ev.prealert.value, ev.quality.value].every(e => !e || e.synthetic_data !== false))
const test = computed(() => ev.arrival.value?.result?.test ?? null)
const replay = computed(() => ev.replay.value?.result ?? null)
const pre = computed(() => ev.prealert.value?.result?.metrics ?? null)
const replayFile = computed(() => `${ev.replayScenario.value ? `${ev.replayScenario.value}/` : ''}replay_summary.json`)

const glance = computed(() => {
  const t = test.value?.metrics
  const r = replay.value
  const base = r?.policies?.baseline
  const wide = r?.policies?.centres_and_hospitals
  const p = pre.value
  const burden = rateText(p?.evaluated_alert_count, p?.evaluated_window_count)
  return [
    { to: 'arrival', big: hoursText(t?.mean_absolute_error_hours), label: 'Mean arrival error, held-out test', sub: `Map time + 2 h: ${hoursText(t?.baseline_map_plus_2_mean_absolute_error_hours)}` },
    { to: 'arrival', big: pctText(t?.p10_p90_coverage), label: 'Test arrivals inside p10–p90', sub: `An estimated ${pctText(t?.nominal_interval_probability, 0)} interval, over ${countText(test.value?.interval_sample_count)} deliveries` },
    {
      to: 'replay',
      big: `${countText(base?.full_source_p50_within_deadline)} → ${countText(wide?.full_source_p50_within_deadline)}`,
      label: `Requests with a full source, p50 within ${hoursText(r?.deadline_hours)}`,
      sub: `Today's search → centres + hospitals, of ${countText(base?.evaluated_requests)} · ${scenarioLabel(ev.replayScenario.value)}`
    },
    { to: 'prealerts', big: pctText(p?.precision), label: 'Evening alert precision', sub: `Recall ${pctText(p?.recall)} · ${burden} alerts per evening` }
  ]
})

function why(name: ResultName): string {
  const f = ev.missing.value[name]
  const msg = f?.network ? 'The results service is not reachable.' : f?.message || 'This results file could not be read.'
  return `${msg.replace(/\.?$/, '.')} It is written by scripts/evaluate_ds2.py.`
}

const unique = (xs: string[]) => [...new Set(xs)]
const notes = computed(() => {
  const out: { title: string; file: string; assumptions: string[]; limitations: string[] }[] = []
  const a = ev.arrival.value?.result
  if (a) out.push({ title: 'Arrival ranges', file: 'arrival_validation.json', assumptions: [], limitations: unique([...(a.test?.limitations ?? []), ...(a.validation?.limitations ?? [])]) })
  const r = replay.value
  if (r) out.push({ title: `Replay ladder · ${scenarioLabel(ev.replayScenario.value)}`, file: replayFile.value, assumptions: r.assumptions ?? [], limitations: r.limitations ?? [] })
  const p = ev.prealert.value?.result
  if (p) out.push({ title: 'Evening pre-alerts', file: 'prealert_evaluation.json', assumptions: p.assumptions ?? [], limitations: p.limitations ?? [] })
  const q = ev.quality.value?.result
  if (q) out.push({ title: 'Data cleaning', file: 'data_quality.json', assumptions: [], limitations: isCleaningReport(q) ? q.limitations ?? [] : [q.reason] })
  return out
})

const provFiles = computed(() => {
  const out: { title: string; env: ResultEnvelope<unknown> }[] = []
  if (ev.arrival.value) out.push({ title: 'arrival_validation.json', env: ev.arrival.value })
  if (ev.replay.value) out.push({ title: replayFile.value, env: ev.replay.value })
  if (ev.prealert.value) out.push({ title: 'prealert_evaluation.json', env: ev.prealert.value })
  if (ev.quality.value) out.push({ title: 'data_quality.json', env: ev.quality.value })
  return out
})

const errorText = computed(() => {
  const f = ev.error.value
  if (f?.network) return ev.live ? 'The results service is not reachable. Try again in a moment.' : 'Could not read the results files. Check the connection and try again.'
  return f?.message || 'The results files could not be read.'
})
</script>

<template>
  <div class="page">
    <header class="hero organic-card">
      <p class="kick">For expert reviewers</p>
      <h1>Evidence</h1>
      <p class="lead">
        How well the arrival ranges, a replay of past emergencies and the evening alert held up on held-out months.
        Every number comes from the committed results files.
      </p>
      <ul class="frame" aria-label="How to read these results">
        <li :class="{ warn: !synthetic }"><AppIcon name="warning" :size="18" /><span>{{ synthetic ? 'Synthetic starter data.' : 'Not every file is marked synthetic. Check the provenance.' }}</span></li>
        <li><AppIcon name="units" :size="18" /><span>Counts are opportunities, not patients served.</span></li>
        <li><AppIcon name="window" :size="18" /><span>p10–p90 is an estimated 80% interval.</span></li>
      </ul>
    </header>

    <div v-if="ev.state.value === 'loading'" class="card box" role="status">
      <span class="spin" aria-hidden="true" />
      <b>Loading the results files…</b>
      <p>Arrival validation, the replay ladder and the evening alert evaluation.</p>
    </div>

    <div v-else-if="ev.state.value === 'error'" class="card box" role="alert">
      <IconBadge size="lg" tone="amber"><AppIcon name="warning" :size="26" /></IconBadge>
      <b>Results not available</b>
      <p>{{ errorText }}</p>
      <div class="acts"><button type="button" class="btn btn-primary" @click="load">Try again</button></div>
    </div>

    <template v-else>
      <nav class="toc" aria-label="On this page">
        <!-- Same-page jumps: never announced as the current page. -->
        <NuxtLink v-for="t in TOC" :key="t.id" :to="{ query: route.query, hash: `#${t.id}` }" aria-current-value="false">{{ t.label }}</NuxtLink>
      </nav>

      <section class="glance" aria-labelledby="glance-h">
        <h2 id="glance-h">At a glance</h2>
        <ul>
          <li v-for="(g, i) in glance" :key="i" class="rise" :style="{ '--d': i * 70 + 'ms' }">
            <NuxtLink :to="{ query: route.query, hash: `#${g.to}` }" aria-current-value="false">
              <strong class="tnum">{{ g.big }}</strong>
              <span>{{ g.label }}</span>
              <small>{{ g.sub }}</small>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <EvidenceSection id="arrival" :n="1" icon="window" kicker="Arrival ranges" title="How close the arrival estimates came" source="arrival_validation.json">
        <EvidenceArrival v-if="ev.arrival.value" :data="ev.arrival.value.result" />
        <p v-else class="gone">{{ why('arrival_validation') }}</p>
      </EvidenceSection>

      <EvidenceSection id="replay" :n="2" icon="route" kicker="Replay ladder" title="Would a wider search have found blood in time?" :source="replayFile">
        <div v-if="options.length > 1" class="switch" role="group" aria-label="Hospital reserve scenario">
          <button
            v-for="s in options" :key="s ?? 'default'" type="button" :class="{ on: ev.scenario.value === s }"
            :aria-pressed="ev.scenario.value === s" @click="choose(s)"
          >
            {{ scenarioLabel(s) }}
          </button>
        </div>
        <div class="replay" :class="{ busy: ev.replayState.value === 'loading' }" :aria-busy="ev.replayState.value === 'loading'">
          <p v-if="ev.replayState.value === 'loading'" class="wait" role="status"><span class="spin sm" aria-hidden="true" /> Loading {{ scenarioLabel(ev.scenario.value) }}…</p>
          <EvidenceReplay v-if="ev.replay.value" :data="ev.replay.value.result" :settings="ev.replay.value.settings ?? {}" />
          <p v-else-if="ev.replayState.value === 'error'" class="gone">
            {{ why('replay_summary') }}
            <button type="button" class="retry" @click="choose(ev.scenario.value)">Try again</button>
          </p>
        </div>
      </EvidenceSection>

      <EvidenceSection id="prealerts" :n="3" icon="bell" kicker="Evening pre-alerts" title="Did the evening alert come before a shortage?" source="prealert_evaluation.json">
        <EvidencePrealert v-if="ev.prealert.value" :data="ev.prealert.value.result" />
        <p v-else class="gone">{{ why('prealert_evaluation') }}</p>
        <NuxtLink to="/prealerts" class="more">See the latest evening list <AppIcon name="back" class="fwd" :size="16" /></NuxtLink>
      </EvidenceSection>

      <EvidenceSection id="limits" :n="4" icon="warning" kicker="Assumptions and limitations" title="What these results assume, and cannot show">
        <p class="ev-p">Quoted word for word from each results file.</p>
        <div class="notes">
          <article v-for="g in notes" :key="g.file" class="ev-panel">
            <h3 class="nt">{{ g.title }} <code>{{ g.file }}</code></h3>
            <template v-if="g.assumptions.length">
              <h4 class="ev-h3">Assumptions</h4>
              <ul class="ev-list"><li v-for="(a, i) in g.assumptions" :key="i">{{ a }}</li></ul>
            </template>
            <template v-if="g.limitations.length">
              <h4 class="ev-h3">Limitations</h4>
              <ul class="ev-list"><li v-for="(a, i) in g.limitations" :key="i">{{ a }}</li></ul>
            </template>
          </article>
        </div>
      </EvidenceSection>

      <EvidenceSection id="provenance" :n="5" icon="audit" kicker="Provenance" title="Where the numbers come from">
        <EvidenceProvenance :files="provFiles" :quality="ev.quality.value?.result ?? null" :provider="replay?.candidate_provider ?? null" :live="ev.live" />
      </EvidenceSection>
    </template>
  </div>
</template>

<style scoped>
.page { width: 100%; max-width: 1120px; margin: 0 auto; padding: 14px 16px 36px; display: grid; gap: 16px; align-content: start; min-width: 0; }
.page > * { min-width: 0; }

.hero { padding: 22px 20px; background: linear-gradient(135deg, #e4f2f0 0%, #d6e8e5 100%); border: 1.5px solid var(--primary-500); }
.kick { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--primary-700); }
h1 { margin: 6px 0 0; font-size: clamp(32px, 6vw, 48px); line-height: 1; letter-spacing: -0.03em; font-weight: 800; text-transform: uppercase; color: var(--primary-600); }
.lead { margin: 10px 0 0; max-width: 640px; font-size: 15px; line-height: 1.55; font-weight: 500; color: #44545f; }
.frame { list-style: none; margin: 16px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.frame li { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; padding: 8px 14px 8px 10px; border-radius: 22px; background: #fff; border: 1.5px solid #b9d9d4; font-size: 13px; font-weight: 800; color: var(--primary-700); line-height: 1.3; }
.frame li svg { flex-shrink: 0; color: var(--primary-500); }
.frame li.warn { background: var(--amber-50); border-color: var(--amber-500); color: var(--amber-900); }
.frame li.warn svg { color: var(--amber-700); }

/* Phones: one row of chips that scrolls inside itself; wider screens wrap. */
.toc { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; margin: 0 -16px; padding: 2px 16px; }
.toc::-webkit-scrollbar { display: none; }
.toc a { flex-shrink: 0; display: inline-flex; align-items: center; min-height: 40px; padding: 0 16px; border-radius: 99px; border: 1.5px solid #b9d9d4; background: #fff; color: var(--primary-700); font-size: 13px; font-weight: 800; text-decoration: none; white-space: nowrap; transition: background 0.2s ease, transform 0.2s ease; }
.toc a:hover { background: var(--primary-50); transform: translateY(-1px); }

.glance { padding: 20px 14px; border-radius: 30px 38px 32px 40px / 36px 30px 40px 32px; background: linear-gradient(180deg, var(--ink-deep), #071c22); color: #fff; box-shadow: var(--sh-1); }
.glance h2 { margin: 0 0 12px 6px; font-size: 12px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #9fd6cd; }
.glance ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
/* Phones: the number on the left, what it means on the right. */
.glance a { display: grid; grid-template-columns: 116px minmax(0, 1fr); align-items: center; gap: 2px 12px; height: 100%; padding: 12px 14px; border-radius: 20px; background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(159, 214, 205, 0.22); color: inherit; text-decoration: none; transition: background 0.2s ease, transform 0.2s ease; }
.glance a:hover { background: rgba(255, 255, 255, 0.11); transform: translateY(-2px); }
.glance strong { grid-row: span 2; font-size: 22px; line-height: 1.05; font-weight: 800; letter-spacing: -0.02em; color: #7fd6c9; white-space: nowrap; }
.glance span { font-size: 13px; font-weight: 700; line-height: 1.35; color: #e6f2f0; }
.glance small { font-size: 12px; font-weight: 600; line-height: 1.4; color: #a9c3bf; }
@media (min-width: 600px) {
  .toc { flex-wrap: wrap; overflow: visible; margin: 0; padding: 0; }
  .glance ul { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .glance a { display: flex; flex-direction: column; gap: 5px; padding: 14px; }
  .glance strong { font-size: 28px; }
}

.switch { display: flex; flex-wrap: wrap; gap: 8px; }
.switch button { min-height: 44px; padding: 0 16px; border-radius: 99px; border: 1.5px solid #c9dbd8; background: #fff; color: #44545f; font-size: 13.5px; font-weight: 800; transition: background 0.2s ease, transform 0.15s ease; }
.switch button:hover { border-color: var(--primary-500); color: var(--primary-700); }
.switch button.on { background: linear-gradient(180deg, #0e8277, #085a53); border-color: transparent; color: #fff; box-shadow: 0 8px 18px rgba(10, 107, 98, 0.24); }
.replay { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.replay.busy :deep(.evr) { opacity: 0.45; pointer-events: none; transition: opacity 0.2s ease; }
.wait { margin: 0; display: flex; align-items: center; gap: 10px; font-size: 13.5px; font-weight: 700; color: var(--primary-700); }
.gone { margin: 0; padding: 14px 16px; border-radius: var(--r-lg); background: #fff; border: 1.5px dashed #d8e4e2; font-size: 13.5px; font-weight: 600; color: #44545f; line-height: 1.5; }
.retry { border: 0; background: none; padding: 0; margin-left: 4px; font: inherit; font-weight: 800; color: var(--primary-700); text-decoration: underline; }
.more { align-self: flex-start; display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 18px; border-radius: 99px; border: 1.5px solid #b9d9d4; background: var(--primary-50); color: var(--primary-700); font-size: 14px; font-weight: 800; text-decoration: none; }
.fwd { transform: rotate(180deg); }

.notes { display: grid; gap: 14px; }
.nt { margin: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; font-size: 16px; font-weight: 800; color: var(--ink-deep); }
.nt code { padding: 3px 9px; border-radius: 99px; background: var(--primary-50); color: var(--primary-700); font-size: 12px; font-weight: 700; overflow-wrap: anywhere; }
.notes .ev-h3 { margin-top: 16px; }

.box { width: 100%; max-width: 480px; justify-self: center; margin-top: 12px; padding: 28px 24px; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.box b { font-size: 18px; color: var(--ink-deep); }
.box p { margin: 0; font-size: 14px; font-weight: 600; color: #44545f; line-height: 1.5; }
.acts { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 6px; }
.acts .btn { min-height: 46px; }
.spin { width: 34px; height: 34px; border-radius: 99px; border: 3px solid var(--primary-50); border-top-color: var(--primary-500); animation: spin 0.9s linear infinite; }
.spin.sm { width: 18px; height: 18px; border-width: 2.5px; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (min-width: 900px) {
  .page { padding: 22px 24px 48px; gap: 20px; }
  .hero { padding: 30px 36px; }
  .lead { font-size: 16px; }
  .glance { padding: 24px 26px; }
  .glance ul { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
  .glance strong { font-size: 32px; }
  .notes { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: start; }
}
</style>
