<script setup lang="ts">
// The evening pre-alert list for regional centre staff (DS2): hospitals whose closing count of the
// day before showed zero for a common group. It suggests a review; a person decides on any top-up.
import type { PrealertMissing } from '~/composables/useResults'
import { eatIso, eatTime } from '~/utils/format'

useHead({ title: 'Pre-alerts · Blood Dispatch' })

const { public: { authEnabled } } = useRuntimeConfig()
const pl = usePrealertList()
onMounted(pl.load)

const list = computed(() => pl.list.value)

// The list is made offline, not yet every evening: say so when it is not from today (EAT).
const eatDay = (iso: string) => { const t = eatTime(iso.replace(/(\.\d{3})\d+/, '$1')); return t === null ? null : eatIso(t).slice(0, 10) }
const stale = computed(() => { const d = list.value ? eatDay(list.value.generated_at) : null; return !!d && d !== eatIso().slice(0, 10) })

const ORDER = ['RBC', 'WB', 'PLT', 'FFP', 'CRYO']
const productRank = (c: string) => (ORDER.includes(c) ? ORDER.indexOf(c) : ORDER.length)
const byProduct = (a: { component: string; blood_group: string }, b: { component: string; blood_group: string }) =>
  productRank(a.component) - productRank(b.component) || a.component.localeCompare(b.component) || a.blood_group.localeCompare(b.blood_group)

type Row = Pick<PrealertMissing, 'facility_id' | 'facility_name' | 'component' | 'blood_group'>
/** Rows by facility (name, else id), products in a fixed order. */
function byFacility<T extends Row>(rows: T[]) {
  const groups = new Map<string, { id: string; name: string | null; rows: T[] }>()
  for (const r of rows) {
    const g = groups.get(r.facility_id) ?? { id: r.facility_id, name: null, rows: [] }
    g.name = g.name ?? r.facility_name ?? null
    g.rows.push(r)
    groups.set(r.facility_id, g)
  }
  const label = (g: { id: string; name: string | null }) => g.name ?? g.id
  return [...groups.values()]
    .map(g => ({ ...g, rows: [...g.rows].sort(byProduct) }))
    .sort((a, b) => label(a).localeCompare(label(b), 'en', { numeric: true }))
}

const products = computed(() => [...new Set((list.value?.alerts ?? []).map(a => a.component))].sort((a, b) => productRank(a) - productRank(b) || a.localeCompare(b)))
const product = ref('all')
// A choice left over from an earlier list never hides this one.
const active = computed(() => (products.value.includes(product.value) ? product.value : 'all'))
const countOf = (c: string) => (list.value?.alerts ?? []).filter(a => a.component === c).length
const shown = computed(() => (list.value?.alerts ?? []).filter(a => active.value === 'all' || a.component === active.value))
const facilities = computed(() => byFacility(shown.value))
const unknown = computed(() => byFacility(list.value?.missing_snapshot ?? []))
const hospitalCount = computed(() => new Set((list.value?.alerts ?? []).map(a => a.facility_id)).size)
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

// What the rule looks for, from the list itself and the evaluation's settings.
const zeroOf = computed(() => {
  const rows = [...(list.value?.alerts ?? []), ...(list.value?.missing_snapshot ?? [])]
  const s = pl.evaluation.value?.settings
  const groups = [...new Set([...rows.map(r => r.blood_group), ...(s?.blood_groups ?? [])])].map(toDisplayGroup)
  const kinds = [...new Set([...rows.map(r => r.component), ...(s?.components ?? [])])].sort((a, b) => productRank(a) - productRank(b))
  if (!groups.length) return 'stock of a common blood group'
  return `${groups.join(' or ')}${kinds.length ? ` ${kinds.map(c => componentText(c).toLowerCase()).join(' or ')}` : ''}`
})

const precisionNote = computed(() => {
  const m = pl.evaluation.value?.metrics
  if (!m || m.precision === null) return 'This rule has low precision on held-out months: most alerts were not followed by a shortage.'
  const share = `${pctText(m.precision)} of alerts (${countText(m.true_positive_alert_count)} of ${countText(m.precision_denominator_alerts)})`
  return m.precision < 0.5
    ? `This rule has low precision: on held-out months only ${share} were followed by a shortage.`
    : `On held-out months ${share} were followed by a shortage.`
})

const failure = computed(() => {
  const f = pl.error.value
  if (!f) return { title: 'Pre-alerts not available', text: 'The list could not be loaded.', signIn: false }
  if (f.code === 'not_found') return { title: 'No pre-alert list yet', text: `${f.message.replace(/\.?$/, '.')} It is written by scripts/evaluate_ds2.py.`, signIn: false }
  if (f.network) return { title: 'Pre-alerts not available', text: pl.live ? 'The tool is not reachable. Try again in a moment.' : 'Could not read the list. Check the connection and try again.', signIn: false }
  if (isAuthFailure(f)) return { title: 'Sign in to see the list', text: f.message || 'Sign in and choose your organisation to see the evening list.', signIn: authEnabled }
  return { title: 'Pre-alerts not available', text: f.message || 'The list could not be loaded.', signIn: false }
})
</script>

