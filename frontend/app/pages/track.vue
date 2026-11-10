<script setup lang="ts">
useHead({ title: 'Track · Blood Dispatch' })

const route = useRoute()
const d = useDispatch()
const { toast } = useToast()
const { public: { authEnabled } } = useRuntimeConfig()

// Tracking needs a stored request (?id=); the server renders the loading state, the browser restores it.
const view = ref<'loading' | 'ready' | 'error'>(d.matches(route.query) ? 'ready' : 'loading')
async function load() {
  if (!d.matches(route.query)) view.value = 'loading'
  const r = await d.loadFromQuery(route.query, { preview: false })
  if (r === 'empty') return navigateTo({ path: '/request', query: { need: 'track' } }, { replace: true })
  view.value = r === 'ok' ? 'ready' : 'error'
}
onMounted(load)
watch(() => route.query, (q) => { if (!d.matches(q)) load() })

const req = computed(() => d.request.value)
const status = computed(() => d.status.value)
// The source being tracked is the pick on record, never just the highlighted card.
const picked = computed(() => d.options.value.find(o => o.id === d.pickedId.value) ?? null)
const limit = computed(() => d.limitH.value)
const axis = computed(() => barMax(limit.value, picked.value?.p90 ?? 0))
const busy = computed(() => d.busy.value !== null)
const short = (name: string) => name.split(' ').slice(0, 2).join(' ')

const steps = computed(() => {
  const who = picked.value ? short(picked.value.name) : 'The site'
  return [
    { title: 'Request sent', sub: `${eatClock(req.value?.createdAt ?? req.value?.requestedAt ?? '')} · logged` },
    { title: 'Waiting for shelf check', sub: `${who} confirms the units are on the shelf. No answer in ${CONFIRM_TIMEOUT_MIN} min: try the next source.` },
    { title: 'Shelf confirmed', sub: 'The site has checked the units are there.' },
    { title: 'Dispatched', sub: 'On the road. Times still count from the request.' },
    { title: 'Arrived', sub: 'The lab checks and crossmatches every bag.' }
  ]
})
function stepState(i: number) {
  if (status.value === 'arrived') return 'done'
  if (status.value === 'cancelled') return i === 0 ? 'done' : 'todo'
  const stage = statusStage(status.value)
  return i < stage ? 'done' : i === stage ? 'now' : 'todo'
}
const decisionText = computed(() => (d.decision.value === 'groupO' ? 'the clinician chose emergency group O.' : d.decision.value === 'transfer' ? 'the clinician chose to transfer the patient.' : ''))
const canCancel = computed(() => (['open', 'escalated', 'awaiting_shelf', 'confirmed'] as string[]).includes(status.value))
const nextStep = computed(() => siteStep(status.value))

// The supplying site has CONFIRM_TIMEOUT_MIN minutes to confirm the shelf; then a person moves on.
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined
onMounted(() => { tick = setInterval(() => { now.value = Date.now() }, 15_000) })
onBeforeUnmount(() => clearInterval(tick))
const minutesLeft = computed(() => {
  const at = d.pickedAt.value ? eatTime(d.pickedAt.value) : null
  return at === null ? null : Math.max(0, CONFIRM_TIMEOUT_MIN - Math.floor((now.value - at) / 60_000))
})

function callSite() {
  toast({ title: `Call ${picked.value?.name ?? 'the site'}`, body: 'Phone process: ask them to confirm the units are on the shelf, then record the answer here.' })
}
const showAudit = ref(false)
const askCancel = ref(false)
function cancel() {
  askCancel.value = false
  d.cancel()
}

const errorText = computed(() => {
  const f = d.error.value
  if (!f) return 'Could not load this request.'
  if (f.network) return 'Tool not reachable. Use the phone process: call the blood centre directly.'
  if (isAuthFailure(f)) return f.message || 'Sign in and choose your hospital to track requests.'
  return f.message || 'Could not load this request.'
})
</script>

