// DS2's committed evidence (results/*.json, written by scripts/evaluate_ds2.py) and the evening
// pre-alert list. Live: GET /api/results, /api/results/<name>?scenario=<s> and /api/prealerts.
// Static demo (no API): the same files, served by this site at <baseURL>results-data/.
// Everything is fetched in the browser; the server renders the loading state.
import type { ShallowRef } from 'vue'
import { eatClock, eatIso, eatTime, fmtDay } from '~/utils/format'
import { apiFailure, useApi } from './useApi'
import type { ApiFailure } from './useApi'

// ---------- The artifacts, as the JSON has them ----------

export type ResultName = 'summary' | 'replay_summary' | 'arrival_validation' | 'prealert_evaluation' | 'data_quality'

/** The settings a run used. Only the parts the pages read are typed. */
export interface ResultSettings {
  replay?: { deadline_hours?: number; components?: string[]; urgencies?: string[]; hospital_reserve_units?: Record<string, number> }
  lending?: { enabled?: boolean }
  prealert?: { blood_groups?: string[]; components?: string[]; run_hour?: number; horizon_hours?: number }
  [key: string]: unknown
}

/** Every results file is wrapped like this. */
export interface ResultEnvelope<R> {
  schema_version: number
  generated_at: string
  synthetic_data: boolean
  timezone?: string
  cleaning_performed?: boolean
  dataset_manifest: Record<string, { rows: number; sha256: string }>
  settings: ResultSettings
  settings_sha256: string
  /** naive EAT times; each end is exclusive */
  split: { training_end_exclusive: string; validation_end_exclusive: string; test_end_exclusive: string }
  seed: number | null
  result: R
}

export interface ArrivalMetrics {
  mean_absolute_error_hours: number | null
  median_absolute_error_hours: number | null
  baseline_map_plus_2_mean_absolute_error_hours: number | null
  baseline_map_plus_2_median_absolute_error_hours: number | null
  /** share of arrivals inside p10-p90 */
  p10_p90_coverage: number | null
  nominal_interval_probability: number | null
  mean_interval_width_hours: number | null
  fraction_after_p90: number | null
}

/** One scored period (validation or held-out test) of the frozen arrival model. */
export interface ArrivalCheck {
  model_type: string
  evaluation_period: { start_inclusive: string; end_exclusive: string }
  trained_before: string
  training_sample_count: number
  sample_count: number
  interval_sample_count: number
  unit_of_analysis: string
  time_origin: string
  arrival_endpoint: string
  metrics: ArrivalMetrics
  exclusions: Record<string, number>
  limitations: string[]
}

export interface ArrivalValidation { validation: ArrivalCheck; test: ArrivalCheck }

export type PolicyName = 'baseline' | 'all_centres' | 'centres_and_hospitals'

export interface ReplayPolicy {
  evaluated_requests: number
  full_source_found: number
  partial_source_only: number
  no_source_found: number
  full_source_p50_within_deadline: number
  full_source_p90_within_deadline: number
  median_p50_hours_full_sources: number | null
  mean_p50_hours_full_sources: number | null
  previously_unfulfilled_p50_opportunities: number
  hospital_sources_selected: number
  /** baseline only: today's quote, map time + 2 h */
  median_map_plus_two_quote_hours?: number | null
}

export interface ReplaySummary {
  evaluation_type: string
  period: { start_inclusive: string; end_exclusive: string }
  cohort: { components: string[]; urgencies: string[]; definition: string }
  deadline_hours: number
  exclusions: Record<string, number>
  policies: Record<PolicyName, ReplayPolicy>
  candidate_provider: string
  observed_outcomes_same_cohort: Record<string, number>
  observed_fully_served_median_bedside_hours: number | null
  observed_fully_served_timing_count: number
  observed_timing_exclusions: Record<string, number>
  /** saved = today's p50 minus the centres + hospitals p50, on requests where both found a full source */
  paired_comparison: { requests: number; mean_p50_hours_saved: number | null; median_p50_hours_saved: number | null }
  assumptions: string[]
  limitations: string[]
}

