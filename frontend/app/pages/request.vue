<script setup lang="ts">
import { mockRank, RECENT } from '~/utils/mock'

useHead({ title: 'New request · Blood Dispatch' })

const route = useRoute()
const { search } = useDispatch()
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
  form.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const submit = () => search({ group: effective.value, units: units.value, product: product.value, limitH: limitH.value, unknownGroup: unknown.value })
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
        <button type="button" class="sosbtn" @click="sos"><AppIcon name="drop" :size="18" /> Group unknown? Request group O</button>
      </div>
      <div class="thumb" aria-hidden="true"><img :src="img('hand-vial.jpg')" alt=""></div>
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
          <select v-model="product" class="sel" aria-label="Product"><option>Red cells</option><option>Whole blood</option></select>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="units" :size="22" /></IconBadge>
          <span class="rl"><b>Units needed</b><small>Bags for this patient</small></span>
          <span class="step"><button type="button" aria-label="One fewer unit" @click="units = Math.max(1, units - 1)">−</button><output class="tnum" aria-live="polite">{{ units }}</output><button type="button" aria-label="One more unit" @click="units = Math.min(10, units + 1)">+</button></span>
        </div>
        <div class="row">
          <IconBadge><AppIcon name="clock" :size="22" /></IconBadge>
          <span class="rl"><b>Longest wait</b><small>Used to flag a wait that is too long</small></span>
          <span class="step"><button type="button" aria-label="Shorter limit" @click="limitH = Math.max(1, limitH - 1)">−</button><output class="tnum">{{ limitH }}h</output><button type="button" aria-label="Longer limit" @click="limitH = Math.min(12, limitH + 1)">+</button></span>
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
        <div class="sh"><h2>Recent requests</h2></div>
        <ul class="recent">
          <li v-for="r in RECENT" :key="r.when">
            <NuxtLink to="/results?group=B%2B&units=2&limit=3&demo=1" class="rcard">
              <IconBadge size="lg" class="rg"><b>{{ r.group }}</b></IconBadge>
              <span class="rb">
                <b>{{ r.units }} {{ r.units === 1 ? 'unit' : 'units' }} needed</b>
                <small>{{ r.where }}</small>
                <small class="when"><i v-if="r.urgent" class="dot" />{{ r.urgent ? 'Urgent' : 'Planned' }} · {{ r.when }}</small>
              </span>
              <span class="chipst" :class="statusClass(r.status)">{{ r.status }}</span>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <section>
        <div class="sh"><h2>Nearby sources</h2><span>Yesterday's stock</span></div>
        <ul class="near">
          <li v-for="o in nearby" :key="o.id" class="ncard rise">
            <div class="nt">
              <IconBadge size="lg" tone="solid" :square="o.kind === 'centre'"><AppIcon :name="o.kind" :size="26" /></IconBadge>
              <span class="nb">
                <b>{{ o.name }}</b>
                <small><AppIcon name="drop" :size="13" /> {{ effective }} <i>·</i> <AppIcon name="route" :size="13" /> {{ fmtHours(o.p50) }} away</small>
              </span>
              <span class="avail">{{ o.avail }} units<br>available</span>
            </div>
            <a href="#" class="contact"><AppIcon name="call" :size="18" /> Contact site</a>
          </li>
        </ul>
      </section>
    </aside>
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
.thumb { width: 96px; height: 96px; flex-shrink: 0; border-radius: 99px; overflow: hidden; border: 4px solid #fff; box-shadow: 0 12px 26px rgba(126, 16, 21, 0.25); position: relative; background: #f3c9c4; }
.thumb img { position: absolute; width: 330%; left: -115%; top: -257%; max-width: none; height: auto; filter: sepia(0.4) saturate(1.5) hue-rotate(-14deg) brightness(1.1); }

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
.rcard { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-lg); background: #fff; border: 1.5px solid #ecd5d1; text-decoration: none; color: inherit; transition: transform 0.2s ease, box-shadow 0.2s ease; }
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
  .thumb { width: 78px; height: 78px; align-self: flex-start; }
  .sosbtn { font-size: 13px; padding: 0 14px; line-height: 1.2; text-align: left; }
  .hosp { max-width: 120px; }
}
@media (min-width: 1000px) {
  .page { grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr); gap: 20px 28px; padding: 22px 24px 40px; }
  .greet, .hero { grid-column: 1 / -1; }
  .side { position: sticky; top: 96px; }
  .thumb { width: 150px; height: 150px; }
  .hero { padding: 28px 36px; }
  .hero p { font-size: 16px; }
}
.needhint { margin: 0; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-4); border-radius: var(--r-lg); background: var(--amber-50); color: var(--amber-900); font-size: var(--fs-caption); font-weight: 700; line-height: 1.4; }
</style>