<template>
  <div v-if="view === 'ready' && req" class="wrap">
    <h1 class="sr-only">Tracking your blood request</h1>
    <div class="map"><SourceMap :options="picked ? [picked] : []" :selected-id="picked?.id ?? null" :pad-top="80" /></div>

    <section class="panel">
      <NuxtLink :to="d.resultsLink.value" class="back"><AppIcon name="back" /> Back to results</NuxtLink>

      <p v-if="status === 'escalated'" class="flag warn" role="status"><AppIcon name="warning" :size="18" /> <span><b>Escalated:</b> {{ decisionText || 'a clinician decision was recorded.' }} Saved in the audit log.</span></p>
      <p v-else-if="status === 'cancelled'" class="flag" role="status"><AppIcon name="close" :size="18" /> <span><b>Cancelled.</b> Saved in the audit log.</span></p>
      <p v-else-if="decisionText" class="flag warn" role="status"><AppIcon name="warning" :size="18" /> <span>Also recorded: {{ decisionText }}</span></p>

      <div v-if="picked" class="window card">
        <small>ARRIVAL WINDOW · {{ picked.name }}</small>
        <div class="big"><strong><Dur :h="picked.p50" /></strong><span>most likely · 8 in 10 arrive within {{ fmtRange(picked.p10, picked.p90) }}</span></div>
        <p class="eta"><AppIcon name="clock" :size="18" /> Expected around <b class="tnum">{{ clockAfter(req.requestedAt, picked.p50) }}</b><span>(8 in 10 between {{ clockAfter(req.requestedAt, picked.p10) }} and {{ clockAfter(req.requestedAt, picked.p90) }})</span></p>
        <WindowBar :p10="picked.p10" :p50="picked.p50" :p90="picked.p90" :limit="limit" :max="axis" />
        <div class="scale"><span>Request at {{ eatClock(req.requestedAt) }}</span><span>Line = your {{ fmtHours(limit) }} limit</span><span>{{ fmtHours(axis) }} later</span></div>
      </div>
      <div v-else class="card nopick">
        <b>No source picked{{ status === 'open' && d.passed.value.length ? ' now' : '' }}</b>
        <p v-if="status === 'open'">Pick a source on the results to start the shelf check.</p>
        <p v-else-if="status === 'escalated'">The request stays open: you can still pick a source on the results.</p>
        <p v-else>Nothing is on its way for this request.</p>
        <NuxtLink v-if="status === 'open' || status === 'escalated'" :to="d.resultsLink.value" class="btn btn-primary">Back to results</NuxtLink>
      </div>

      <ol class="steps">
        <li v-for="(s, i) in steps" :key="s.title" :class="[stepState(i), 'rise']" :style="{ '--d': i * 80 + 'ms' }">
          <span class="dot"><AppIcon v-if="stepState(i) === 'done'" name="check" :size="14" /></span>
          <span class="txt"><strong>{{ s.title }}</strong><small>{{ s.sub }}</small></span>
        </li>
      </ol>

      <div v-if="status === 'awaiting_shelf' && minutesLeft === 0" class="timeout" role="alert">
        <span><AppIcon name="warning" :size="18" /> No answer from {{ picked ? short(picked.name) : 'the site' }} in {{ CONFIRM_TIMEOUT_MIN }} minutes.</span>
        <button type="button" class="btn btn-dark" :disabled="busy" @click="d.nextSource('confirm_timeout')">Ask the next source</button>
      </div>
      <p v-else-if="status === 'awaiting_shelf' && minutesLeft !== null" class="countdown"><AppIcon name="clock" :size="16" /> Shelf check: {{ minutesLeft }} min left before you try the next source.</p>

      <div v-if="picked && !['arrived', 'cancelled'].includes(status)" class="actions">
        <button v-if="status === 'awaiting_shelf'" type="button" class="btn" :disabled="busy" @click="d.nextSource()">Try next source</button>
        <NuxtLink v-else :to="d.resultsLink.value" class="btn">Back to results</NuxtLink>
        <button type="button" class="btn btn-dark" @click="callSite"><AppIcon name="call" :size="20" /> Call site</button>
      </div>
      <button v-if="nextStep" type="button" class="demo" :disabled="busy" @click="d.advance()">Demo: record next step (the supplying site does this)</button>
      <SafetyNote />

      <div class="foot">
        <button type="button" class="auditbtn" @click="showAudit = true"><AppIcon name="audit" :size="18" /> Audit log ({{ d.audit.value.length }})</button>
        <button v-if="canCancel" type="button" class="cancel" :disabled="busy" @click="askCancel = true">Cancel request</button>
      </div>
    </section>

    <AppModal v-model="showAudit" title="Audit log" :sub="`${req.id ?? 'Demo request'} · times in East Africa Time. Every action is recorded; a person approves every step.`">
      <ul class="alog"><li v-for="a in d.audit.value" :key="a.id"><time>{{ eatClock(a.at) }}</time><span>{{ auditSentence(a, d.names.value) }}</span></li></ul>
    </AppModal>

    <AppModal v-model="askCancel" title="Cancel this request?" sub="The cancellation is saved in the audit log.">
      <p class="mnote">Cancel when the patient no longer needs these units. If a site is already checking its shelf, tell it by phone.</p>
      <template #footer>
        <button type="button" class="btn" @click="askCancel = false">Keep the request</button>
        <button type="button" class="btn btn-dark" @click="cancel">Cancel request</button>
      </template>
    </AppModal>
  </div>

  <div v-else class="state">
    <div v-if="view === 'loading'" class="card box" role="status">
      <span class="spin" aria-hidden="true" />
      <b>Loading the request…</b>
    </div>
    <div v-else class="card box" role="alert">
      <IconBadge size="lg" tone="amber"><AppIcon name="warning" :size="26" /></IconBadge>
      <b>Request not available</b>
      <p>{{ errorText }}</p>
      <div class="acts">
        <button type="button" class="btn btn-primary" @click="load">Try again</button>
        <NuxtLink v-if="d.error.value && isAuthFailure(d.error.value) && authEnabled" to="/sign-in" class="btn">Sign in</NuxtLink>
        <NuxtLink to="/request" class="btn">New request</NuxtLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { position: relative; flex: 1; min-height: calc(100dvh - var(--header-h) - var(--dock-h)); background: var(--fog); overflow: hidden; }