export interface PrealertMetrics {
  scheduled_window_count: number
  evaluated_window_count: number
  censored_window_count: number
  alert_count: number
  evaluated_alert_count: number
  censored_alert_count: number
  known_snapshot_exposure_count: number
  unknown_snapshot_exposure_count: number
  evaluated_request_count: number
  observed_unmet_request_count: number
  detected_unmet_request_count: number
  missed_unmet_request_count: number
  true_positive_alert_count: number
  false_positive_alert_count: number
  requests_excluded_missing_snapshot: number
  unmet_requests_excluded_missing_snapshot: number
  requests_excluded_censoring: number
  unmet_requests_excluded_censoring: number
  precision: number | null
  precision_denominator_alerts: number
  recall: number | null
  recall_denominator_unmet_requests: number
}

export interface PrealertEvaluation {
  evaluation_period: { start: string; end_exclusive: string }
  settings: { blood_groups: string[]; components: string[]; run_hour: number; horizon_hours: number; max_snapshot_age_days?: number }
  metrics: PrealertMetrics
  ignored_requests: Record<string, number>
  assumptions: string[]
  limitations: string[]
}

export interface CleaningReport {
  status: string
  cleaning_policy_version: string
  time_basis?: string
  corrections: Record<string, number>
  exclusions: Record<string, number>
  review_flags: Record<string, number>
  limitations: string[]
}

/** data_quality.json: the cleaning report, or why cleaning was skipped. */
export type DataQuality = CleaningReport | { performed: false; reason: string }

export interface ResultsSummary {
  training_batches: number
  test_arrival_batches: number
  arrival_test_metrics: ArrivalMetrics
  replay_policies: Record<PolicyName, ReplayPolicy>
  prealert_metrics: PrealertMetrics
}

export interface ResultPayloads {
  summary: ResultsSummary
  replay_summary: ReplaySummary
  arrival_validation: ArrivalValidation
  prealert_evaluation: PrealertEvaluation
  data_quality: DataQuality
}

/** GET /api/results */
export interface ResultsIndex { files: ResultName[]; scenarios: string[] }

/** A known zero in yesterday's closing count. Needs a person; it is not a forecast or an order. */
export interface PrealertAlert {
  facility_id: string
  facility_name: string | null
  component: string
  blood_group: string
  stock_as_of: string
  recorded_units: number
  generated_at: string
  reason: string
  human_review_required: boolean
}

/** No closing count on record: the stock is unknown, not zero. */
export interface PrealertMissing {
  facility_id: string
  facility_name: string | null
  component: string
  blood_group: string
  stock_as_of: string
  reason: string
}

/** GET /api/prealerts */
export interface PrealertList {
  generated_at: string
  stock_as_of: string
  alerts: PrealertAlert[]
  missing_snapshot: PrealertMissing[]
  assumptions: string[]
  synthetic_data: boolean
  source: string
}

export function isCleaningReport(q: DataQuality | null | undefined): q is CleaningReport {
  return !!q && 'review_flags' in q
}

// ---------- Loading ----------

const FILES: ResultName[] = ['arrival_validation', 'data_quality', 'prealert_evaluation', 'replay_summary', 'summary']
/** The scenario folders bundled with the static demo (the API lists its own). */
const STATIC_SCENARIOS = ['hospital-reserve-5', 'hospital-reserve-10']
const PREALERT_SOURCE = 'results/prealerts.json'

// Committed files do not change while the page is open; failures are not kept.
const cache = new Map<string, Promise<unknown>>()

function isFailure(e: unknown): e is ApiFailure {
  return !!e && typeof e === 'object' && 'code' in e && 'network' in e && 'message' in e
}

function missingFile(what: string): ApiFailure {
  return { status: 404, code: 'not_found', message: `${what} is not available.`, network: false }
}