<template>
  <div class="page">
    <header class="hero organic-card">
      <p class="kick">For regional centre staff · evening review</p>
      <h1>Evening pre-alerts</h1>
      <p class="lead">
        Hospitals whose last closing count showed zero {{ zeroOf }}. Check each one and decide whether to send a top-up
        before the night. The list suggests; a person decides.
      </p>
      <ul v-if="list" class="meta">
        <li><AppIcon name="clock" :size="16" /> List of {{ stampText(list.generated_at) }}</li>
        <li><AppIcon name="units" :size="16" /> Stock count of {{ dayText(list.stock_as_of) }}</li>
        <li v-if="list.synthetic_data"><AppIcon name="warning" :size="16" /> Synthetic starter data</li>
      </ul>
      <p v-if="list && stale" class="stale" role="note">
        <AppIcon name="warning" :size="18" />
        <span>This is the latest list ({{ stampText(list.generated_at) }}), not tonight's: lists are not yet made every evening.</span>
      </p>
    </header>

    <div v-if="pl.state.value === 'loading'" class="card box" role="status">
      <span class="spin" aria-hidden="true" />
      <b>Loading the latest evening list…</b>
    </div>

    <div v-else-if="pl.state.value === 'error' || !list" class="card box" role="alert">
      <IconBadge size="lg" tone="amber"><AppIcon name="warning" :size="26" /></IconBadge>
      <b>{{ failure.title }}</b>
      <p>{{ failure.text }}</p>
      <div class="acts">
        <button type="button" class="btn btn-primary" @click="pl.load">Try again</button>
        <NuxtLink v-if="failure.signIn" to="/sign-in" class="btn">Sign in</NuxtLink>
      </div>
    </div>

    <template v-else>
      <div class="review" role="note">
        <IconBadge tone="amber"><AppIcon name="warning" :size="22" /></IconBadge>
        <div>
          <b>Human review required</b>
          <p>
            Each alert is a known zero in the closing count of {{ dayText(list.stock_as_of) }}, not a forecast or an order.
            Stock may have changed since: check with the hospital before planning a top-up.
          </p>
          <p>{{ precisionNote }} <NuxtLink to="/evidence#prealerts">See the evidence</NuxtLink></p>
        </div>
      </div>

      <div class="bar">
        <p class="count">
          <b>{{ plural(list.alerts.length, 'alert') }}</b> at <b>{{ plural(hospitalCount, 'hospital') }}</b>
          <template v-if="unknown.length"> · <b>{{ plural(unknown.length, 'hospital') }}</b> with no count</template>
        </p>
        <div v-if="products.length > 1" class="filters" role="group" aria-label="Show alerts for">
          <button type="button" :class="{ on: active === 'all' }" :aria-pressed="active === 'all'" @click="product = 'all'">All {{ list.alerts.length }}</button>
          <button v-for="c in products" :key="c" type="button" :class="{ on: active === c }" :aria-pressed="active === c" @click="product = c">
            {{ componentText(c) }} {{ countOf(c) }}
          </button>
        </div>
      </div>

      <ul v-if="facilities.length" class="grid">
        <li v-for="(f, i) in facilities" :key="f.id" class="rise" :style="{ '--d': Math.min(i, 8) * 45 + 'ms' }">
          <PrealertFacility :facility-id="f.id" :name="f.name" :alerts="f.rows" />
        </li>
      </ul>
      <div v-else class="card empty">
        <IconBadge size="lg" tone="teal"><AppIcon name="check" :size="26" /></IconBadge>
        <b>No alerts in the list of {{ dayText(list.generated_at) }}</b>
        <p>
          No hospital had a known zero {{ zeroOf }} in the closing count of {{ dayText(list.stock_as_of) }}.
          <template v-if="list.missing_snapshot.length">The hospitals with no count are listed below.</template>
        </p>
      </div>

      <section v-if="unknown.length" class="card unknown" aria-labelledby="unknown-h">
        <h2 id="unknown-h" class="h2">No count recorded</h2>
        <p class="sub">
          These hospitals have no closing count for {{ dayText(list.stock_as_of) }}. Their stock is unknown, not zero:
          check by phone.
        </p>
        <ul class="ulist">
          <li v-for="g in unknown" :key="g.id">
            <span class="un"><b>{{ g.name ?? g.id }}</b><small v-if="g.name">{{ g.id }}</small></span>
            <span class="uchips">
              <span v-for="r in g.rows" :key="`${r.component}-${r.blood_group}`" class="uchip">
                {{ toDisplayGroup(r.blood_group) }} {{ componentText(r.component).toLowerCase() }}: unknown
              </span>
            </span>
          </li>
        </ul>
      </section>

      <section class="card assume" aria-labelledby="assume-h">
        <h2 id="assume-h" class="h2">Assumptions behind this list</h2>
        <ul v-if="list.assumptions.length"><li v-for="(a, i) in list.assumptions" :key="i">{{ a }}</li></ul>
        <p class="src">From {{ list.source }}, written by scripts/evaluate_ds2.py.</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page { width: 100%; max-width: 1120px; margin: 0 auto; padding: 14px 16px 36px; display: grid; gap: 16px; align-content: start; min-width: 0; }
