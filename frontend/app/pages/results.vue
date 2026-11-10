<script setup lang="ts">
useHead({ title: 'Results · Blood Dispatch' })

const route = useRoute()
const d = useDispatch()
const { public: { authEnabled } } = useRuntimeConfig()

// API calls run on the client: the server renders the loading state, the browser restores the request.
const view = ref<'loading' | 'ready' | 'error'>(d.matches(route.query) ? 'ready' : 'loading')
async function load() {
  if (!d.matches(route.query)) view.value = 'loading'
  const r = await d.loadFromQuery(route.query)
  if (r === 'empty') return navigateTo({ path: '/request', query: { need: 'results' } }, { replace: true })
  view.value = r === 'ok' ? 'ready' : 'error'
}
onMounted(load)
watch(() => route.query, (q) => { if (!d.matches(q)) load() })

const req = computed(() => d.request.value)
const rk = computed(() => d.ranking.value)
const opts = computed(() => d.options.value)
const limit = computed(() => d.limitH.value)
const need = computed(() => req.value?.units ?? 1)
const unknownGroup = computed(() => req.value?.group === 'Unknown')

const filter = ref<'all' | 'hospital' | 'centre'>('all')
const shown = computed(() => opts.value.filter(o => filter.value === 'all' || o.kind === filter.value))
const count = (k: 'hospital' | 'centre') => opts.value.filter(o => o.kind === k).length
const axis = computed(() => barMax(limit.value, ...opts.value.map(o => o.p90)))
const fastest = computed(() => { const t = opts.value[0]; return !!t && opts.value.every(o => o.p50 >= t.p50) })
const short = (name: string) => name.split(' ').slice(0, 2).join(' ')

const baselineLine = computed(() => {
  const b = d.baseline.value
  if (!b) return ''
  return b.facility_id && b.quote_hours != null ? `Today's way: ${b.name}, about ${fmtHours(b.quote_hours)}, no range.` : 'Today\'s way: no regional centre has enough stock.'
})
const mapLine = computed(() => {
  const n = opts.value.length
  return `${n} ${n === 1 ? 'source' : 'sources'} ${d.noFullSource.value ? 'can cover part of this' : d.tooLong.value ? 'available' : 'can cover this'}`
})
const pickedName = computed(() => d.record.value?.selected_name ?? opts.value.find(o => o.id === d.pickedId.value)?.name ?? null)
const decided = computed(() => d.decision.value === 'groupO' ? 'Emergency group O recorded.' : d.decision.value === 'transfer' ? 'Patient transfer recorded.' : '')

// What the main button does depends on where the request is.
const cta = computed(() => {
  const s = d.status.value
  const o = d.selected.value
  if (s === 'cancelled' || s === 'arrived') return { kind: 'closed' as const, label: s === 'arrived' ? 'Units arrived. Start a new request' : 'Request cancelled. Start a new request' }
  if (s === 'confirmed' || s === 'dispatched' || (s === 'awaiting_shelf' && o?.id === d.pickedId.value)) return { kind: 'track' as const, label: `Track: ${statusLabel(s).toLowerCase()}` }
  if (!o) return { kind: 'none' as const, label: 'Pick a source' }
  let label = `${s === 'awaiting_shelf' ? 'Switch to' : 'Request from'} ${short(o.name)}`
  if (o.partial) label += ` (covers ${o.spare} of ${need.value})`
  if (d.tooLong.value) label += ' anyway'
  return { kind: 'pick' as const, label }
})
const busy = computed(() => d.busy.value !== null)

const authFail = computed(() => !!d.error.value && isAuthFailure(d.error.value))
const errorText = computed(() => {
  const f = d.error.value
  if (!f) return 'Could not load this request.'
  if (f.network) return 'Tool not reachable. Use the phone process: call the blood centre directly.'
  if (f.code === 'engine_unavailable') return `Ranking engine not available: ${f.message.replace(/\.+$/, '')}. Use the phone process: call the blood centre directly.`
  if (authFail.value) return f.message || 'Sign in and choose your hospital to see live sources.'
  return f.message || 'Could not load this request.'
})
</script>