function envelopeOf<T>(body: unknown, what: string): T {
  // A static host can answer a missing file with an HTML page; never treat that as results.
  if (!body || typeof body !== 'object' || !('result' in body)) throw missingFile(what)
  return body as T
}

const fileTitle = (name: string, scenario: string | null) => `${scenario ? `${scenario}/` : ''}${name}.json`

/** Hospital reserve scenarios by size, then anything else by name. */
export function sortScenarios(names: string[]): string[] {
  const reserve = (s: string) => Number(/^hospital-reserve-(\d+)$/.exec(s)?.[1] ?? Number.NaN)
  return [...names].sort((a, b) => {
    const ra = reserve(a), rb = reserve(b)
    if (!Number.isNaN(ra) && !Number.isNaN(rb)) return ra - rb
    if (!Number.isNaN(ra)) return -1
    if (!Number.isNaN(rb)) return 1
    return a.localeCompare(b)
  })
}

export function scenarioLabel(scenario: string | null): string {
  if (!scenario) return 'Default: no hospital reserve'
  const n = /^hospital-reserve-(\d+)$/.exec(scenario)?.[1]
  if (n) return `Hospital reserve ${n}`
  if (scenario === 'ds1-provider') return 'DS1 rules'
  return scenario
}

/** Low-level loaders. Both modes return the same shapes. */
export function useResults() {
  const config = useRuntimeConfig()
  const live = !!config.public.apiBase
  const { api, fail } = useApi()
  const base = config.app.baseURL || '/'
  const root = `${base}${base.endsWith('/') ? '' : '/'}results-data/`

  function toFailure(e: unknown): ApiFailure {
    if (isFailure(e)) return e
    if (live) return fail(e, { quiet: true })
    const f = apiFailure(e)
    if (f.status === 404) return missingFile('This results file')
    if (f.network) return { ...f, message: 'Could not read the results files. Check the connection and try again.' }
    return f
  }

  function cached<T>(key: string, get: () => Promise<T>): Promise<T> {
    let p = cache.get(key) as Promise<T> | undefined
    if (!p) {
      p = get()
      cache.set(key, p)
      p.catch(() => cache.delete(key))
    }
    return p
  }

  /** Which files and scenarios exist. */
  function loadIndex(): Promise<ResultsIndex> {
    if (!live) return Promise.resolve({ files: [...FILES], scenarios: [...STATIC_SCENARIOS] })
    return cached('index', async () => {
      const r = await api<Partial<ResultsIndex>>('/api/results')
      return { files: Array.isArray(r.files) ? r.files : [], scenarios: Array.isArray(r.scenarios) ? r.scenarios : [] }
    })
  }

  /** One artifact's full envelope, unchanged. `scenario` null is the default run. */
  function loadArtifact<N extends ResultName>(name: N, scenario: string | null = null): Promise<ResultEnvelope<ResultPayloads[N]>> {
    const what = fileTitle(name, scenario)
    return cached(`${live ? 'api' : 'static'}:${what}`, async () => {
      const body = live
        ? await api<unknown>(`/api/results/${name}${scenario ? `?scenario=${encodeURIComponent(scenario)}` : ''}`)
        : await $fetch<unknown>(`${root}${scenario ? `${encodeURIComponent(scenario)}/` : ''}${name}.json`, { responseType: 'json' })
      return envelopeOf<ResultEnvelope<ResultPayloads[N]>>(body, what)
    })
  }

  /** The evening list. In the static demo facility names are not known, so they are null. */
  async function loadPrealerts(): Promise<PrealertList> {
    if (live) return await api<PrealertList>('/api/prealerts')
    const env = envelopeOf<ResultEnvelope<Partial<Omit<PrealertList, 'alerts' | 'missing_snapshot'>> & { alerts?: Omit<PrealertAlert, 'facility_name'>[]; missing_snapshot?: Omit<PrealertMissing, 'facility_name'>[] }>>(
      await $fetch<unknown>(`${root}prealerts.json`, { responseType: 'json' }), 'prealerts.json'
    )
    const r = env.result ?? {}
    return {
      generated_at: r.generated_at ?? env.generated_at,
      stock_as_of: r.stock_as_of ?? '',
      alerts: (r.alerts ?? []).map(a => ({ ...a, facility_name: null })),
      missing_snapshot: (r.missing_snapshot ?? []).map(m => ({ ...m, facility_name: null })),
      assumptions: r.assumptions ?? [],
      synthetic_data: env.synthetic_data !== false,
      source: PREALERT_SOURCE
    }
  }

  return { live, toFailure, loadIndex, loadArtifact, loadPrealerts }
}

