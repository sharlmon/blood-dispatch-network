<script setup lang="ts">
// One numbered section of the evidence page, with the results file it reads from.
defineProps<{ id: string; n: number; icon: string; kicker: string; title: string; source?: string }>()
</script>

<template>
  <section :id="id" class="evs card" :aria-labelledby="`${id}-h`">
    <header class="hd">
      <IconBadge size="lg"><AppIcon :name="icon" :size="24" /></IconBadge>
      <span class="ht">
        <span class="overline">{{ n }} · {{ kicker }}</span>
        <h2 :id="`${id}-h`" class="h2">{{ title }}</h2>
      </span>
      <code v-if="source" class="src">{{ source }}</code>
    </header>
    <slot />
  </section>
</template>

<style scoped>
.evs { padding: 20px 16px; display: flex; flex-direction: column; gap: 18px; min-width: 0; scroll-margin-top: calc(var(--header-h) + 12px); }
.hd { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ht { flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 4px; }
.h2 { line-height: 1.2; }
.src { padding: 5px 11px; border-radius: 99px; background: var(--primary-50); color: var(--primary-700); font-size: 12px; font-weight: 700; overflow-wrap: anywhere; }
@media (min-width: 900px) { .evs { padding: 26px 28px; gap: 22px; } }
</style>

<style>
/* Shared by the Evidence* components (prefixed so nothing else is touched). */
.ev-p { margin: 0; font-size: 14.5px; line-height: 1.6; font-weight: 500; color: #44545f; max-width: 760px; }
.ev-p b { color: var(--ink-deep); }
.ev-h3 { margin: 0 0 12px; font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: #5d6d78; }
.ev-small { margin: 0; font-size: 12.5px; font-weight: 600; color: #5d6d78; line-height: 1.5; }
.ev-panel { padding: 16px; border-radius: var(--r-lg); background: #fff; border: 1.5px solid #e2ece9; min-width: 0; }
.ev-grid { display: grid; gap: 14px; }
@media (min-width: 900px) { .ev-grid.two { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: start; } }

.ev-callout { margin: 0; display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border-radius: var(--r-md); background: var(--amber-50); border: 1.5px solid #ecc98a; color: var(--amber-900); font-size: 13.5px; font-weight: 600; line-height: 1.5; }
.ev-callout svg { flex-shrink: 0; color: var(--amber-700); margin-top: 1px; }
.ev-callout.teal { background: var(--teal-50); border-color: #9fd6cd; color: #064e46; }
.ev-callout.teal svg { color: var(--teal-600); }
.ev-callout b { font-weight: 800; }

/* Tones for bars, stacks and their legends */
.ev-t-teal { background: var(--teal-600); }
.ev-t-light { background: #9fd6cd; }
.ev-t-amber { background: #e3a43c; }
.ev-t-grey { background: #c9d6d4; }
.ev-t-primary { background: var(--primary-500); }
.ev-t-slate { background: #7c909f; }
.ev-legend { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12.5px; font-weight: 700; color: #44545f; }
.ev-legend li { display: inline-flex; align-items: center; gap: 7px; }
.ev-legend i { width: 12px; height: 12px; border-radius: 4px; flex-shrink: 0; }

/* Tables scroll inside their own box on narrow screens; the first column stays put. */
.ev-scroll { overflow-x: auto; overscroll-behavior-x: contain; -webkit-overflow-scrolling: touch; }
.ev-tbl { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; font-variant-numeric: tabular-nums; }
.ev-tbl caption { caption-side: bottom; text-align: left; padding-top: 10px; font-size: 12.5px; font-weight: 600; color: #5d6d78; line-height: 1.5; }
.ev-tbl th, .ev-tbl td { padding: 10px 12px; border-bottom: 1px solid #e2ece9; text-align: right; vertical-align: top; }
.ev-tbl thead th { font-size: 12px; font-weight: 800; color: #44545f; vertical-align: bottom; border-bottom: 1.5px solid #c9dbd8; line-height: 1.3; }
.ev-tbl thead small { display: block; margin-top: 2px; font-size: 11.5px; font-weight: 600; color: #5d6d78; }
.ev-tbl th[scope='row'] { text-align: left; font-weight: 700; color: var(--ink-deep); line-height: 1.4; }
.ev-tbl th[scope='row'] small { display: block; font-size: 12px; font-weight: 600; color: #5d6d78; margin-top: 2px; }
.ev-tbl td { font-weight: 800; color: var(--ink); white-space: nowrap; }
.ev-tbl tbody tr:last-child > * { border-bottom: 0; }
.ev-tbl .ev-first { position: sticky; left: 0; z-index: 1; background: #fff; text-align: left; }
.ev-na { color: #8a99a3; font-weight: 600; }

.ev-details { border-radius: var(--r-lg); background: #fff; border: 1.5px solid #e2ece9; padding: 0 16px; }
.ev-details > summary { cursor: pointer; min-height: 48px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-weight: 800; font-size: 14px; color: var(--primary-700); }
.ev-details > summary small { font-size: 12px; font-weight: 600; color: #5d6d78; }
.ev-details[open] { padding-bottom: 16px; }
.ev-list { margin: 0; padding-left: 20px; display: grid; gap: 8px; font-size: 14px; font-weight: 500; line-height: 1.5; color: #2c3d48; }
</style>
