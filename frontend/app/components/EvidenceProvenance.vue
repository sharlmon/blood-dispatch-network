<script setup lang="ts">
// Section 5: where the numbers come from, so a reviewer can trace and reproduce them.
import type { DataQuality, ResultEnvelope } from '~/composables/useResults'

const props = defineProps<{
  files: { title: string; env: ResultEnvelope<unknown> }[]
  quality: DataQuality | null
  provider: string | null
  live: boolean
}>()

const first = computed(() => props.files[0]?.env ?? null)
const split = computed(() => first.value?.split ?? null)
const same = (pick: (e: ResultEnvelope<unknown>) => unknown) => {
  const seen = new Set(props.files.map(f => JSON.stringify(pick(f.env) ?? null)))
  return seen.size <= 1
}
const splitDiffers = computed(() => !same(e => e.split))
const manifestDiffers = computed(() => !same(e => e.dataset_manifest))
const manifest = computed(() => Object.entries(first.value?.dataset_manifest ?? {}).map(([file, v]) => ({ file, rows: v?.rows ?? null, sha: v?.sha256 ?? '' })))
const report = computed(() => (isCleaningReport(props.quality) ? props.quality : null))
const skipped = computed(() => (props.quality && !isCleaningReport(props.quality) ? props.quality.reason : null))

const CORRECTIONS: Record<string, string> = {
  facility_names_canonicalized: 'Facility names made consistent',
  whitespace_trimmed_cells: 'Cells with stray spaces trimmed',
  temperature_sentinels_removed: 'Temperature sentinel values blanked',
  components_normalized: 'Product codes normalised',
  timestamps_normalized: 'Timestamps normalised'
}
const FLAGS: Record<string, string> = {
  missing_received_at: 'Transfers with no receipt time',
  possible_duplicate_donor_review: 'Possible duplicate donors',
  missing_blood_group: 'Donors with no blood group',
  unknown_patient_blood_group: 'Requests with an unknown patient group',
  short_donation_gap_review: 'Short gaps between donations',
  documented_temperature_sensor_glitch: 'Documented temperature sensor glitches'
}
</script>

<template>
  <div class="evp">
    <p class="ev-p">
      Read from this site's copy of the committed results folder (results-data/).
      Every number on this page comes from these files; the page only divides or subtracts where it says so.
    </p>

    <div class="ev-grid two">
      <div class="ev-panel">
        <h3 class="ev-h3">Files read</h3>
        <ul class="files">
          <li v-for="f in files" :key="f.title">
            <b>{{ f.title }}</b>
            <span>Generated {{ stampText(f.env.generated_at) }} · schema {{ f.env.schema_version ?? '—' }} · {{ f.env.synthetic_data === false ? 'not marked synthetic' : 'synthetic data' }}</span>
            <span class="hash">settings_sha256 <code>{{ f.env.settings_sha256 || '—' }}</code></span>
          </li>
        </ul>
      </div>

      <div class="ev-panel">
        <h3 class="ev-h3">Run</h3>
        <dl class="kv">
          <div><dt>Train</dt><dd>before {{ dayText(split?.training_end_exclusive) }}</dd></div>
          <div><dt>Validation</dt><dd>{{ periodText(split?.training_end_exclusive, split?.validation_end_exclusive) }}</dd></div>
          <div><dt>Held-out test</dt><dd>{{ periodText(split?.validation_end_exclusive, split?.test_end_exclusive) }}</dd></div>
          <div><dt>Seed</dt><dd class="tnum">{{ first?.seed ?? '—' }}</dd></div>
          <div><dt>Time zone</dt><dd>{{ first?.timezone ?? '—' }} (EAT, UTC+3)</dd></div>
          <div><dt>Cleaning</dt><dd>{{ first?.cleaning_performed === false ? 'skipped' : first?.cleaning_performed ? 'performed' : '—' }}</dd></div>
          <div><dt>Replay sources</dt><dd>{{ provider ?? '—' }}</dd></div>
        </dl>
        <p v-if="splitDiffers" class="ev-small warn">These files do not all share one split; the split shown is from {{ files[0]?.title }}.</p>
      </div>
    </div>

    <div class="ev-grid two">
      <div class="ev-panel">
        <h3 class="ev-h3">Input data</h3>
        <div class="ev-scroll">
          <table class="ev-tbl">
            <caption>The starter CSVs the evaluation read, with their row counts and checksums.<template v-if="manifestDiffers"> Not every file used the same inputs; shown for {{ files[0]?.title }}.</template></caption>
            <thead><tr><th scope="col" class="ev-first">File</th><th scope="col">Rows</th><th scope="col">sha256</th></tr></thead>
            <tbody>
              <tr v-for="r in manifest" :key="r.file">
                <th scope="row" class="ev-first">{{ r.file }}</th>
                <td>{{ countText(r.rows) }}</td>
                <td><code :title="r.sha">{{ r.sha ? `${r.sha.slice(0, 12)}…` : '—' }}</code></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="report" class="ev-panel">
        <h3 class="ev-h3">Cleaning</h3>
        <p class="ev-small policy">Status {{ report.status }} · policy <code>{{ report.cleaning_policy_version }}</code></p>
        <EvidenceCounts :counts="report.corrections ?? {}" :labels="CORRECTIONS" :order="Object.keys(CORRECTIONS)" />
        <h3 class="ev-h3 sub">Kept and flagged for review, not changed</h3>
        <EvidenceCounts :counts="report.review_flags ?? {}" :labels="FLAGS" :order="Object.keys(FLAGS)" />
      </div>
      <div v-else-if="skipped" class="ev-panel">
        <h3 class="ev-h3">Cleaning skipped</h3>
        <p class="ev-small">{{ skipped }}</p>
      </div>
    </div>

    <p class="ev-small">
      To reproduce, run <code>python scripts/evaluate_ds2.py</code> with the starter dataset (see docs/ds2-implementation.md).
      Each hospital reserve scenario adds <code>--hospital-reserve-units N --output-dir results/hospital-reserve-N</code>.
    </p>
  </div>
</template>

<style scoped>
.evp { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.files { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.files li { display: flex; flex-direction: column; gap: 3px; padding-bottom: 12px; border-bottom: 1px solid #e2ece9; font-size: 12.5px; font-weight: 600; color: #44545f; line-height: 1.45; }
.files li:last-child { padding-bottom: 0; border-bottom: 0; }
.files b { font-size: 14px; color: var(--ink-deep); overflow-wrap: anywhere; }
.hash code { overflow-wrap: anywhere; word-break: break-all; color: var(--ink); }
code { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.kv { margin: 0; display: grid; }
.kv div { display: flex; justify-content: space-between; gap: 14px; padding: 9px 0; border-bottom: 1px solid #e2ece9; }
.kv div:last-child { border-bottom: 0; }
.kv dt { font-size: 13.5px; font-weight: 600; color: #2c3d48; }
.kv dd { margin: 0; font-size: 13.5px; font-weight: 800; color: var(--ink); text-align: right; overflow-wrap: anywhere; }
.warn { margin-top: 10px; color: var(--amber-700); }
.sub { margin-top: 18px; }
.policy { margin: -4px 0 6px; }
</style>
