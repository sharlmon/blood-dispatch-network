<script setup lang="ts">
import type { ApiFailure } from '~/composables/useApi'
import type { Option, RankResult, RequestRecord } from '~/utils/engine'
import { RECENT, mockRankResult } from '~/utils/mock'

useHead({ title: 'New request · Blood Dispatch' })

const route = useRoute()
const d = useDispatch()
const { api, fail, engineUp, live } = useApi()
const { toast } = useToast()
const { firstName, hospital } = useSite()
const fac = useFacilities()
const img = useImg()

const group = ref(route.query.sos ? 'Unknown' : 'B+')
const units = ref(2)
const limitH = ref(6) // the engine's default clinician limit
const facilityId = ref('')

const hello = ref('Hello')
onMounted(() => {
  const h = new Date().getHours()
  hello.value = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
})

const unknown = computed(() => group.value === 'Unknown')
const effective = computed(() => (unknown.value ? 'O' : group.value))

// Requesting facility (live): saved on this device, else the organisation's, else the first hospital.
const hospitalOptions = computed(() => fac.hospitals.value.map(f => ({ value: f.facility_id, label: f.name, hint: f.county ?? undefined })))
const facilityName = computed(() => fac.name(facilityId.value))
const where = computed(() => (live ? facilityName.value ?? hospital.value : hospital.value))
function chooseFacility(id: string) {
  facilityId.value = id
  saveFacility(id)
}
async function loadFacilities() {
  const id = await fac.defaultId()
  if (id && !facilityId.value) facilityId.value = id
}

// Recent requests of this organisation (live) or a fictional sample (static demo).
const recent = ref<RequestRecord[] | null>(null)
const recentError = ref<ApiFailure | null>(null)
async function loadRecent() {
  try {
    recent.value = (await api<{ requests: RequestRecord[] }>('/api/requests?limit=6')).requests
    recentError.value = null
  } catch (e) {
    recentError.value = fail(e, { quiet: true })
  }
}
const recordLink = (r: RequestRecord) => ({ path: r.status === 'open' || r.status === 'escalated' ? '/results' : '/track', query: { id: r.id } })
const PLAIN: Record<string, string> = { open: 'No source picked yet', escalated: 'Escalated to the clinician', cancelled: 'Cancelled' }
const recordLine = (r: RequestRecord) => r.selected_name ?? PLAIN[r.status] ?? statusLabel(r.status)
const recordTone = (s: string) => ({ awaiting_shelf: 'st-red', confirmed: 'st-red', dispatched: 'st-red', arrived: 'st-teal', escalated: 'st-amber' } as Record<string, string>)[s] ?? 'st-grey'
const groupOf = (g: string) => (g.toLowerCase() === 'unknown' ? 'O?' : toDisplayGroup(g))

onMounted(() => {
  if (!live) return
  loadFacilities()
  loadRecent()
})

// Nearby sources: a stateless preview of the same ranking (POST /api/rank), refreshed as the form changes.
const preview = shallowRef<RankResult | null>(null)
const previewBusy = ref(false)
const previewError = ref<ApiFailure | null>(null)
let seq = 0
let timer: ReturnType<typeof setTimeout> | undefined
async function runPreview() {
  const my = ++seq
  previewBusy.value = true
  try {
    const r = await api<RankResult>('/api/rank', {
      method: 'POST',
      body: { facility_id: facilityId.value, patient_group: toApiGroup(group.value), units_needed: units.value, component: 'RBC', limit_h: limitH.value }
    })
    if (my !== seq) return // a newer preview is on its way
    preview.value = r
    previewError.value = null
    engineUp()
  } catch (e) {
    if (my === seq) previewError.value = fail(e, { quiet: true })
  } finally {
    if (my === seq) previewBusy.value = false
  }
}
watch([facilityId, group, units, limitH], () => {
  if (!live || !import.meta.client || !facilityId.value) return
  clearTimeout(timer)
  timer = setTimeout(runPreview, 400)
})
onBeforeUnmount(() => clearTimeout(timer))