.page > * { min-width: 0; }

.hero { padding: 22px 20px; background: linear-gradient(135deg, #e4f2f0 0%, #d6e8e5 100%); border: 1.5px solid var(--primary-500); }
.kick { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--primary-700); }
h1 { margin: 6px 0 0; font-size: clamp(30px, 6vw, 46px); line-height: 1; letter-spacing: -0.03em; font-weight: 800; text-transform: uppercase; color: var(--primary-600); }
.lead { margin: 10px 0 0; max-width: 640px; font-size: 15px; line-height: 1.55; font-weight: 500; color: #44545f; }
.meta { list-style: none; margin: 14px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.meta li { display: inline-flex; align-items: center; gap: 7px; padding: 7px 13px; border-radius: 99px; background: #fff; border: 1.5px solid #b9d9d4; font-size: 13px; font-weight: 800; color: var(--primary-700); }
.meta li svg { flex-shrink: 0; color: var(--primary-500); }
.stale { margin: 12px 0 0; max-width: 640px; display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; border-radius: var(--r-md); background: var(--amber-50); border: 1.5px solid var(--amber-500); color: var(--amber-900); font-size: 13.5px; font-weight: 700; line-height: 1.45; }
.stale svg { flex-shrink: 0; margin-top: 1px; color: var(--amber-700); }

.review { display: flex; align-items: flex-start; gap: 14px; padding: 16px 18px; border-radius: var(--r-lg); background: var(--amber-50); border: 2px solid var(--amber-500); color: var(--amber-900); }
.review > div { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.review b { font-size: 16px; line-height: 1.3; }
.review p { margin: 0; font-size: 13.5px; font-weight: 600; line-height: 1.5; }
.review a { color: var(--amber-900); font-weight: 800; white-space: nowrap; }

.bar { display: flex; align-items: center; justify-content: space-between; gap: 10px 16px; flex-wrap: wrap; }
.count { margin: 0; font-size: 14px; font-weight: 600; color: #44545f; }
.count b { color: var(--ink-deep); font-weight: 800; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; }
.filters button { min-height: 40px; padding: 0 16px; border-radius: 99px; border: 1.5px solid #c9dbd8; background: #fff; color: #44545f; font-size: 13px; font-weight: 800; }
.filters button.on { background: linear-gradient(180deg, #0e8277, #085a53); border-color: transparent; color: #fff; }

.grid { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }

.empty { padding: 28px 22px; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.empty b { font-size: 18px; color: var(--ink-deep); }
.empty p { margin: 0; max-width: 520px; font-size: 14px; font-weight: 600; color: #44545f; line-height: 1.5; }

.unknown, .assume { padding: 20px 16px; display: flex; flex-direction: column; gap: 10px; }
.sub { margin: 0; font-size: 14px; font-weight: 600; color: #44545f; line-height: 1.5; }
.ulist { list-style: none; margin: 4px 0 0; padding: 0; display: grid; gap: 8px; }
.ulist li { display: flex; align-items: center; justify-content: space-between; gap: 8px 14px; flex-wrap: wrap; padding: 12px 14px; border-radius: var(--r-md); background: #fff; border: 1.5px dashed #c9d6d4; }
.un { display: flex; flex-direction: column; min-width: 0; }
.un b { font-size: 14.5px; color: var(--ink-deep); overflow-wrap: anywhere; }
.un small { font-size: 12px; font-weight: 700; color: #5d6d78; }
.uchips { display: flex; flex-wrap: wrap; gap: 6px; }
.uchip { padding: 5px 11px; border-radius: 99px; background: #eceff1; color: var(--slate); font-size: 12px; font-weight: 800; }
.assume ul { margin: 0; padding-left: 20px; display: grid; gap: 8px; font-size: 14px; font-weight: 500; line-height: 1.5; color: #2c3d48; }
.src { margin: 4px 0 0; font-size: 12.5px; font-weight: 600; color: #5d6d78; }

.box { width: 100%; max-width: 480px; justify-self: center; margin-top: 12px; padding: 28px 24px; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.box b { font-size: 18px; color: var(--ink-deep); }
.box p { margin: 0; font-size: 14px; font-weight: 600; color: #44545f; line-height: 1.5; }
.acts { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 6px; }
.acts .btn { min-height: 46px; }
.spin { width: 34px; height: 34px; border-radius: 99px; border: 3px solid var(--primary-50); border-top-color: var(--primary-500); animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (min-width: 700px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 900px) {
  .page { padding: 22px 24px 48px; gap: 20px; }
  .hero { padding: 30px 36px; }
  .lead { font-size: 16px; }
  .unknown, .assume { padding: 24px 28px; }
}
@media (min-width: 1100px) { .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
</style>
