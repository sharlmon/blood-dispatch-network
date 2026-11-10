<script setup lang="ts">
import { mockRank, RECENT } from '~/utils/mock'

useHead({ title: 'New request · Blood Dispatch' })

const route = useRoute()
const { search } = useDispatch()
const { toast } = useToast()
const { firstName, hospital } = useSite()
const img = useImg()

const group = ref(route.query.sos ? 'Unknown' : 'B+')
const product = ref('Red cells')
const units = ref(2)
const limitH = ref(3)

const hello = ref('Hello')
onMounted(() => {
  const h = new Date().getHours()
  hello.value = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
})

const unknown = computed(() => group.value === 'Unknown')
const effective = computed(() => (unknown.value ? 'O' : group.value))
// Live preview of who could spare this, before the full search.
const nearby = computed(() => mockRank({ id: '#n', group: effective.value, units: units.value, product: product.value, limitH: limitH.value, openedAt: '00:00' }).options)

const form = ref<HTMLElement | null>(null)
function sos() {
  group.value = 'Unknown'
  toast({ tone: 'warn', title: 'Group O will be requested', body: 'Unknown group: only group O, per hospital protocol.' })
  form.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const stepUnits = (d: number) => {
  const n = Math.min(10, Math.max(1, units.value + d))
  if (n === units.value) toast({ tone: 'info', title: d > 0 ? 'Maximum is 10 units' : 'At least 1 unit', ms: 2200 })
  units.value = n
}
const stepLimit = (d: number) => {
  const n = Math.min(12, Math.max(1, limitH.value + d))
  if (n === limitH.value) toast({ tone: 'info', title: d > 0 ? 'Longest limit is 12 hours' : 'Shortest limit is 1 hour', ms: 2200 })
  limitH.value = n
}

// Lists stay short on the page; the full list opens in a modal.
const showRecent = ref(false)
const showSources = ref(false)
const pickedRecent = ref<(typeof RECENT)[number] | null>(null)
const recentOpen = computed({ get: () => !!pickedRecent.value, set: (v) => { if (!v) pickedRecent.value = null } })
const contact = ref<(typeof nearby.value)[number] | null>(null)
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
const submit = () => { toast({ tone: 'info', title: 'Finding sources', body: `${effective.value}, ${units.value} ${units.value === 1 ? 'unit' : 'units'}`, ms: 2400 }); return search({ group: effective.value, units: units.value, product: product.value, limitH: limitH.value, unknownGroup: unknown.value }) }
const statusClass = (s: string) => ({ Dispatched: 'st-red', Arrived: 'st-teal', Escalated: 'st-amber' }[s] ?? '')
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
        <p class="where"><AppIcon name="pin" :size="16" /> {{ hospital }}</p>
      </div>
      <NuxtLink to="/track" class="bell" aria-label="Notifications"><AppIcon name="bell" :size="22" /><i /></NuxtLink>
    </header>

    <section class="hero organic-card">
      <div class="hc">
        <h1>Urgently need blood?</h1>
        <p>Tell us what the patient needs. We find every source that can spare it, and when it will really arrive.</p>
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
          <ThemedSelect v-model="product" label="Product" :options="[{ value: 'Red cells', hint: 'Most requests' }, { value: 'Whole blood', hint: 'When whole blood is needed' }]" />
        </div>
        <div class="row">
          <IconBadge><AppIcon name="units" :size="22" /></IconBadge>
          <span class="rl"><b>Units needed</b><small>Bags for this patient</small></span>
          <span class="step"><button type="button" aria-label="One fewer unit" @click="stepUnits(-1)">−</button><output :key="units" class="tnum flip" aria-live="polite">{{ units }}</output><button type="button" aria-label="One more unit" @click="stepUnits(1)">+</button></span>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="clock" :size="22" /></IconBadge>
          <span class="rl"><b>Longest wait</b><small>Used to flag a wait that is too long</small></span>
          <span class="step"><button type="button" aria-label="Shorter limit" @click="stepLimit(-1)">−</button><output :key="limitH" class="tnum flip">{{ limitH }}h</output><button type="button" aria-label="Longer limit" @click="stepLimit(1)">+</button></span>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="hospital" :size="22" /></IconBadge>
          <span class="rl"><b>Requesting hospital</b><small>From your account</small></span>
          <span class="hosp">{{ hospital }}</span>
        </div>
      </div>

      <button type="submit" class="btn btn-primary go"><AppIcon name="search" /> Find sources</button>
      <p class="sms"><AppIcon name="sms" :size="22" /><span>No data? Text <b>{{ effective }} {{ units }} RBC {{ limitH }}H</b> to [SHORTCODE].</span></p>
      <SafetyNote />
    </form>

    <aside class="side">
      <section>
        <div class="sh"><h2>Recent requests</h2><button type="button" class="more" @click="showRecent = true"><AppIcon name="list" :size="16" /> View all {{ RECENT.length }}</button></div>
        <ul class="recent">
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
        <div class="sh"><h2>Nearby sources</h2><button v-if="nearby.length > 2" type="button" class="more" @click="showSources = true"><AppIcon name="list" :size="16" /> View all {{ nearby.length }}</button><span v-else>Yesterday's stock</span></div>
        <ul class="near">
          <li v-for="(o, i) in nearby.slice(0, 2)" :key="o.id" class="ncard rise" :style="{ '--d': i * 80 + 'ms' }">
            <div class="nt">
              <IconBadge size="lg" tone="solid" :square="o.kind === 'centre'"><AppIcon :name="o.kind" :size="26" /></IconBadge>
              <span class="nb">
                <b>{{ o.name }}</b>
                <small><AppIcon name="drop" :size="13" /> {{ effective }} <i>·</i> <AppIcon name="route" :size="13" /> {{ fmtHours(o.p50) }} away</small>
              </span>
              <span class="avail">{{ o.avail }} units<br>available</span>
            </div>
            <button type="button" class="contact" :class="{ done: contacted.includes(o.id) }" @click="contact = o"><AppIcon :name="contacted.includes(o.id) ? 'check' : 'call'" :size="18" /> {{ contacted.includes(o.id) ? 'Contacted' : 'Contact site' }}</button>
          </li>
        </ul>
      </section>
    </aside>

    <AppModal v-model="showRecent" title="Recent requests" :sub="`${RECENT.length} in the last week`">
      <ul class="mlist">
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

    <AppModal v-model="showSources" title="Nearby sources" sub="Based on yesterday's stock. Confirm the shelf before you rely on it.">
      <ul class="mlist">
        <li v-for="o in nearby" :key="o.id" class="ncard">
          <div class="nt">
            <IconBadge size="lg" tone="solid" :square="o.kind === 'centre'"><AppIcon :name="o.kind" :size="26" /></IconBadge>
            <span class="nb"><b>{{ o.name }}</b><small><AppIcon name="drop" :size="13" /> {{ effective }} <i>·</i> <AppIcon name="route" :size="13" /> {{ fmtHours(o.p50) }} away</small></span>
            <span class="avail">{{ o.avail }} units<br>available</span>
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
.greet { display: flex; align-items: center; justify-content: space-between; }
.hi { margin: 0; font-size: 22px; font-weight: 800; color: var(--wine); }
.where { margin: 4px 0 0; display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: #5a3c3f; }
.where svg { color: var(--blood-500); }
.bell { position: relative; width: 46px; height: 46px; border-radius: 99px; background: #fff; border: 1.5px solid #ecd5d1; display: grid; place-items: center; color: var(--blood-700); }
.bell i { position: absolute; top: 9px; right: 11px; width: 9px; height: 9px; border-radius: 99px; background: var(--blood-500); border: 2px solid #fff; }

.hero { position: relative; display: flex; align-items: center; gap: 14px; padding: 22px 22px 22px 24px; background: linear-gradient(135deg, #fdecea 0%, #f9d3ce 100%); border: 1.5px solid var(--blood-500); overflow: hidden; }
.hc { flex: 1; min-width: 0; position: relative; z-index: 1; }
.hero h1 { margin: 0; font-size: clamp(26px, 5vw, 38px); line-height: 1; letter-spacing: -0.03em; font-weight: 800; text-transform: uppercase; color: var(--blood-600); }
.hero p { margin: 10px 0 0; font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #5a3c3f; max-width: 420px; }
.sosbtn { margin-top: 16px; display: inline-flex; align-items: center; gap: 8px; min-height: 46px; padding: 0 18px; border-radius: 99px; background: #fff; border: 1.5px solid var(--blood-500); color: var(--blood-700); font-weight: 800; font-size: 14px; box-shadow: 0 8px 18px rgba(179, 23, 30, 0.18); }
.bgphoto { position: absolute; top: 0; right: 0; bottom: 0; width: 62%; z-index: 0; -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 55%); mask-image: linear-gradient(90deg, transparent 0%, #000 55%); }
.bgphoto img { width: 100%; height: 100%; object-fit: cover; object-position: 30% 60%; filter: sepia(0.35) saturate(1.4) hue-rotate(-12deg) contrast(1.05); mix-blend-mode: multiply; }
.bgphoto::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(179, 23, 30, 0) 40%, rgba(126, 16, 21, 0.28)); }

.form { padding: var(--s-5) var(--s-4); display: flex; flex-direction: column; gap: var(--s-4); }
.form h2, .side h2 { margin: 0; font-size: 18px; font-weight: 800; color: var(--wine); }
.lbl { display: block; font-size: 13px; font-weight: 800; color: var(--wine); margin-bottom: 10px; }
.unk-note { margin: 12px 0 0; display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; border-radius: var(--r-md); background: var(--amber-50); color: var(--amber-900); font-size: 13px; font-weight: 600; line-height: 1.45; }
.unk-note svg { flex-shrink: 0; color: var(--amber-700); margin-top: 1px; }
.rows { border: 1.5px solid #ecd5d1; border-radius: var(--r-lg); background: #fff; overflow: hidden; }
.row { display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
.row + .row { border-top: 1px solid #f0e1de; }
.rl { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rl b { font-size: 14.5px; color: var(--ink); }
.rl small { font-size: var(--fs-caption); font-weight: 600; color: #7a5a5d; margin-top: 1px; }
.sel { appearance: none; min-height: 44px; padding: 0 34px 0 16px; border-radius: 99px; border: 1.5px solid #e6c4c0; font-weight: 800; font-size: 14px; color: var(--blood-700); background: #fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%237e1015' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat right 14px center; }
.step { display: inline-flex; align-items: center; gap: 4px; }
.step button { width: 44px; height: 44px; border-radius: 99px; border: 1.5px solid #e6c4c0; background: #fff; font-size: 20px; font-weight: 700; color: var(--blood-700); }
.step output { min-width: 40px; text-align: center; font-size: 20px; font-weight: 800; }
.hosp { font-size: 13px; font-weight: 800; color: var(--blood-700); text-align: right; max-width: 130px; }
.go { min-height: 56px; font-size: 16px; }
.sms { margin: 0; display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: var(--r-md); background: var(--azure-50); color: var(--azure-600); font-size: var(--fs-caption); font-weight: 600; }
.sms span { color: var(--ink); line-height: 1.35; }

.side { display: grid; gap: 18px; align-content: start; }
.sh { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
.sh span { font-size: var(--fs-caption); font-weight: 700; color: #7a5a5d; }
.recent, .near { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.rcard { width: 100%; text-align: left; font: inherit; cursor: pointer; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-lg); background: #fff; border: 1.5px solid #ecd5d1; text-decoration: none; color: inherit; transition: transform 0.2s ease, box-shadow 0.2s ease; }
.rcard:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(126, 16, 21, 0.12); }
.rg b { font-size: 17px; font-weight: 800; }
.rb { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.rb b { font-size: 14.5px; }
.rb small { font-size: var(--fs-caption); font-weight: 600; color: #7a5a5d; margin-top: 1px; }
.rb .when { display: flex; align-items: center; gap: 6px; }
.dot { width: 8px; height: 8px; border-radius: 99px; background: var(--blood-500); display: inline-block; }
.chipst { padding: 5px 11px; border-radius: 99px; font-size: 11.5px; font-weight: 800; white-space: nowrap; }
.st-red { background: var(--blood-50); color: var(--blood-700); }
.st-teal { background: var(--teal-50); color: var(--teal-600); }
.st-amber { background: var(--amber-50); color: var(--amber-700); }
.ncard { padding: var(--s-4); border-radius: var(--r-lg); background: #fff; border: 1.5px solid #ecd5d1; display: flex; flex-direction: column; gap: 12px; }
.nt { display: flex; align-items: center; gap: 12px; }
.nb { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.nb b { font-size: 14.5px; color: var(--ink); }
.nb small { display: flex; align-items: center; gap: 5px; font-size: var(--fs-caption); font-weight: 700; color: #7a5a5d; margin-top: 3px; flex-wrap: wrap; }
.nb small svg { color: var(--blood-500); }
.nb small i { font-style: normal; opacity: 0.5; }
.avail { font-size: var(--fs-caption); font-weight: 800; color: var(--teal-600); text-align: right; line-height: 1.3; }
.contact { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 46px; border-radius: 99px; background: var(--blood-50); color: var(--blood-700); font-weight: 800; font-size: 14px; text-decoration: none; border: 1.5px solid #f0c0ba; }

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

.more { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 14px; border-radius: 99px; border: 1.5px solid #f0c0ba; background: var(--blood-50); color: var(--blood-700); font-weight: 800; font-size: 13px; transition: transform 0.2s ease, background 0.2s ease; }
.more:hover { transform: translateY(-1px); background: #fbddd9; }
.contact { width: 100%; font: inherit; cursor: pointer; transition: transform 0.15s ease, background 0.2s ease; }
.contact:active { transform: scale(0.98); }
.contact.done { background: var(--teal-50); border-color: #9fd6cd; color: var(--teal-600); }
.flip { animation: flip 0.35s cubic-bezier(0.2, 1.1, 0.3, 1); }
@keyframes flip { from { opacity: 0; transform: translateY(-10px) scale(0.8); } to { opacity: 1; transform: none; } }
.mlist { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.facts { margin: 0 0 12px; display: grid; gap: 8px; }
.facts div { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-radius: var(--r-md); background: #fff; border: 1.5px solid #ecd5d1; }
.facts dt { font-size: 13px; font-weight: 700; color: #7a5a5d; }
.facts dd { margin: 0; font-weight: 800; color: var(--ink); font-size: 14.5px; }
.mnote { margin: 0 0 12px; font-size: 14px; line-height: 1.55; font-weight: 500; color: #5a3c3f; }
.smsbox { display: flex; align-items: center; gap: 12px; justify-content: space-between; padding: 12px 12px 12px 18px; border-radius: var(--r-md); background: var(--azure-50); margin-bottom: 12px; }
.smsbox span { display: flex; flex-direction: column; }
.smsbox small { font-size: 12px; font-weight: 800; color: var(--azure-600); text-transform: uppercase; letter-spacing: 0.06em; }
.smsbox b { font-size: 17px; color: var(--ink); letter-spacing: 0.02em; }
</style>