const nearbyResult = computed<RankResult | null>(() => (live
  ? preview.value
  : mockRankResult({ group: group.value, units: units.value, limitH: limitH.value, requesterName: hospital.value })))
const nearby = computed(() => (nearbyResult.value ? toOptions(nearbyResult.value) : []))
const stockDay = computed(() => (nearbyResult.value ? fmtDay(nearbyResult.value.ranking.request.as_of_stock_date) : ''))
const nearbyNote = computed(() => {
  if (!live) return ''
  if (!facilityId.value) return fac.state.value === 'error' ? quiet(fac.error.value) : 'Choose your hospital to see who could spare blood.'
  if (previewError.value) return quiet(previewError.value)
  if (!preview.value) return 'Checking yesterday\'s stock…'
  return nearby.value.length ? '' : 'No site has spare compatible units in yesterday\'s count. Use the phone process.'
})
function quiet(f: ApiFailure | null): string {
  if (!f) return 'Could not load this.'
  if (f.network) return 'Tool not reachable. Use the phone process.'
  if (f.code === 'engine_unavailable') return 'Ranking engine not available. Use the phone process.'
  if (isAuthFailure(f)) return f.message || 'Sign in and choose your hospital to see live data.'
  return f.message || 'Could not load this.'
}
const spareText = (o: Option) => (o.partial ? `covers ${o.spare} of ${units.value}` : `${o.spare} ${o.spare === 1 ? 'unit' : 'units'} spare`)