<template>
  <div v-if="view === 'ready' && req && rk" class="results">
    <h1 class="sr-only">Sources for your blood request</h1>
    <div class="map"><SourceMap :options="opts" :selected-id="d.selectedId.value" :pad-top="70" :pad-bottom="40" panels @select="d.select" /></div>

    <span class="mapchip">{{ mapLine }}</span>

    <section class="panel">
      <div class="grab" aria-hidden="true" />

      <div class="sum" aria-label="Your request">
        <span class="grp">{{ unknownGroup ? 'O' : req.group }}</span>
        <span class="meta">
          <b>{{ req.units }} {{ req.units === 1 ? 'unit' : 'units' }} · red cells</b>
          <small v-if="d.sooner.value > 0.2" class="soon">{{ fmtHours(d.sooner.value) }} sooner than the current way</small>
          <small v-if="unknownGroup">Patient group unknown · group O only · limit {{ fmtHours(limit) }}</small>
          <small v-else>{{ req.id ?? (d.live ? 'Preview, not saved' : 'Demo') }} · {{ eatClock(req.requestedAt) }} · limit {{ fmtHours(limit) }}</small>
        </span>
        <span class="urgent">Urgent</span>
        <NuxtLink to="/request" class="edit" aria-label="New request"><AppIcon name="edit" :size="20" /></NuxtLink>
      </div>

      <NuxtLink v-if="d.status.value !== 'open'" :to="d.trackLink.value" class="state-pill" :class="d.status.value">
        <AppIcon :name="d.status.value === 'escalated' ? 'warning' : 'clock'" :size="18" />
        <span><b>{{ statusLabel(d.status.value) }}</b><template v-if="pickedName"> · {{ pickedName }}</template></span>
        <small>Track</small>
      </NuxtLink>

      <div v-if="!opts.length" class="warn" role="alert">
        <div class="wt"><AppIcon name="warning" :size="26" /><strong>No site has spare compatible units</strong></div>
        <p>Yesterday's count shows nothing to spare for this request. Use the phone process, and decide now on emergency group O or a transfer. A person makes this call.</p>
        <p v-if="decided" class="done"><AppIcon name="check" :size="18" /> {{ decided }}</p>
        <button type="button" class="btn btn-dark" :disabled="busy" @click="d.decide('groupO')"><AppIcon name="groupO" /> Use emergency group O</button>
        <button type="button" class="btn warn-outline" :disabled="busy" @click="d.decide('transfer')"><AppIcon name="transfer" /> Transfer the patient</button>
      </div>

      <div v-else-if="d.tooLong.value && d.top.value" class="warn" role="alert">
        <div class="wt"><AppIcon name="warning" :size="26" /><strong>The best source may not arrive in time</strong></div>
        <p>
          The fastest is most likely {{ fmtHours(d.top.value.p50) }}, and 8 in 10 arrive within
          {{ fmtRange(d.top.value.p10, d.top.value.p90) }}: the slow end is over your limit of {{ fmtHours(limit) }}.
          Decide now. A person makes this call.
        </p>
        <p v-if="decided" class="done"><AppIcon name="check" :size="18" /> {{ decided }}</p>
        <button type="button" class="btn btn-dark" :disabled="busy" @click="d.decide('groupO')"><AppIcon name="groupO" /> Use emergency group O</button>
        <button type="button" class="btn warn-outline" :disabled="busy" @click="d.decide('transfer')"><AppIcon name="transfer" /> Transfer the patient</button>
      </div>

      <div v-if="d.noFullSource.value && opts.length" class="info" role="status">
        <AppIcon name="units" :size="22" />
        <span>No single site has all {{ need }} units. Each option covers part of the request.</span>
      </div>

      <div v-if="baselineLine" class="banner">
        <AppIcon name="clock" :size="24" />
        <span>{{ baselineLine }}</span>
      </div>

      <div v-if="opts.length" class="filters" role="group" aria-label="Filter sources">
        <button type="button" :class="{ on: filter === 'all' }" @click="filter = 'all'">All {{ opts.length }}</button>
        <button type="button" :class="{ on: filter === 'hospital' }" @click="filter = 'hospital'">Hospitals {{ count('hospital') }}</button>
        <button type="button" :class="{ on: filter === 'centre' }" @click="filter = 'centre'">Centres {{ count('centre') }}</button>
      </div>
      <p class="notes">
        <span>Stock: count of {{ fmtDay(rk.request.as_of_stock_date) }}, unconfirmed until the site confirms.</span>
        <span v-if="!rk.model_used" class="rough">Rough estimate: the arrival model is not loaded.</span>
        <span v-if="!rk.sharing_allowed">Hospital sharing is off: regional centres only.</span>
        <span v-if="!d.live" class="demo">Demo data: fictional sites.</span>
      </p>

      <ul class="list">
        <li v-for="(o, i) in shown" :key="o.id" class="rise" :style="{ '--d': i * 90 + 'ms' }">
          <SourceCard
            :option="o" :rank="o.rank" :selected="o.id === d.selectedId.value" :limit-h="limit" :need="need" :max="axis"
            :first="o.rank === 1" :fastest="fastest" :passed="d.passed.value.includes(o.id)" @select="d.select(o.id)"
          />
        </li>
      </ul>

      <details v-if="d.selected.value" class="whym">
        <summary>Why {{ short(d.selected.value.name) }}? <small>Reasons, stock and arrival clock</small></summary>
        <SourceDetail :option="d.selected.value" :requested-at="req.requestedAt" :need="need" :compatibility-note="rk.compatibility_note" compact />
      </details>

      <div class="cta">
        <NuxtLink v-if="cta.kind === 'track'" :to="d.trackLink.value" class="btn btn-primary">{{ cta.label }}</NuxtLink>
        <NuxtLink v-else-if="cta.kind === 'closed'" to="/request" class="btn">{{ cta.label }}</NuxtLink>
        <button v-else type="button" class="btn" :class="d.tooLong.value || d.selected.value?.partial ? 'btn-outline-blood' : 'btn-primary'" :disabled="cta.kind === 'none' || busy" @click="d.confirmSelection()">
          {{ d.busy.value === 'event' ? 'Recording…' : cta.label }}
        </button>
        <SafetyNote />
      </div>
    </section>

    <aside v-if="d.selected.value" class="detail" aria-label="Why this source">
      <SourceDetail :option="d.selected.value" :requested-at="req.requestedAt" :need="need" :compatibility-note="rk.compatibility_note" />
    </aside>
  </div>

  <div v-else class="state">
    <div v-if="view === 'loading'" class="card box" role="status">
      <span class="spin" aria-hidden="true" />
      <b>Loading sources…</b>
      <p>Checking yesterday's stock and arrival ranges.</p>
    </div>
    <div v-else class="card box" role="alert">
      <IconBadge size="lg" tone="amber"><AppIcon name="warning" :size="26" /></IconBadge>
      <b>Sources not available</b>
      <p>{{ errorText }}</p>
      <div class="acts">
        <button type="button" class="btn btn-primary" @click="load">Try again</button>
        <NuxtLink v-if="authFail && authEnabled" to="/sign-in" class="btn">Sign in</NuxtLink>
        <NuxtLink to="/request" class="btn">New request</NuxtLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.results { position: relative; height: calc(100dvh - var(--header-h) - var(--dock-h)); min-height: 560px; overflow: hidden; background: var(--fog); margin-top: 6px; }
