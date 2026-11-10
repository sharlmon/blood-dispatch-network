<script setup lang="ts">
useHead({ title: 'Track · Blood Dispatch' })

const route = useRoute()
const d = useDispatch()
if (!d.request.value) { d.loadFromQuery(route.query, route.query.pick as string | undefined); d.stage.value = Number(route.query.stage) || 1 }
if (!d.request.value || !d.selected.value) await navigateTo('/request')

const steps = computed(() => [
  { title: 'Request sent', sub: `${d.request.value?.openedAt} · logged` },
  { title: 'Waiting for shelf check', sub: `${d.selected.value?.name.split(' ').slice(0, 2).join(' ')} confirms the units are on the shelf. If no answer in 10 min, we move to the next source.` },
  { title: 'Dispatched', sub: 'Arrival window tightens once it leaves.' },
  { title: 'Arrived', sub: 'Lab worker checks every bag.' }
])
const state = (i: number) => (i < d.stage.value ? 'done' : i === d.stage.value ? 'now' : 'todo')
</script>

<template>
  <div v-if="d.request.value && d.selected.value" class="wrap">
    <div class="map"><SourceMap :options="[d.selected.value]" :selected-id="d.selected.value.id" :pad-top="80" /></div>

    <section class="panel">
      <NuxtLink to="/results" class="back"><AppIcon name="back" /> Back to results</NuxtLink>
      <div class="window card">
        <small>ARRIVAL WINDOW</small>
        <div class="big"><strong class="tnum">{{ fmtHours(d.selected.value.p50) }}</strong><span>most likely · almost certain {{ fmtRange(d.selected.value.p10, d.selected.value.p90) }}</span></div>
        <WindowBar :p10="d.selected.value.p10" :p50="d.selected.value.p50" :p90="d.selected.value.p90" :limit="d.request.value.limitH" :max="Math.max(4, d.request.value.limitH + 1)" />
        <div class="scale"><span>Now</span><span>Your {{ d.request.value.limitH }} h limit</span></div>
      </div>

      <ol class="steps">
        <li v-for="(s, i) in steps" :key="s.title" :class="[state(i), 'rise']" :style="{ '--d': i * 80 + 'ms' }">
          <span class="dot"><AppIcon v-if="state(i) === 'done'" name="check" :size="14" /></span>
          <span class="txt"><strong>{{ s.title }}</strong><small>{{ s.sub }}</small></span>
        </li>
      </ol>

      <div class="actions">
        <NuxtLink to="/results" class="btn">Try next source</NuxtLink>
        <button type="button" class="btn btn-dark"><AppIcon name="call" :size="20" /> Call site</button>
      </div>
      <button v-if="d.stage.value < 3" type="button" class="demo" @click="d.advance()">Demo: simulate next step</button>
      <SafetyNote />

      <details class="audit">
        <summary><AppIcon name="audit" :size="18" /> Audit log ({{ d.audit.value.length }})</summary>
        <ul><li v-for="(a, i) in d.audit.value" :key="i"><time>{{ a.at }}</time> {{ a.text }}</li></ul>
      </details>
    </section>
  </div>
</template>

<style scoped>
.wrap { position: relative; flex: 1; min-height: calc(100dvh - var(--header-h) - 86px); background: var(--fog); overflow: hidden; }
.map { position: absolute; inset: 0 0 auto 0; height: 32vh; }
.panel { position: absolute; left: 0; right: 0; top: 30vh; bottom: 0; background: var(--white); border-radius: 26px 26px 0 0; box-shadow: 0 -8px 30px rgba(18, 32, 43, 0.16); padding: 16px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
.back { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; font-size: 14px; color: var(--slate); text-decoration: none; min-height: 32px; }
.window { padding: 14px 16px; background: var(--paper); display: flex; flex-direction: column; gap: 10px; }
.window small { font-size: 12px; font-weight: 800; letter-spacing: 0.04em; color: var(--slate); }
.big { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.big strong { font-size: 34px; line-height: 1; }
.big span { font-size: 13px; font-weight: 700; color: var(--slate); }
.scale { display: flex; justify-content: space-between; font-size: 11px; font-weight: 700; color: var(--slate); }
.steps { list-style: none; margin: 0; padding: 0 4px; display: flex; flex-direction: column; }
.steps li { display: flex; gap: 14px; padding-bottom: 14px; position: relative; }
.steps li:not(:last-child)::before { content: ''; position: absolute; left: 11px; top: 26px; bottom: 2px; width: 2px; background: var(--line); }
.steps li.done:not(:last-child)::before { background: var(--teal-600); }
.dot { width: 24px; height: 24px; border-radius: 99px; flex-shrink: 0; display: grid; place-items: center; background: var(--white); border: 2px solid var(--line); color: #fff; }
.done .dot { background: var(--teal-600); border-color: var(--teal-600); }
.now .dot { border: 3px solid var(--blood-500); animation: ring 1.6s ease-out infinite; }
.txt { display: flex; flex-direction: column; }
.txt strong { font-size: 14.5px; }
.txt small { font-size: 12.5px; font-weight: 600; color: var(--slate); line-height: 1.4; margin-top: 1px; }
.todo .txt strong { color: var(--slate); }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: auto; }
.actions .btn { min-height: 52px; font-size: 14px; }
.demo { align-self: center; border: 1px dashed var(--line); background: transparent; border-radius: 10px; min-height: 36px; padding: 0 14px; font-size: 12px; font-weight: 700; color: var(--slate); }
.audit { font-size: 13px; }
.audit summary { display: flex; align-items: center; gap: 8px; font-weight: 700; cursor: pointer; min-height: 32px; }
.audit ul { margin: 6px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
.audit li { color: var(--slate); font-weight: 600; }
.audit time { font-weight: 800; color: var(--ink); margin-right: 6px; }

@media (min-width: 900px) {
  .wrap { height: calc(100dvh - var(--header-h)); min-height: 640px; margin-top: 6px; }
  .map { inset: 0; height: auto; }
  .panel { top: 12px; left: 24px; right: auto; bottom: 24px; width: 470px; border-radius: 40px 44px 40px 46px / 44px 40px 46px 40px; border: 1.5px solid var(--blood-500); box-shadow: 0 26px 60px rgba(126, 16, 21, 0.2); padding: 22px; }
}
</style>