const form = ref<HTMLElement | null>(null)
function sos() {
  group.value = 'Unknown'
  toast({ tone: 'warn', title: 'Group O will be requested', body: 'Unknown group: only group O, per hospital protocol.' })
  form.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const stepUnits = (n: number) => {
  const next = Math.min(10, Math.max(1, units.value + n))
  if (next === units.value) toast({ tone: 'info', title: n > 0 ? 'Maximum is 10 units' : 'At least 1 unit', ms: 2200 })
  units.value = next
}
const stepLimit = (n: number) => {
  const next = Math.min(12, Math.max(1, limitH.value + n))
  if (next === limitH.value) toast({ tone: 'info', title: n > 0 ? 'Longest limit is 12 hours' : 'Shortest limit is 1 hour', ms: 2200 })
  limitH.value = next
}

// Lists stay short on the page; the full list opens in a modal.
const showRecent = ref(false)
const showSources = ref(false)
const pickedRecent = ref<(typeof RECENT)[number] | null>(null)
const recentOpen = computed({ get: () => !!pickedRecent.value, set: (v) => { if (!v) pickedRecent.value = null } })
const contact = ref<Option | null>(null)
const contactOpen = computed({ get: () => !!contact.value, set: (v) => { if (!v) contact.value = null } })
const contacted = ref<string[]>([])
const smsText = computed(() => `${effective.value} ${units.value} RBC ${limitH.value}H`)
async function copy(text: string) {
  try { await navigator.clipboard.writeText(text); toast({ tone: 'ok', title: 'Copied', body: text, ms: 2600 }) }
  catch { toast({ tone: 'warn', title: 'Could not copy', body: 'Select the text and copy it by hand.' }) }
}
function markContacted() {
  if (!contact.value) return
  contacted.value = [...contacted.value, contact.value.id]
  toast({ tone: 'ok', title: 'Marked as contacted', body: `${contact.value.name}. Ask them to confirm the shelf.` })
  contact.value = null
}
function rerun(r: (typeof RECENT)[number]) {
  group.value = r.group; units.value = r.units
  pickedRecent.value = null; showRecent.value = false
  toast({ tone: 'info', title: `Loaded ${r.group}, ${r.units} ${r.units === 1 ? 'unit' : 'units'}`, body: 'Check the details, then find sources.' })
  form.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function submit() {
  if (live && !facilityId.value) {
    toast({ tone: 'warn', title: 'Choose the requesting hospital', body: 'Pick it under "Requesting hospital", then find sources.' })
    return
  }
  await d.search({ facilityId: facilityId.value, facilityName: facilityName.value, group: group.value, units: units.value, limitH: limitH.value })
}
const statusClass = (s: string) => ({ Dispatched: 'st-red', Arrived: 'st-teal', Escalated: 'st-amber' }[s] ?? '')
const searching = computed(() => d.busy.value === 'search')
</script>

<template>
  <div class="page">
    <p v-if="route.query.need" class="needhint" role="status">
      <IconBadge size="sm" tone="amber"><AppIcon name="warning" :size="18" /></IconBadge>
      <span>Results and tracking appear here after you find sources. Start a request first.</span>
    </p>

    <header class="greet">
      <div>
        <p class="hi">{{ hello }}<span v-if="firstName">, {{ firstName }}</span></p>
        <p class="where"><AppIcon name="pin" :size="16" /> {{ where }}</p>
      </div>
      <NuxtLink :to="d.request.value ? d.trackLink.value : '/request?need=track'" class="bell" aria-label="Your current request"><AppIcon name="bell" :size="22" /><i v-if="d.request.value" /></NuxtLink>
    </header>

    <section class="hero organic-card">
      <div class="hc">
        <h1>Urgently need blood?</h1>
        <p>Tell us what the patient needs. We list every source that can spare it, with an honest range for when it will arrive.</p>
        <button type="button" class="sosbtn" @click="sos"><AppIcon name="drop" :size="18" /> <span class="long">Group unknown? </span>Request group O</button>
      </div>
      <div class="bgphoto" aria-hidden="true"><img :src="img('donation-room.jpg')" alt=""></div>
    </section>

    <form ref="form" class="form card" @submit.prevent="submit">
      <h2>Quick request</h2>

      <div class="block">
        <label class="lbl">Patient blood group</label>
        <BloodGroupPicker v-model="group" allow-unknown />
        <p v-if="unknown" class="unk-note"><AppIcon name="warning" :size="18" /> Unknown group: only group O is requested, per hospital protocol. A person confirms the group before use.</p>
      </div>

      <div class="rows">
        <div class="row">
          <IconBadge><AppIcon name="drop" :size="22" /></IconBadge>
          <span class="rl"><b>Product</b><small>What the patient needs</small></span>
          <span class="hosp">Red cells</span>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="units" :size="22" /></IconBadge>
          <span class="rl"><b>Units needed</b><small>Bags for this patient</small></span>
          <span class="step"><button type="button" aria-label="One fewer unit" @click="stepUnits(-1)">−</button><output :key="units" class="tnum flip" aria-live="polite">{{ units }}</output><button type="button" aria-label="One more unit" @click="stepUnits(1)">+</button></span>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="clock" :size="22" /></IconBadge>
          <span class="rl"><b>Longest wait</b><small>Flags a wait that is too long</small></span>
          <span class="step"><button type="button" aria-label="Shorter limit" @click="stepLimit(-1)">−</button><output :key="limitH" class="tnum flip" aria-live="polite">{{ limitH }}h</output><button type="button" aria-label="Longer limit" @click="stepLimit(1)">+</button></span>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="hospital" :size="22" /></IconBadge>
          <span class="rl"><b>Requesting hospital</b><small>{{ live ? 'Saved on this device' : 'From your account' }}</small></span>
          <span v-if="live" class="pickfac">
            <ThemedSelect
              :model-value="facilityId" label="Requesting hospital" :options="hospitalOptions" :disabled="!hospitalOptions.length"
              :placeholder="fac.state.value === 'error' ? 'Not loaded' : 'Loading…'" @update:model-value="chooseFacility"
            />
            <button v-if="fac.state.value === 'error'" type="button" class="retry" @click="loadFacilities">Retry</button>
          </span>
          <span v-else class="hosp">{{ hospital }}</span>
        </div>
      </div>
      <p class="pnote"><AppIcon name="drop" :size="16" /> Red cells and whole blood stock both count. Platelets and plasma are not ranked yet.</p>

      <button type="submit" class="btn btn-primary go" :disabled="searching"><AppIcon name="search" /> {{ searching ? 'Finding sources…' : 'Find sources' }}</button>
      <p class="sms"><AppIcon name="sms" :size="22" /><span>No data? Text <b>{{ effective }} {{ units }} RBC {{ limitH }}H</b> to [SHORTCODE].</span></p>
      <SafetyNote />
    </form>

    <aside class="side">
      <section>
        <div class="sh">
          <h2>Recent requests</h2>
          <button v-if="live ? (recent?.length ?? 0) > 2 : true" type="button" class="more" @click="showRecent = true"><AppIcon name="list" :size="16" /> View all {{ live ? recent?.length : RECENT.length }}</button>
        </div>
        <template v-if="live">
          <p v-if="recentError" class="quiet">{{ quiet(recentError) }}</p>
          <p v-else-if="recent === null" class="quiet">Loading recent requests…</p>
          <p v-else-if="!recent.length" class="quiet">No requests from your hospital yet.</p>
          <ul v-else class="recent">
            <li v-for="(r, i) in recent.slice(0, 2)" :key="r.id" class="rise" :style="{ '--d': i * 80 + 'ms' }">
              <NuxtLink :to="recordLink(r)" class="rcard">
                <IconBadge size="lg" class="rg"><b>{{ groupOf(r.patient_group) }}</b></IconBadge>
                <span class="rb">
                  <b>{{ r.units_needed }} {{ r.units_needed === 1 ? 'unit' : 'units' }} needed</b>
                  <small>{{ recordLine(r) }}</small>
                  <small class="when">{{ fmtWhen(r.created_at) }}</small>
                </span>
                <span class="chipst" :class="recordTone(r.status)">{{ statusLabel(r.status) }}</span>
              </NuxtLink>
            </li>
          </ul>
        </template>
        <ul v-else class="recent">
          <li v-for="(r, i) in RECENT.slice(0, 2)" :key="r.when" class="rise" :style="{ '--d': i * 80 + 'ms' }">
            <button type="button" class="rcard" @click="pickedRecent = r">
              <IconBadge size="lg" class="rg"><b>{{ r.group }}</b></IconBadge>
              <span class="rb">
                <b>{{ r.units }} {{ r.units === 1 ? 'unit' : 'units' }} needed</b>
                <small>{{ r.where }}</small>
                <small class="when"><i v-if="r.urgent" class="dot" />{{ r.urgent ? 'Urgent' : 'Planned' }} · {{ r.when }}</small>
              </span>
              <span class="chipst" :class="statusClass(r.status)">{{ r.status }}</span>
            </button>
          </li>
        </ul>
      </section>

      <section>
        <div class="sh">
          <h2>Nearby sources</h2>
          <button v-if="nearby.length > 2" type="button" class="more" @click="showSources = true"><AppIcon name="list" :size="16" /> View all {{ nearby.length }}</button>
        </div>
        <p v-if="stockDay && !nearbyNote" class="stockday">Count of {{ stockDay }}, unconfirmed<span v-if="previewBusy"> · updating…</span></p>
        <p v-if="nearbyNote" class="quiet">{{ nearbyNote }}</p>
        <ul v-else class="near">
          <li v-for="(o, i) in nearby.slice(0, 2)" :key="o.id" class="ncard rise" :style="{ '--d': i * 80 + 'ms' }">
            <div class="nt">
              <IconBadge size="lg" tone="solid" :square="o.kind === 'centre'"><AppIcon :name="o.kind" :size="26" /></IconBadge>
              <span class="nb">
                <b>{{ o.name }}</b>
                <small><AppIcon name="drop" :size="13" /> {{ effective }} <i>·</i> <AppIcon name="clock" :size="13" /> most likely {{ fmtHours(o.p50) }}</small>
              </span>
              <span class="avail" :class="{ part: o.partial }">{{ spareText(o) }}</span>
            </div>
            <button type="button" class="contact" :class="{ done: contacted.includes(o.id) }" @click="contact = o"><AppIcon :name="contacted.includes(o.id) ? 'check' : 'call'" :size="18" /> {{ contacted.includes(o.id) ? 'Contacted' : 'Contact site' }}</button>
          </li>
        </ul>
      </section>
    </aside>

    <AppModal v-model="showRecent" title="Recent requests" :sub="live ? `The last ${recent?.length ?? 0} from your hospital` : `${RECENT.length} in the last week (demo data)`">
      <ul v-if="live" class="mlist">
        <li v-for="r in recent ?? []" :key="r.id">
          <NuxtLink :to="recordLink(r)" class="rcard" @click="showRecent = false">
            <IconBadge size="lg" class="rg"><b>{{ groupOf(r.patient_group) }}</b></IconBadge>
            <span class="rb"><b>{{ r.units_needed }} {{ r.units_needed === 1 ? 'unit' : 'units' }} needed</b><small>{{ recordLine(r) }}</small><small class="when">{{ r.id }} · {{ fmtWhen(r.created_at) }}</small></span>
            <span class="chipst" :class="recordTone(r.status)">{{ statusLabel(r.status) }}</span>
          </NuxtLink>
        </li>
      </ul>
      <ul v-else class="mlist">
        <li v-for="r in RECENT" :key="r.when + r.group">
          <button type="button" class="rcard" @click="showRecent = false; pickedRecent = r">
            <IconBadge size="lg" class="rg"><b>{{ r.group }}</b></IconBadge>
            <span class="rb"><b>{{ r.units }} {{ r.units === 1 ? 'unit' : 'units' }} needed</b><small>{{ r.where }}</small><small class="when"><i v-if="r.urgent" class="dot" />{{ r.urgent ? 'Urgent' : 'Planned' }} · {{ r.when }}</small></span>
            <span class="chipst" :class="statusClass(r.status)">{{ r.status }}</span>
          </button>
        </li>
      </ul>
    </AppModal>

    <AppModal v-model="recentOpen" :title="pickedRecent ? `${pickedRecent.group} · ${pickedRecent.units} ${pickedRecent.units === 1 ? 'unit' : 'units'}` : ''" :sub="pickedRecent?.where">
      <template v-if="pickedRecent">
        <dl class="facts">
          <div><dt>Status</dt><dd><span class="chipst" :class="statusClass(pickedRecent.status)">{{ pickedRecent.status }}</span></dd></div>
          <div><dt>Priority</dt><dd>{{ pickedRecent.urgent ? 'Urgent' : 'Planned' }}</dd></div>
          <div><dt>When</dt><dd>{{ pickedRecent.when }}</dd></div>
        </dl>
        <p class="mnote">Past requests are kept in the audit log. You can start a new search with the same group and units.</p>
      </template>
      <template #footer>
        <button type="button" class="btn" @click="pickedRecent = null">Close</button>
        <button type="button" class="btn btn-primary" @click="pickedRecent && rerun(pickedRecent)"><AppIcon name="search" :size="18" /> Use these details</button>
      </template>
    </AppModal>

    <AppModal v-model="showSources" title="Nearby sources" :sub="`Count of ${stockDay}, unconfirmed. Confirm the shelf before you rely on it.`">
      <ul class="mlist">
        <li v-for="o in nearby" :key="o.id" class="ncard">
          <div class="nt">
            <IconBadge size="lg" tone="solid" :square="o.kind === 'centre'"><AppIcon :name="o.kind" :size="26" /></IconBadge>
            <span class="nb"><b>{{ o.name }}</b><small><AppIcon name="drop" :size="13" /> {{ effective }} <i>·</i> <AppIcon name="clock" :size="13" /> most likely {{ fmtHours(o.p50) }}</small></span>
            <span class="avail" :class="{ part: o.partial }">{{ spareText(o) }}</span>
          </div>
          <button type="button" class="contact" :class="{ done: contacted.includes(o.id) }" @click="showSources = false; contact = o"><AppIcon :name="contacted.includes(o.id) ? 'check' : 'call'" :size="18" /> {{ contacted.includes(o.id) ? 'Contacted' : 'Contact site' }}</button>
        </li>
      </ul>
    </AppModal>

    <AppModal v-model="contactOpen" :title="contact ? `Contact ${contact.name}` : ''" sub="Call or text the site, then mark it here so the team can see.">
      <template v-if="contact">
        <p class="mnote">The site's phone number will come from the site register once it is connected. Until then, use the number your hospital already has.</p>
        <div class="smsbox">
          <span><small>SMS request</small><b>{{ smsText }}</b></span>
          <button type="button" class="btn" @click="copy(smsText)"><AppIcon name="copy" :size="18" /> Copy</button>
        </div>
        <p class="mnote">Say you need {{ units }} {{ units === 1 ? 'unit' : 'units' }} of {{ effective }}. Ask them to confirm the units are on the shelf before dispatch.</p>
      </template>
      <template #footer>
        <button type="button" class="btn" @click="contact = null">Not now</button>
        <button type="button" class="btn btn-primary" @click="markContacted"><AppIcon name="check" :size="18" /> Mark contacted</button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.page { width: 100%; max-width: 1180px; margin: 0 auto; padding: 14px 16px 28px; display: grid; gap: 16px; align-content: start; }
.greet { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.hi { margin: 0; font-size: 22px; font-weight: 800; color: var(--ink-deep); }
.where { margin: 4px 0 0; display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: #44545f; }
.where svg { color: var(--primary-500); flex-shrink: 0; }
.bell { position: relative; width: 46px; height: 46px; flex-shrink: 0; border-radius: 99px; background: #fff; border: 1.5px solid #d8e4e2; display: grid; place-items: center; color: var(--primary-700); }
.bell i { position: absolute; top: 9px; right: 11px; width: 9px; height: 9px; border-radius: 99px; background: var(--primary-500); border: 2px solid #fff; }

.hero { position: relative; display: flex; align-items: center; gap: 14px; padding: 22px 22px 22px 24px; background: linear-gradient(135deg, #e4f2f0 0%, #d6e8e5 100%); border: 1.5px solid var(--primary-500); overflow: hidden; }
.hc { flex: 1; min-width: 0; position: relative; z-index: 1; }
.hero h1 { margin: 0; font-size: clamp(26px, 5vw, 38px); line-height: 1; letter-spacing: -0.03em; font-weight: 800; text-transform: uppercase; color: var(--primary-600); }
.hero p { margin: 10px 0 0; font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #44545f; max-width: 420px; }
.sosbtn { margin-top: 16px; display: inline-flex; align-items: center; gap: 8px; min-height: 46px; padding: 0 18px; border-radius: 99px; background: #fff; border: 1.5px solid var(--blood-500); color: var(--blood-700); font-weight: 800; font-size: 14px; box-shadow: 0 8px 18px rgba(179, 23, 30, 0.16); }
.bgphoto { position: absolute; top: 0; right: 0; bottom: 0; width: 62%; z-index: 0; -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 55%); mask-image: linear-gradient(90deg, transparent 0%, #000 55%); }
.bgphoto img { width: 100%; height: 100%; object-fit: cover; object-position: 30% 60%; filter: saturate(1.05) contrast(1.02); mix-blend-mode: multiply; }
.bgphoto::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(10, 107, 98, 0) 40%, rgba(6, 74, 68, 0.28)); }

.form { padding: var(--s-5) var(--s-4); display: flex; flex-direction: column; gap: var(--s-4); }
.form h2, .side h2 { margin: 0; font-size: 18px; font-weight: 800; color: var(--ink-deep); }
.lbl { display: block; font-size: 13px; font-weight: 800; color: var(--ink-deep); margin-bottom: 10px; }
.unk-note { margin: 12px 0 0; display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; border-radius: var(--r-md); background: var(--amber-50); color: var(--amber-900); font-size: 13px; font-weight: 600; line-height: 1.45; }
.unk-note svg { flex-shrink: 0; color: var(--amber-700); margin-top: 1px; }
.rows { border: 1.5px solid #d8e4e2; border-radius: var(--r-lg); background: #fff; overflow: hidden; }
.row { display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
.row + .row { border-top: 1px solid #e2ece9; }
.rl { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rl b { font-size: 14.5px; color: var(--ink); }
.rl small { font-size: var(--fs-caption); font-weight: 600; color: #5d6d78; margin-top: 1px; }
.step { display: inline-flex; align-items: center; gap: 4px; }
.step button { width: 44px; height: 44px; border-radius: 99px; border: 1.5px solid #c9dbd8; background: #fff; font-size: 20px; font-weight: 700; color: var(--primary-700); }
.step output { min-width: 40px; text-align: center; font-size: 20px; font-weight: 800; }
.hosp { font-size: 13px; font-weight: 800; color: var(--primary-700); text-align: right; max-width: 130px; }
.pickfac { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; min-width: 0; max-width: 58%; }
.retry { border: 0; background: none; padding: 0; font-size: 12px; font-weight: 800; color: var(--primary-700); text-decoration: underline; }
.pnote { margin: -6px 0 0; display: flex; align-items: flex-start; gap: 8px; font-size: var(--fs-caption); font-weight: 600; color: #44545f; line-height: 1.45; }
.pnote svg { color: var(--primary-500); flex-shrink: 0; margin-top: 1px; }
.go { min-height: 56px; font-size: 16px; }
.go:disabled { opacity: 0.7; cursor: progress; }
.sms { margin: 0; display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: var(--r-md); background: var(--azure-50); color: var(--azure-600); font-size: var(--fs-caption); font-weight: 600; }
.sms span { color: var(--ink); line-height: 1.35; }

.side { display: grid; gap: 18px; align-content: start; }
.sh { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.stockday { margin: -4px 0 10px; font-size: var(--fs-caption); font-weight: 700; color: #5d6d78; }
.quiet { margin: 0; padding: 14px 16px; border-radius: var(--r-lg); background: #fff; border: 1.5px dashed #d8e4e2; font-size: 13.5px; font-weight: 600; color: #44545f; line-height: 1.45; }
.recent, .near { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.rcard { width: 100%; text-align: left; font: inherit; cursor: pointer; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-lg); background: #fff; border: 1.5px solid #d8e4e2; text-decoration: none; color: inherit; transition: transform 0.2s ease, box-shadow 0.2s ease; }
.rcard:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(6, 74, 68, 0.12); }
.rg b { font-size: 17px; font-weight: 800; }
.rb { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rb b { font-size: 14.5px; }
.rb small { font-size: var(--fs-caption); font-weight: 600; color: #5d6d78; margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rb .when { display: flex; align-items: center; gap: 6px; }
.dot { width: 8px; height: 8px; border-radius: 99px; background: var(--blood-500); display: inline-block; }
.chipst { padding: 5px 11px; border-radius: 99px; font-size: 11.5px; font-weight: 800; white-space: nowrap; }
.st-red { background: var(--blood-50); color: var(--blood-700); }
.st-teal { background: var(--teal-50); color: var(--teal-600); }
.st-amber { background: var(--amber-50); color: var(--amber-700); }
.st-grey { background: #eceff1; color: var(--slate); }
.ncard { padding: var(--s-4); border-radius: var(--r-lg); background: #fff; border: 1.5px solid #d8e4e2; display: flex; flex-direction: column; gap: 12px; }
.nt { display: flex; align-items: center; gap: 12px; }
.nb { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.nb b { font-size: 14.5px; color: var(--ink); }
.nb small { display: flex; align-items: center; gap: 5px; font-size: var(--fs-caption); font-weight: 700; color: #5d6d78; margin-top: 3px; flex-wrap: wrap; }
.nb small svg { color: var(--primary-500); }
.nb small i { font-style: normal; opacity: 0.5; }
.avail { font-size: var(--fs-caption); font-weight: 800; color: var(--teal-600); text-align: right; line-height: 1.3; max-width: 90px; }
.avail.part { color: var(--amber-700); }
.contact { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 46px; border-radius: 99px; background: var(--primary-50); color: var(--primary-700); font-weight: 800; font-size: 14px; text-decoration: none; border: 1.5px solid #b9d9d4; }

@media (max-width: 520px) {
  .rl small { display: none; }
  .row { padding: 10px 12px; gap: 10px; }
  .hero { padding: 18px 16px 18px 18px; gap: 10px; }
  .bgphoto { width: 50%; opacity: 0.85; -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 45%); mask-image: linear-gradient(90deg, transparent 0%, #000 45%); }
  .hero h1, .hero p { max-width: 60%; }
  .hero h1 { font-size: 26px; }
  .long { display: none; }
  .sosbtn { max-width: 100%; }
  .sosbtn { font-size: 13px; padding: 0 14px; line-height: 1.2; text-align: left; }
  .hosp { max-width: 120px; }
  .pickfac { max-width: 64%; }
}
@media (min-width: 1000px) {
  .page { grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr); gap: 20px 28px; padding: 22px 24px 40px; }
  .greet, .hero { grid-column: 1 / -1; }
  .side { position: sticky; top: 96px; }
  .bgphoto { width: 52%; }
  .hero { padding: 28px 36px; }
  .hero p { font-size: 16px; }
}
.needhint { margin: 0; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-lg); background: var(--amber-50); color: var(--amber-900); font-size: var(--fs-caption); font-weight: 700; line-height: 1.4; }

.more { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 14px; border-radius: 99px; border: 1.5px solid #b9d9d4; background: var(--primary-50); color: var(--primary-700); font-weight: 800; font-size: 13px; transition: transform 0.2s ease, background 0.2s ease; }
.more:hover { transform: translateY(-1px); background: #d6e8e5; }
.contact { width: 100%; font: inherit; cursor: pointer; transition: transform 0.15s ease, background 0.2s ease; }
.contact:active { transform: scale(0.98); }
.contact.done { background: var(--teal-50); border-color: #9fd6cd; color: var(--teal-600); }
.flip { animation: flip 0.35s cubic-bezier(0.2, 1.1, 0.3, 1); }
@keyframes flip { from { opacity: 0; transform: translateY(-10px) scale(0.8); } to { opacity: 1; transform: none; } }
.mlist { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.facts { margin: 0 0 12px; display: grid; gap: 8px; }
.facts div { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-radius: var(--r-md); background: #fff; border: 1.5px solid #d8e4e2; }
.facts dt { font-size: 13px; font-weight: 700; color: #5d6d78; }
.facts dd { margin: 0; font-weight: 800; color: var(--ink); font-size: 14.5px; }
.mnote { margin: 0 0 12px; font-size: 14px; line-height: 1.55; font-weight: 500; color: #44545f; }
.smsbox { display: flex; align-items: center; gap: 12px; justify-content: space-between; padding: 12px 12px 12px 18px; border-radius: var(--r-md); background: var(--azure-50); margin-bottom: 12px; }
.smsbox span { display: flex; flex-direction: column; }
.smsbox small { font-size: 12px; font-weight: 800; color: var(--azure-600); text-transform: uppercase; letter-spacing: 0.06em; }
.smsbox b { font-size: 17px; color: var(--ink); letter-spacing: 0.02em; }
</style>
