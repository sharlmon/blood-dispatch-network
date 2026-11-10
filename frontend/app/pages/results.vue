<script setup lang="ts">
useHead({ title: 'Results · Blood Dispatch' })

const route = useRoute()
const d = useDispatch()
if (!d.request.value) d.loadFromQuery(route.query, route.query.pick as string | undefined)
if (!d.request.value) await navigateTo('/request')

const limitH = computed(() => d.request.value?.limitH ?? 3)
const filter = ref<'all' | 'hospital' | 'centre'>('all')
const shown = computed(() => d.options.value.filter(o => filter.value === 'all' || o.kind === filter.value))
const count = (k: 'hospital' | 'centre') => d.options.value.filter(o => o.kind === k).length
const keptSegments = computed(() => {
  const o = d.selected.value
  return o?.totalN ? Array.from({ length: o.totalN }, (_, i) => i < (o.spareN ?? 0)) : []
})
</script>

<template>
  <div v-if="d.request.value" class="results">
    <div class="map"><SourceMap :options="d.options.value" :selected-id="d.selectedId.value" :pad-top="70" :pad-bottom="40" panels @select="d.select" /></div>

    <span class="mapchip">{{ d.options.value.length }} {{ d.options.value.length === 1 ? 'source' : 'sources' }} {{ d.tooLong.value ? 'available' : 'can cover this' }}</span>

    <section class="panel">
      <div class="grab" aria-hidden="true" />

      <div class="sum" aria-label="Your request">
        <span class="grp">{{ d.request.value.group }}</span>
        <span class="meta">
          <b>{{ d.request.value.units }} units · {{ d.request.value.product.toLowerCase() }}</b>
          <small v-if="d.sooner.value > 0.2 && !d.tooLong.value" class="soon">{{ fmtHours(d.sooner.value) }} sooner than the current way</small>
          <small v-else>{{ d.request.value.id }} · {{ d.request.value.openedAt }} · limit {{ d.request.value.limitH }} h</small>
        </span>
        <span class="urgent">Urgent</span>
        <NuxtLink to="/request" class="edit" aria-label="Edit request"><AppIcon name="edit" :size="20" /></NuxtLink>
      </div>

      <div v-if="d.tooLong.value" class="warn" role="alert">
        <div class="wt"><AppIcon name="warning" :size="26" /><strong>The best source may not arrive in time</strong></div>
        <p>
          Fastest option is most likely {{ fmtHours(d.top.value!.p50) }} and almost certainly
          {{ fmtRange(d.top.value!.p10, d.top.value!.p90) }}. Your limit is {{ d.request.value.limitH }} h. Decide now, a person makes this call.
        </p>
        <button type="button" class="btn btn-dark" @click="d.decide('groupO')"><AppIcon name="groupO" /> Use emergency group O</button>
        <button type="button" class="btn warn-outline" @click="d.decide('transfer')"><AppIcon name="transfer" /> Transfer the patient</button>
      </div>

      <div v-else class="banner">
        <AppIcon name="clock" :size="24" />
        <span>Today's way: Central Blood Centre, about 4 h, no range.</span>
      </div>

      <div class="filters" role="group" aria-label="Filter sources">
        <button type="button" :class="{ on: filter === 'all' }" @click="filter = 'all'">All {{ d.options.value.length }}</button>
        <button type="button" :class="{ on: filter === 'hospital' }" @click="filter = 'hospital'">Hospitals {{ count('hospital') }}</button>
        <button type="button" :class="{ on: filter === 'centre' }" @click="filter = 'centre'">Centres {{ count('centre') }}</button>
        <span class="stock">Yesterday's stock</span>
      </div>

      <ul class="list">
        <li v-for="(o, i) in shown" :key="o.id" class="rise" :style="{ '--d': i * 90 + 'ms' }">
          <SourceCard :option="o" :rank="d.options.value.indexOf(o) + 1" :selected="o.id === d.selectedId.value" :limit-h="limitH" :fastest="d.options.value[0]?.id === o.id" @select="d.select(o.id)" />
        </li>
      </ul>

      <div class="cta">
        <button type="button" class="btn" :class="d.tooLong.value ? 'btn-outline-blood' : 'btn-primary'" :disabled="!d.selected.value" @click="d.confirmSelection()">
          Request from {{ d.selected.value?.name.split(' ').slice(0, 2).join(' ') }}{{ d.tooLong.value ? ' anyway' : '' }}
        </button>
        <SafetyNote />
      </div>
    </section>

    <aside v-if="d.selected.value" class="detail" aria-label="Why this source">
      <div class="dh">
        <span class="di" :class="d.selected.value.kind"><AppIcon :name="d.selected.value.kind" :size="26" /></span>
        <span><strong>{{ d.selected.value.name }}</strong><small>{{ d.selected.value.kind === 'hospital' ? 'Hospital' : 'Centre' }} · {{ d.selected.value.km }} km by road</small></span>
      </div>
      <h3>Why this source</h3>
      <ul class="why">
        <li v-for="r in d.selected.value.reasons" :key="r"><span class="tick"><AppIcon name="check" :size="14" /></span>{{ r }}</li>
      </ul>
      <div class="kept">
        <div class="kh"><small>Stock kept for itself</small><small>{{ d.selected.value.kind === 'hospital' ? `${d.request.value.group.endsWith('−') ? 'O−' : 'B+'} units` : 'centre' }}</small></div>
        <template v-if="keptSegments.length">
          <div class="big"><b class="tnum">{{ d.selected.value.spareN }} of {{ d.selected.value.totalN }}</b><span>spare to share</span></div>
          <div class="segs"><i v-for="(on, i) in keptSegments" :key="i" :class="{ on }" /></div>
        </template>
        <div v-else class="big"><b>All spare</b><span>compatible units</span></div>
        <p>{{ d.selected.value.kept }} The supplier confirms the shelf within 10 minutes, or we ask the next source.</p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.results { position: relative; height: calc(100dvh - var(--header-h) - 86px); min-height: 560px; overflow: hidden; background: var(--fog); margin-top: 6px; }
