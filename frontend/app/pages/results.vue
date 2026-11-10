<script setup lang="ts">
useHead({ title: 'Results · Blood Dispatch' })

const route = useRoute()
const d = useDispatch()
if (!d.request.value) d.loadFromQuery(route.query, route.query.pick as string | undefined)
if (!d.request.value) await navigateTo('/request')

const limitH = computed(() => d.request.value?.limitH ?? 3)
const reasons = computed(() => d.selected.value?.reasons ?? [])
</script>

<template>
  <div v-if="d.request.value" class="results">
    <div class="map"><SourceMap :options="d.options.value" :selected-id="d.selectedId.value" @select="d.select" /></div>

    <section class="panel">
      <div class="grab" aria-hidden="true" />

      <div class="summary" aria-label="Your request">
        <span class="grp">{{ d.request.value.group }}</span>
        <span class="meta"><b>{{ d.request.value.units }} units · {{ d.request.value.product.toLowerCase() }}</b><small>{{ d.request.value.id }} · {{ d.request.value.openedAt }} · limit {{ d.request.value.limitH }} h</small></span>
        <NuxtLink to="/request" class="edit" aria-label="Edit request"><AppIcon name="edit" /></NuxtLink>
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

      <div class="head">
        <h1>{{ d.tooLong.value ? 'Still available' : `${d.options.value.length} sources can cover this` }}</h1>
        <span class="muted">Yesterday's stock</span>
      </div>

      <ul class="list">
        <li v-for="(o, i) in d.options.value" :key="o.id" class="rise" :style="{ '--d': i * 90 + 'ms' }">
          <SourceCard :option="o" :rank="i + 1" :selected="o.id === d.selectedId.value" :limit-h="limitH" @select="d.select(o.id)" />
        </li>
      </ul>
      <p class="muted base">{{ d.baseline.value }}</p>

      <div class="cta">
        <button type="button" class="btn" :class="d.tooLong.value ? 'btn-outline-blood' : 'btn-primary'" :disabled="!d.selected.value" @click="d.confirmSelection()">
          Request from {{ d.selected.value?.name.split(' ').slice(0, 2).join(' ') }}{{ d.tooLong.value ? ' anyway' : '' }}
        </button>
        <SafetyNote />
      </div>
    </section>

    <aside v-if="d.selected.value" class="detail" aria-label="Why this source">
      <div class="dh">
        <span class="di" :class="d.selected.value.kind"><AppIcon :name="d.selected.value.kind" /></span>
        <span><strong>{{ d.selected.value.name }}</strong><small>{{ d.selected.value.kind === 'hospital' ? 'Hospital' : 'Centre' }} · {{ d.selected.value.km }} km by road</small></span>
      </div>
      <h3>Why this source</h3>
      <ul>
        <li v-for="r in reasons" :key="r"><AppIcon name="check" :size="18" />{{ r }}</li>
      </ul>
      <div class="kept"><small>Stock kept for itself</small><strong>{{ d.selected.value.kept }}</strong></div>
      <p class="muted fine">Stock is yesterday's count. The supplier confirms the shelf before anything moves.</p>
    </aside>
  </div>
</template>

<style scoped>
.results { position: relative; flex: 1; min-height: calc(100dvh - var(--header-h) - 86px); overflow: hidden; background: var(--fog); }
.map { position: absolute; inset: 0 0 auto 0; height: 36vh; }
.summary { display: flex; align-items: center; gap: 12px; background: var(--paper); border-radius: 16px; padding: 8px 8px 8px 14px; }
.grp { font-size: 26px; font-weight: 800; color: var(--blood-500); line-height: 1; }
.meta { flex: 1; display: flex; flex-direction: column; font-size: 14px; }
.meta small { font-size: 11.5px; font-weight: 600; color: var(--slate); }
.edit { width: 44px; height: 44px; border-radius: 12px; border: 1px solid var(--line); background: var(--white); display: grid; place-items: center; color: var(--ink); }
.panel { position: absolute; left: 0; right: 0; bottom: 0; top: 34vh; background: var(--white); border-radius: 26px 26px 0 0; box-shadow: 0 -8px 30px rgba(18, 32, 43, 0.16); padding: 10px 16px 16px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
.grab { width: 40px; height: 4px; border-radius: 99px; background: var(--line); margin: 0 auto; flex-shrink: 0; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.head h1 { margin: 0; font-size: 17px; font-weight: 800; }
.head span { font-size: 11.5px; font-weight: 700; }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.base { margin: 0; font-size: 12.5px; font-weight: 600; }
.cta { margin-top: auto; display: flex; flex-direction: column; gap: 8px; padding-top: 8px; }
.warn { background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: 20px; padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; color: var(--amber-900); }
.wt { display: flex; align-items: center; gap: 10px; color: var(--amber-700); }
.wt strong { font-size: 17px; line-height: 1.2; color: var(--amber-900); }
.warn p { margin: 0; font-size: 13.5px; line-height: 1.5; font-weight: 600; }
.warn-outline { border-color: var(--amber-500); }
.detail { display: none; }

@media (min-width: 900px) {
  .results { min-height: calc(100dvh - var(--header-h)); display: grid; grid-template-columns: 440px minmax(0, 1fr) 340px; }
  .map { position: relative; inset: auto; height: auto; grid-column: 2; grid-row: 1; min-height: 0; }
  .panel { position: relative; inset: auto; grid-column: 1; grid-row: 1; border-radius: 0; box-shadow: 6px 0 24px rgba(18, 32, 43, 0.12); padding: 20px; z-index: 1; }
  .grab { display: none; }
  .detail { display: flex; grid-column: 3; grid-row: 1; flex-direction: column; gap: 14px; background: var(--white); border-left: 1px solid var(--line); padding: 22px 22px; overflow-y: auto; }
  .dh { display: flex; align-items: center; gap: 10px; }
  .dh span:last-child { display: flex; flex-direction: column; }
  .dh small { font-size: 12px; font-weight: 600; color: var(--slate); }
  .di { width: 36px; height: 36px; border-radius: 99px; background: var(--blood-500); color: #fff; display: grid; place-items: center; }
  .di.centre { border-radius: 10px; }
  .detail h3 { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; color: var(--slate); }
  .detail ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .detail li { display: flex; gap: 10px; font-size: 13px; font-weight: 600; line-height: 1.4; color: var(--ink); }
  .detail li svg { color: var(--teal-600); flex-shrink: 0; margin-top: 1px; }
  .kept { background: var(--paper); border-radius: 14px; padding: 12px 14px; display: flex; flex-direction: column; gap: 3px; }
  .kept small { font-size: 12px; font-weight: 800; color: var(--slate); }
  .kept strong { font-size: 14px; }
  .fine { margin: 0; font-size: 12px; font-weight: 600; line-height: 1.4; }
}
</style>