.map { position: absolute; inset: 0 0 auto 0; height: 34vh; }
.mapchip { display: none; }
.panel { position: absolute; left: 0; right: 0; bottom: 0; top: 28vh; padding: 10px 16px 12px; border-radius: 40px 44px 0 0; background: rgba(255, 255, 255, 0.97); box-shadow: 0 -14px 40px rgba(6, 74, 68, 0.2); display: flex; flex-direction: column; gap: 10px; overflow-y: auto; z-index: 5; }
.grab { width: 44px; height: 5px; border-radius: 99px; background: #c9dbd8; margin: 0 auto 2px; flex-shrink: 0; }
.sum { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-lg); background: linear-gradient(180deg, #e4f2f0, #e3efed); flex-shrink: 0; }
.grp { font-size: 44px; line-height: 1; font-weight: 800; color: var(--blood-500); letter-spacing: -0.03em; }
.meta { flex: 1; min-width: 0; display: flex; flex-direction: column; font-size: 16px; }
.meta small { font-size: var(--fs-caption); font-weight: 700; color: #44545f; margin-top: 3px; }
.meta small.soon { color: var(--teal-600); }
.urgent { padding: 5px 11px; border-radius: 99px; background: var(--blood-500); color: #fff; font-size: 11px; font-weight: 800; }
.edit { display: none; width: 44px; height: 44px; border-radius: 99px; border: 1.5px solid #c9dbd8; background: #fff; place-items: center; color: var(--primary-700); }
.state-pill { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-radius: 99px; background: var(--primary-50); border: 1.5px solid #b9d9d4; color: var(--primary-700); text-decoration: none; font-size: 13.5px; font-weight: 600; flex-shrink: 0; }
.state-pill span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.state-pill b { font-weight: 800; }
.state-pill small { font-size: 12px; font-weight: 800; text-decoration: underline; }
.state-pill.escalated, .state-pill.cancelled { background: var(--amber-50); border-color: #ecc98a; color: var(--amber-900); }
.banner { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: var(--r-md); background: var(--teal-50); color: #064e46; font-size: 13px; font-weight: 700; line-height: 1.4; flex-shrink: 0; }
.banner svg { color: var(--teal-600); flex-shrink: 0; }
.info { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: var(--r-md); background: var(--azure-50); color: #123e73; font-size: 13.5px; font-weight: 700; line-height: 1.4; flex-shrink: 0; }
.info svg { color: var(--azure-600); flex-shrink: 0; }
.filters { display: none; align-items: center; gap: 8px; }
.filters button { padding: 8px 16px; border-radius: 99px; border: 1.5px solid #c9dbd8; background: #fff; color: #44545f; font-size: 13px; font-weight: 800; }
.filters button.on { background: #1b1b1f; border-color: #1b1b1f; color: #fff; }
.notes { margin: 0; display: flex; flex-direction: column; gap: 2px; font-size: 12px; font-weight: 700; color: #5d6d78; line-height: 1.4; flex-shrink: 0; }
.notes .rough { color: var(--amber-700); }
.notes .demo { color: var(--azure-600); }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; padding-top: 8px; }
.whym { border-radius: var(--r-lg); background: #fff; border: 1.5px solid #d8e4e2; padding: 0 16px; flex-shrink: 0; }
.whym summary { cursor: pointer; min-height: 48px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-weight: 800; font-size: 14px; color: var(--primary-700); }
.whym summary small { font-size: 12px; font-weight: 600; color: #5d6d78; }
.whym[open] { padding-bottom: 16px; }
.cta { margin-top: auto; display: flex; flex-direction: column; gap: 8px; padding-top: 6px; }
.cta .btn { min-height: 52px; }
.cta .btn:disabled { opacity: 0.6; cursor: not-allowed; }
.warn { background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: var(--r-lg); padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; color: var(--amber-900); flex-shrink: 0; }
.wt { display: flex; align-items: center; gap: 10px; color: var(--amber-700); }
.wt strong { font-size: 17px; line-height: 1.2; color: var(--amber-900); }
.warn p { margin: 0; font-size: 13.5px; line-height: 1.5; font-weight: 600; }
.warn p.done { display: flex; align-items: center; gap: 8px; font-weight: 800; color: var(--teal-600); }
.warn .btn:disabled { opacity: 0.6; }
.warn-outline { border-color: var(--amber-500); }
.detail { display: none; }

@media (min-width: 900px) {
  .results { height: calc(100dvh - var(--header-h)); min-height: 640px; }
  .map { inset: 0; height: auto; }
  .mapchip { display: block; position: absolute; left: 518px; top: 12px; z-index: 5; padding: 10px 20px; border-radius: 99px; background: rgba(255, 255, 255, 0.95); border: 1px solid #d8e4e2; box-shadow: 0 12px 28px rgba(6, 74, 68, 0.14); font-size: 14px; font-weight: 800; color: var(--ink-deep); }
  .panel { left: 24px; right: auto; top: 12px; bottom: 24px; width: 470px; padding: 20px; border-radius: 40px 44px 40px 46px / 44px 40px 46px 40px; border: 1.5px solid var(--primary-500); box-shadow: 0 26px 60px rgba(6, 74, 68, 0.2); gap: 12px; }
  .grab { display: none; }
  .grp { font-size: 56px; }
  .edit { display: grid; }
  .banner { gap: 12px; padding: 12px 16px; font-size: 14px; }
  .filters { display: flex; }
  .whym { display: none; }
  .detail { display: block; position: absolute; right: 24px; top: 12px; width: 350px; padding: 24px; border-radius: 40px 44px 40px 46px / 44px 40px 46px 40px; background: rgba(255, 255, 255, 0.96); border: 1.5px solid #d8e4e2; box-shadow: 0 26px 60px rgba(6, 74, 68, 0.18); z-index: 5; max-height: calc(100% - 36px); overflow-y: auto; }
}

.state { flex: 1; display: grid; place-items: center; padding: 40px 16px; }
.box { width: 100%; max-width: 440px; padding: 28px 24px; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.box b { font-size: 18px; color: var(--ink-deep); }
.box p { margin: 0; font-size: 14px; font-weight: 600; color: #44545f; line-height: 1.5; }
.acts { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 6px; }
.acts .btn { min-height: 46px; }
.spin { width: 34px; height: 34px; border-radius: 99px; border: 3px solid var(--primary-50); border-top-color: var(--primary-500); animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