.map { position: absolute; inset: 0 0 auto 0; height: 34vh; }
.mapchip { display: none; }
.panel { position: absolute; left: 0; right: 0; bottom: 0; top: 28vh; padding: 10px 16px 12px; border-radius: 40px 44px 0 0; background: rgba(255, 255, 255, 0.97); box-shadow: 0 -14px 40px rgba(126, 16, 21, 0.2); display: flex; flex-direction: column; gap: 10px; overflow-y: auto; z-index: 5; }
.grab { width: 44px; height: 5px; border-radius: 99px; background: #e6c4c0; margin: 0 auto 2px; flex-shrink: 0; }
.sum { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 26px; background: linear-gradient(180deg, #fdecea, #fbe0dc); flex-shrink: 0; }
.grp { font-size: 44px; line-height: 1; font-weight: 800; color: var(--blood-500); letter-spacing: -0.03em; }
.meta { flex: 1; min-width: 0; display: flex; flex-direction: column; font-size: 16px; }
.meta small { font-size: 12px; font-weight: 700; color: #5a3c3f; margin-top: 3px; }
.meta small.soon { color: var(--teal-600); }
.urgent { padding: 5px 11px; border-radius: 99px; background: var(--blood-500); color: #fff; font-size: 11px; font-weight: 800; }
.edit { display: none; width: 44px; height: 44px; border-radius: 99px; border: 1.5px solid #e6c4c0; background: #fff; place-items: center; color: var(--blood-700); }
.banner { display: none; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 22px; background: var(--teal-50); color: #064e46; font-size: 14px; font-weight: 700; line-height: 1.4; }
.banner svg { color: var(--teal-600); flex-shrink: 0; }
.filters { display: none; align-items: center; gap: 8px; }
.filters button { padding: 8px 16px; border-radius: 99px; border: 1.5px solid #e6c4c0; background: #fff; color: #5a3c3f; font-size: 13px; font-weight: 800; }
.filters button.on { background: #1b1b1f; border-color: #1b1b1f; color: #fff; }
.stock { margin-left: auto; font-size: 12px; font-weight: 700; color: #7a5a5d; }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; padding-top: 6px; }
.cta { margin-top: auto; display: flex; flex-direction: column; gap: 8px; padding-top: 6px; }
.cta .btn { min-height: 52px; }
.warn { background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: 26px; padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; color: var(--amber-900); flex-shrink: 0; }
.wt { display: flex; align-items: center; gap: 10px; color: var(--amber-700); }
.wt strong { font-size: 17px; line-height: 1.2; color: var(--amber-900); }
.warn p { margin: 0; font-size: 13.5px; line-height: 1.5; font-weight: 600; }
.warn-outline { border-color: var(--amber-500); }
.detail { display: none; }

@media (min-width: 900px) {
  .results { height: calc(100dvh - var(--header-h)); min-height: 640px; }
  .map { inset: 0; height: auto; }
  .mapchip { display: block; position: absolute; left: 518px; top: 12px; z-index: 5; padding: 10px 20px; border-radius: 99px; background: rgba(255, 255, 255, 0.95); border: 1px solid #ecd5d1; box-shadow: 0 12px 28px rgba(126, 16, 21, 0.14); font-size: 14px; font-weight: 800; color: var(--wine); }
  .panel { left: 24px; right: auto; top: 12px; bottom: 24px; width: 470px; padding: 20px; border-radius: 40px 44px 40px 46px / 44px 40px 46px 40px; border: 1.5px solid var(--blood-500); box-shadow: 0 26px 60px rgba(126, 16, 21, 0.2); gap: 12px; }
  .grab { display: none; }
  .grp { font-size: 56px; }
  .edit { display: grid; }
  .banner { display: flex; }
  .filters { display: flex; }
  .detail { display: flex; flex-direction: column; position: absolute; right: 24px; top: 12px; width: 350px; padding: 24px; border-radius: 40px 44px 40px 46px / 44px 40px 46px 40px; background: rgba(255, 255, 255, 0.96); border: 1.5px solid #ecd5d1; box-shadow: 0 26px 60px rgba(126, 16, 21, 0.18); z-index: 5; max-height: calc(100% - 36px); overflow-y: auto; }
}
.dh { display: flex; align-items: center; gap: 12px; }
.dh > span:last-child { display: flex; flex-direction: column; }
.dh strong { font-size: 17px; color: #12202b; }
.dh small { font-size: 12.5px; font-weight: 600; color: #5a3c3f; }
.di { width: 46px; height: 46px; border-radius: 99px; background: var(--blood-500); color: #fff; display: grid; place-items: center; }
.di.centre { border-radius: 14px; }
.detail h3 { margin: 22px 0 12px; font-size: 11.5px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #7a5a5d; }
.why { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.why li { display: flex; gap: 12px; align-items: flex-start; font-size: 14px; font-weight: 600; line-height: 1.45; color: var(--wine); }
.tick { width: 22px; height: 22px; border-radius: 99px; background: var(--teal-50); color: var(--teal-600); display: grid; place-items: center; flex-shrink: 0; margin-top: 1px; }
.kept { margin-top: 22px; padding: 16px 18px; border-radius: 26px; background: var(--blood-50); }
.kh { display: flex; justify-content: space-between; }
.kh small { font-size: 12px; font-weight: 800; color: #7a5a5d; }
.big { display: flex; align-items: baseline; gap: 8px; margin-top: 4px; }
.big b { font-size: 30px; color: var(--blood-500); }
.big span { font-size: 13px; font-weight: 600; color: #5a3c3f; }
.segs { display: flex; gap: 5px; margin-top: 10px; }
.segs i { flex: 1; height: 10px; border-radius: 99px; background: #e6c4c0; }
.segs i.on { background: var(--blood-500); }
.kept p { margin: 10px 0 0; font-size: 12px; font-weight: 600; color: #5a3c3f; line-height: 1.45; }
</style>