.map { position: absolute; inset: 0 0 auto 0; height: 32vh; }
.panel { position: absolute; left: 0; right: 0; top: 30vh; bottom: 0; background: var(--white); border-radius: 26px 26px 0 0; box-shadow: 0 -8px 30px rgba(18, 32, 43, 0.16); padding: 16px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.back { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; font-size: 14px; color: var(--slate); text-decoration: none; min-height: 32px; }
.flag { margin: 0; display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border-radius: var(--r-md); background: #eceff1; color: var(--ink); font-size: 13.5px; font-weight: 600; line-height: 1.45; }
.flag svg { flex-shrink: 0; margin-top: 1px; }
.flag.warn { background: var(--amber-50); color: var(--amber-900); }
.flag.warn svg { color: var(--amber-700); }
.window { padding: 14px 16px; background: var(--paper); display: flex; flex-direction: column; gap: 10px; }
.window small { font-size: 12px; font-weight: 800; letter-spacing: 0.04em; color: var(--slate); }
.big { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.big strong { font-size: 34px; line-height: 1; }
.big > span { font-size: 13px; font-weight: 700; color: var(--slate); }
.eta { margin: 0; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 14px; font-weight: 600; color: #44545f; }
.eta svg { color: var(--teal-600); }
.eta b { font-size: 18px; color: var(--ink); }
.eta span { font-size: 12.5px; color: var(--slate); }
.scale { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; font-weight: 700; color: var(--slate); }
.nopick { padding: 16px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.nopick b { font-size: 16px; color: var(--ink-deep); }
.nopick p { margin: 0; font-size: 13.5px; font-weight: 600; color: #44545f; line-height: 1.45; }
.nopick .btn { min-height: 46px; }
.steps { list-style: none; margin: 0; padding: 0 4px; display: flex; flex-direction: column; }
.steps li { display: flex; gap: 14px; padding-bottom: 14px; position: relative; }
.steps li:not(:last-child)::before { content: ''; position: absolute; left: 11px; top: 26px; bottom: 2px; width: 2px; background: var(--line); }
.steps li.done:not(:last-child)::before { background: var(--teal-600); }
.dot { width: 24px; height: 24px; border-radius: 99px; flex-shrink: 0; display: grid; place-items: center; background: var(--white); border: 2px solid var(--line); color: #fff; }
.done .dot { background: var(--teal-600); border-color: var(--teal-600); }
.now .dot { border: 3px solid var(--primary-500); animation: ring 1.6s ease-out infinite; }
.txt { display: flex; flex-direction: column; }
.txt strong { font-size: 14.5px; }
.txt small { font-size: 12.5px; font-weight: 600; color: var(--slate); line-height: 1.4; margin-top: 1px; }
.todo .txt strong { color: var(--slate); }
.timeout { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border-radius: var(--r-lg); background: var(--amber-50); border: 2px solid var(--amber-500); color: var(--amber-900); font-size: 13.5px; font-weight: 700; }
.timeout span { display: flex; align-items: center; gap: 8px; }
.timeout svg { color: var(--amber-700); flex-shrink: 0; }
.timeout .btn { min-height: 46px; }
.countdown { margin: 0; display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 700; color: var(--slate); }
.countdown svg { color: var(--teal-600); }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: auto; }
.actions .btn { min-height: 52px; font-size: 14px; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.demo { align-self: center; border: 1px dashed var(--line); background: transparent; border-radius: 10px; min-height: 36px; padding: 0 14px; font-size: 12px; font-weight: 700; color: var(--slate); }
.foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.cancel { border: 0; background: none; padding: 8px 4px; font-size: 13px; font-weight: 800; color: var(--slate); text-decoration: underline; }

@media (min-width: 900px) {
  .wrap { height: calc(100dvh - var(--header-h)); min-height: 640px; margin-top: 6px; }
  .map { inset: 0; height: auto; }
  .panel { top: 12px; left: 24px; right: auto; bottom: 24px; width: 470px; border-radius: 40px 44px 40px 46px / 44px 40px 46px 40px; border: 1.5px solid var(--primary-500); box-shadow: 0 26px 60px rgba(6, 74, 68, 0.2); padding: 22px; }
}
.auditbtn { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 16px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: #fff; color: var(--primary-700); font-weight: 800; font-size: 14px; transition: transform 0.2s ease; }
.auditbtn:hover { transform: translateY(-1px); }
.alog { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.alog li { display: flex; gap: 12px; padding: 10px 14px; border-radius: var(--r-md); background: #fff; border: 1.5px solid #d8e4e2; font-size: 14px; font-weight: 600; color: var(--slate); line-height: 1.45; }
.alog time { font-weight: 800; color: var(--ink); flex-shrink: 0; }
.mnote { margin: 0 0 12px; font-size: 14px; line-height: 1.55; font-weight: 500; color: #44545f; }

.state { flex: 1; display: grid; place-items: center; padding: 40px 16px; }
.box { width: 100%; max-width: 440px; padding: 28px 24px; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.box b { font-size: 18px; color: var(--ink-deep); }
.box p { margin: 0; font-size: 14px; font-weight: 600; color: #44545f; line-height: 1.5; }
.acts { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 6px; }
.acts .btn { min-height: 46px; }
.spin { width: 34px; height: 34px; border-radius: 99px; border: 3px solid var(--primary-50); border-top-color: var(--primary-500); animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
