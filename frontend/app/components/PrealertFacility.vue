<script setup lang="ts">
// One hospital on the evening list: its known zero counts, each needing a person to review it.
import type { PrealertAlert } from '~/composables/useResults'

const props = defineProps<{ facilityId: string; name: string | null; alerts: PrealertAlert[] }>()

const review = computed(() => props.alerts.some(a => a.human_review_required !== false))
const ZERO = 'known_zero_stock_for_component_previous_closing_snapshot'
const units = (n: number) => `${countText(n)} ${n === 1 ? 'unit' : 'units'}`
</script>

<template>
  <article class="pf" :aria-label="`${name ?? facilityId}: ${alerts.length} ${alerts.length === 1 ? 'alert' : 'alerts'}`">
    <header class="ph">
      <IconBadge size="md"><AppIcon name="hospital" :size="22" /></IconBadge>
      <span class="pt"><b>{{ name ?? facilityId }}</b><small v-if="name">{{ facilityId }}</small></span>
      <span v-if="review" class="badge"><AppIcon name="warning" :size="14" /> Human review required</span>
    </header>
    <ul class="rows">
      <li v-for="a in alerts" :key="`${a.component}-${a.blood_group}`">
        <span class="grp">{{ toDisplayGroup(a.blood_group) }}</span>
        <span class="what">
          <b>{{ componentText(a.component) }}</b>
          <small>{{ a.component }} · {{ a.reason === ZERO ? 'closing count' : keyText(a.reason) }} of {{ dayText(a.stock_as_of) }}</small>
        </span>
        <b class="n tnum">{{ units(a.recorded_units) }}</b>
      </li>
    </ul>
  </article>
</template>

<style scoped>
.pf { height: 100%; padding: 16px; border-radius: var(--r-lg); background: #fff; border: 1.5px solid #d8e4e2; display: flex; flex-direction: column; gap: 12px; transition: transform 0.2s ease, box-shadow 0.2s ease; }
.pf:hover { transform: translateY(-2px); box-shadow: 0 12px 26px rgba(6, 74, 68, 0.12); }
.ph { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.pt { flex: 1; min-width: 140px; display: flex; flex-direction: column; }
.pt b { font-size: 15px; color: var(--ink-deep); line-height: 1.3; overflow-wrap: anywhere; }
.pt small { font-size: 12px; font-weight: 700; color: #5d6d78; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border-radius: 99px; background: var(--amber-50); color: var(--amber-900); font-size: 11.5px; font-weight: 800; white-space: nowrap; }
.badge svg { color: var(--amber-700); }
.rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.rows li { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: var(--r-md); background: var(--paper); }
.grp { min-width: 46px; padding: 5px 8px; border-radius: 12px; background: var(--blood-50); color: var(--blood-700); font-size: 15px; font-weight: 800; text-align: center; }
.what { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }
.what b { font-size: 14px; color: var(--ink); }
.what small { font-size: 11.5px; font-weight: 700; color: #5d6d78; }
.n { font-size: 14px; color: var(--ink); white-space: nowrap; }
</style>