type LoadState = 'loading' | 'ready' | 'error'

/**
 * The evidence page: arrival validation, pre-alert evaluation and data quality from the default
 * run, plus the replay ladder of the chosen scenario. A missing file only empties its section.
 */
export function useEvidence() {
  const results = useResults()
  const state = ref<LoadState>('loading')
  const error = shallowRef<ApiFailure | null>(null)
  const scenarios = ref<string[]>([])
  const scenario = ref<string | null>(null)
  const arrival = shallowRef<ResultEnvelope<ArrivalValidation> | null>(null)
  const prealert = shallowRef<ResultEnvelope<PrealertEvaluation> | null>(null)
  const quality = shallowRef<ResultEnvelope<DataQuality> | null>(null)
  const replay = shallowRef<ResultEnvelope<ReplaySummary> | null>(null)
  const replayState = ref<LoadState>('loading')
  /** the scenario of the replay on screen (`scenario` is the one asked for, which may still be loading) */
  const replayScenario = ref<string | null>(null)
  /** why a file could not be shown, by name */
  const missing = shallowRef<Partial<Record<ResultName, ApiFailure>>>({})
  let replaySeq = 0

  function note(name: ResultName, f: ApiFailure | null) {
    const next = { ...missing.value }
    if (f) next[name] = f
    else delete next[name]
    missing.value = next
  }

  /** Load the replay ladder of `s` (null: the default run). The rest of the page stays as it is. */
  async function showScenario(s: string | null) {
    const my = ++replaySeq
    scenario.value = s
    replayState.value = 'loading'
    try {
      const env = await results.loadArtifact('replay_summary', s)
      if (my !== replaySeq) return
      replay.value = env
      replayScenario.value = s
      replayState.value = 'ready'
      note('replay_summary', null)
    } catch (e) {
      if (my !== replaySeq) return
      replay.value = null
      replayScenario.value = s
      replayState.value = 'error'
      note('replay_summary', results.toFailure(e))
    }
  }

  async function load(wanted: string | null = null) {
    if (import.meta.server) return
    state.value = 'loading'
    error.value = null
    let index: ResultsIndex
    try {
      index = await results.loadIndex()
    } catch (e) {
      error.value = results.toFailure(e)
      state.value = 'error'
      return
    }
    scenarios.value = sortScenarios(index.scenarios)
    const listed = (n: ResultName) => index.files.includes(n)
    async function one<N extends ResultName>(name: N, into: ShallowRef<ResultEnvelope<ResultPayloads[N]> | null>) {
      if (!listed(name)) { into.value = null; note(name, missingFile(fileTitle(name, null))); return }
      try {
        into.value = await results.loadArtifact(name)
        note(name, null)
      } catch (e) {
        into.value = null
        note(name, results.toFailure(e))
      }
    }
    await Promise.all([
      one('arrival_validation', arrival),
      one('prealert_evaluation', prealert),
      one('data_quality', quality),
      showScenario(wanted && scenarios.value.includes(wanted) ? wanted : null)
    ])
    if (!arrival.value && !prealert.value && !quality.value && !replay.value) {
      error.value = Object.values(missing.value)[0] ?? missingFile('The results files')
      state.value = 'error'
      return
    }
    state.value = 'ready'
  }

  return { live: results.live, state, error, scenarios, scenario, arrival, prealert, quality, replay, replayState, replayScenario, missing, load, showScenario }
}

