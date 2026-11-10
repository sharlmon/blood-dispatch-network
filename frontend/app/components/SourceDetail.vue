<script setup lang="ts">
// "Why this source": the engine's reason sentences verbatim, its flags, what the site can spare
// (by blood group, the units it would lend) and what it keeps, the dated stock count, and the
// arrival clock counted from the request time.
import type { Option } from '~/utils/engine'
import { stockAgeDays, stockCountText } from '~/utils/engine'
import { requestClock, requestNeedsDate } from '~/utils/format'

const props = defineProps<{
  option: Option
  /** request time as the engine echoed it (EAT) */
  requestedAt: string
  /** when the request was logged (null for a preview): the clocks carry their day when the two differ */
  createdAt?: string | null
  /** the ranking's as_of_stock_date */
  asOfStockDate: string
  need: number
  compatibilityNote: string
  /** heading level 3 inside a page section, hidden when the parent already names the source */
  compact?: boolean
}>()

const o = computed(() => props.option)
const where = computed(() => {
  const bits = [o.value.roadKm != null ? `${fmtKm(o.value.roadKm)} by road` : o.value.travelHoursMap != null ? `${fmtHours(o.value.travelHoursMap)} drive on the map` : null, o.value.county]
  return bits.filter(Boolean).join(' · ')
})
// One bar for the share (stock_seen can be ~100 units), never one segment per unit.
const share = computed(() => (o.value.stockSeen > 0 ? Math.min(100, (o.value.spare / o.value.stockSeen) * 100) : 0))
const groups = computed(() => spareGroupsText(o.value.spareByGroup))
const dated = computed(() => requestNeedsDate(props.requestedAt, props.createdAt ?? null))
const stockLine = computed(() => stockCountText(props.requestedAt, props.asOfStockDate))
const stockOld = computed(() => stockAgeDays(props.requestedAt, props.asOfStockDate) > 1)
</script>

<template>
  <div class="sd">
    <div v-if="!compact" class="dh">
      <IconBadge size="lg" tone="solid" :square="o.kind === 'centre'"><AppIcon :name="o.kind" :size="26" /></IconBadge>
      <span><strong>{{ o.name }}</strong><small>{{ o.kind === 'hospital' ? 'Hospital' : 'Regional centre' }}<template v-if="where"> · {{ where }}</template></small></span>
    </div>

    <p class="eta">
      <AppIcon name="clock" :size="20" />
      <span>Most likely arrives about <b class="tnum">{{ clockAfter(requestedAt, o.p50, dated) }}</b></span>
      <small>8 in 10 arrive between {{ clockAfter(requestedAt, o.p10, dated) }} and {{ clockAfter(requestedAt, o.p90, dated) }}, counted from the request at {{ requestClock(requestedAt, createdAt ?? null) }}</small>
    </p>

    <ul v-if="o.flags.length" class="flags" aria-label="Flags">
      <li v-for="f in o.flags" :key="f" :class="f"><AppIcon :name="f === 'partial' ? 'units' : f === 'low_connectivity_2g' ? 'call' : f === 'group_unknown_emergency_O' ? 'groupO' : 'warning'" :size="15" /> {{ flagLabel(f) }}</li>
    </ul>

    <h3>Why this source</h3>
    <ul class="why">
      <li v-for="(r, i) in o.reasons" :key="i"><span class="tick"><AppIcon name="check" :size="14" /></span>{{ r }}</li>
    </ul>

    <div class="kept">
      <div class="kh"><small>{{ o.kind === 'hospital' ? 'What it can spare' : 'What it can share' }}</small><small v-if="groups">Spare by group: {{ groups }}</small></div>
      <template v-if="o.kind === 'hospital'">
        <div class="big"><b class="tnum">{{ o.spare }} of {{ o.stockSeen }}</b><span>spare to share</span></div>
        <div class="bar" role="img" :aria-label="`${o.spare} of ${o.stockSeen} compatible units are spare`"><i :style="{ width: share + '%' }" /></div>
        <p>It keeps the rest: its usual level, at least 2 units per group, and its O− reserve.</p>
      </template>
      <template v-else>
        <div class="big"><b class="tnum">{{ o.spare }}</b><span>All compatible stock can be shared</span></div>
        <p>A regional centre has no safety stock of its own to protect.</p>
      </template>
      <p v-if="o.nearExpiry > 0" class="exp"><AppIcon name="clock" :size="14" /> {{ o.nearExpiry }} {{ o.nearExpiry === 1 ? 'unit' : 'units' }} near expiry: sharing avoids waste.</p>
      <p v-if="o.partial" class="exp"><AppIcon name="units" :size="14" /> Covers {{ o.spare }} of the {{ need }} units needed.</p>
      <p :class="{ old: stockOld }">{{ stockLine }}, unconfirmed until the site confirms. It confirms the shelf within {{ CONFIRM_TIMEOUT_MIN }} minutes, or you ask the next source.</p>
    </div>

    <p class="compat">{{ compatibilityNote }}</p>
  </div>
</template>

<style scoped>
.sd { display: flex; flex-direction: column; }
.dh { display: flex; align-items: center; gap: 12px; }
.dh > span:last-child { display: flex; flex-direction: column; min-width: 0; }
.dh strong { font-size: 17px; color: #12202b; }
.dh small { font-size: 12.5px; font-weight: 600; color: #44545f; }
.eta { margin: 18px 0 0; display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; align-items: center; padding: 12px 14px; border-radius: 22px; background: var(--teal-50); color: #064e46; font-size: 13.5px; font-weight: 700; }
.eta svg { color: var(--teal-600); grid-row: span 2; }
.eta b { font-size: 19px; color: var(--ink); }
.eta small { font-size: 12px; font-weight: 600; color: #3f6f69; line-height: 1.4; }
.flags { list-style: none; margin: 14px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.flags li { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border-radius: 99px; background: var(--amber-50); color: var(--amber-900); font-size: 12px; font-weight: 800; }
.flags li svg { color: var(--amber-700); }
.flags li.group_unknown_emergency_O { background: var(--blood-50); color: var(--blood-700); }
.flags li.group_unknown_emergency_O svg { color: var(--blood-500); }
h3 { margin: 22px 0 12px; font-size: 11.5px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #5d6d78; }
.why { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.why li { display: flex; gap: 12px; align-items: flex-start; font-size: 14px; font-weight: 600; line-height: 1.45; color: var(--ink-deep); }
.tick { width: 22px; height: 22px; border-radius: 99px; background: var(--teal-50); color: var(--teal-600); display: grid; place-items: center; flex-shrink: 0; margin-top: 1px; }
.kept { margin-top: 22px; padding: var(--s-4); border-radius: var(--r-lg); background: var(--primary-50); }
.kh { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 2px 10px; }
.kh small { font-size: 12px; font-weight: 800; color: #5d6d78; }
.big { display: flex; align-items: baseline; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
.big b { font-size: 30px; color: var(--primary-500); }
.big span { font-size: 13px; font-weight: 600; color: #44545f; }
.bar { height: 10px; margin-top: 10px; border-radius: 99px; background: #c9dbd8; overflow: hidden; }
.bar i { display: block; height: 100%; min-width: 4px; border-radius: 99px; background: var(--primary-500); transform-origin: left; animation: grow 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.kept p { margin: 10px 0 0; font-size: 12px; font-weight: 600; color: #44545f; line-height: 1.45; }
.kept p.exp { display: flex; align-items: center; gap: 6px; color: var(--ink-deep); font-weight: 700; }
.kept p.exp svg { color: var(--primary-500); flex-shrink: 0; }
.kept p.old { color: var(--amber-900); font-weight: 700; }
.compat { margin: 14px 0 0; font-size: 11.5px; font-weight: 600; color: var(--slate); line-height: 1.45; }
</style>