/** The evening pre-alert list, plus the rule's held-out precision when it can be read. */
export function usePrealertList() {
  const results = useResults()
  const list = shallowRef<PrealertList | null>(null)
  const state = ref<LoadState>('loading')
  const error = shallowRef<ApiFailure | null>(null)
  const evaluation = shallowRef<PrealertEvaluation | null>(null)

  async function load() {
    if (import.meta.server) return
    state.value = 'loading'
    error.value = null
    // The evaluation only adds a sentence, so its failure stays silent.
    results.loadArtifact('prealert_evaluation').then((env) => { evaluation.value = env.result }, () => {})
    try {
      list.value = await results.loadPrealerts()
      state.value = 'ready'
    } catch (e) {
      error.value = results.toFailure(e)
      state.value = 'error'
    }
  }

  return { live: results.live, list, state, error, evaluation, load }
}

// ---------- Numbers and words for people ----------

const DASH = '—'
const ok = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v)

/** 0.8082 -> "80.8%". Missing -> "—", never 0. */
export function pctText(share: number | null | undefined, digits = 1): string {
  return ok(share) ? `${(share * 100).toFixed(digits)}%` : DASH
}

/** 1762 -> "1,762". */
export function countText(n: number | null | undefined): string {
  return ok(n) ? n.toLocaleString('en-US') : DASH
}

/** 1557 per 60 -> "26.0". Rounded from the integers, so a half (25.95) goes up as people expect. */
export function rateText(count: number | null | undefined, per: number | null | undefined, digits = 1): string {
  if (!ok(count) || !ok(per) || per <= 0) return DASH
  const scale = 10 ** digits
  return (Math.round((count * scale) / per) / scale).toFixed(digits)
}

/** 0.8899 -> "0.89 h", 6 -> "6 h". */
export function hoursText(h: number | null | undefined, digits = 2): string {
  if (!ok(h)) return DASH
  return `${Number.isInteger(h) ? h : h.toFixed(digits)} h`
}

// Python writes microseconds; keep milliseconds so every browser parses the time.
const isoMs = (iso: string) => iso.replace(/(\.\d{3})\d+/, '$1')

/** "10 Nov 2026, 15:00 EAT" */
export function stampText(iso: string | null | undefined): string {
  if (!iso) return DASH
  const t = isoMs(iso)
  const clock = eatClock(t)
  return clock ? `${fmtDay(t)}, ${clock} EAT` : iso
}

/** First day of a period, in EAT. */
export function dayText(iso: string | null | undefined): string {
  return iso ? fmtDay(isoMs(iso)) : DASH
}

/** "1 Sep – 31 Oct 2026" from a start and an exclusive end (either may carry an offset). */
export function periodText(start: string | null | undefined, endExclusive: string | null | undefined): string {
  if (!start || !endExclusive) return DASH
  const from = fmtDay(isoMs(start))
  const endMs = eatTime(isoMs(endExclusive))
  if (endMs === null) return `${from} – ${endExclusive}`
  // An exclusive midnight end means the period runs to the end of the day before.
  const atMidnight = eatClock(eatIso(endMs)) === '00:00'
  const to = atMidnight ? fmtDay(eatIso(endMs - 1)) : `${fmtDay(eatIso(endMs))}, ${eatClock(eatIso(endMs))}`
  const year = (s: string) => / (\d{4})$/.exec(s)?.[1]
  return `${year(from) && year(from) === year(to) ? from.replace(/ \d{4}$/, '') : from} – ${to}`
}

/** A JSON key in plain words: a known label, else "snake_case" -> "Snake case". */
export function keyText(key: string, labels: Record<string, string> = {}): string {
  const known = labels[key]
  if (known) return known
  const s = key.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

const COMPONENTS: Record<string, string> = { RBC: 'Red cells', WB: 'Whole blood', PLT: 'Platelets', FFP: 'Plasma', CRYO: 'Cryoprecipitate' }

/** "RBC" -> "Red cells" */
export function componentText(code: string): string {
  return COMPONENTS[code] ?? code
}
