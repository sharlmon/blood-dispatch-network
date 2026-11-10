import type { LocationQuery } from 'vue-router'
import type { ApiFailure } from './useApi'
import { apiFailure } from './useApi'
import type { AuditEntry, Option, PassReason, RankInput, RankResult, RequestAction, RequestBundle, RequestRecord, RequestStatus, RequestUpdate } from '~/utils/engine'
import { passedOver, siteNames, siteStep, statusAfter, statusLabel, statusStage, toApiGroup, toDisplayGroup, toOptions } from '~/utils/engine'
import { mockRankResult } from '~/utils/mock'
import { eatIso, eatTime } from '~/utils/format'

/** The request on screen. `id` is the server id (BDN-...), or null for a preview or the demo data. */
export interface DispatchRequest {
  id: string | null
  facilityId: string
  facilityName: string | null
  /** as people write it: "A−", "O+", or "Unknown" (then group O only) */
  group: string
  units: number
  limitH: number
  /** request time as the engine echoed it (East Africa Time, no offset) */
  requestedAt: string
  createdAt: string | null
}

export interface SearchInput {
  facilityId: string
  facilityName?: string | null
  group: string
  units: number
  limitH: number
  /** EAT; the API uses the demo clock or now when it is left out */
  requestedAt?: string
}

/** The site on record for the request: a ranked option, or today's way (the baseline site). */
export interface PickedSite {
  id: string
  name: string
  /** the ranked option with its arrival range; null for today's way, which the arrival model did not rank */
  option: Option | null
}

export type RestoreResult = 'ok' | 'empty' | 'error'
type Busy = 'search' | 'restore' | 'event' | null

const STEP_TOAST: Partial<Record<RequestAction, string>> = {
  shelf_confirmed: 'Recorded: shelf confirmed',
  dispatched: 'Recorded: units dispatched',
  arrived: 'Units arrived. Check every bag.'
}

function qText(v: unknown): string | null {
  const s = Array.isArray(v) ? v[0] : v
  return typeof s === 'string' && s.trim() ? s.trim() : null
}

/** A shareable link such as /results?group=B%2B&units=2&limit=3&facility=HSP-004&at=2026-10-31T00:58 */
function queryInput(q: LocationQuery): (SearchInput & { pick: string | null; stage: number }) | null {
  const group = qText(q.group)
  if (!group) return null
  const units = Math.round(Number(qText(q.units)))
  const limit = Number(qText(q.limit))
  return {
    facilityId: qText(q.facility) ?? '',
    group: toDisplayGroup(toApiGroup(group)),
    units: units >= 1 && units <= 50 ? units : 2,
    limitH: limit > 0 && limit <= 72 ? limit : 6,
    requestedAt: qText(q.at) ?? undefined,
    pick: qText(q.pick),
    stage: Math.max(0, Math.min(4, Math.round(Number(qText(q.stage))) || 0))
  }
}

/**
 * Request, ranked options, selection, status and audit trail, shared by every screen.
 * Live mode (an API base is set): the server is the source of truth, and every response replaces
 * the local status and audit. Static demo (no API): the fictional mock and a local audit list.
 * A link with ?demo=1 and no ?id= is the public example: the fictional mock in every build, and
 * nothing is sent to the API (`local`). API calls run on the client only.
 */
export function useDispatch() {
  const { api, fail, engineUp, live } = useApi()
  const { toast } = useToast()
  const route = useRoute()
  const { hospital } = useSite()
  const facilities = useFacilities()

  const request = useState<DispatchRequest | null>('dispatch.request', () => null)
  const result = useState<RankResult | null>('dispatch.result', () => null)
  const record = useState<RequestRecord | null>('dispatch.record', () => null)
  const selectedId = useState<string | null>('dispatch.selected', () => null)
  const status = useState<RequestStatus>('dispatch.status', () => 'open')
  const audit = useState<AuditEntry[]>('dispatch.audit', () => [])
  const busy = useState<Busy>('dispatch.busy', () => null)
  const error = useState<ApiFailure | null>('dispatch.error', () => null)
  /** A live build showing the fictional example (?demo=1): every step stays on this screen. */
  const local = useState<boolean>('dispatch.local', () => false)
  /** Steps are recorded by the API (live, and not the example). */
  const viaApi = computed(() => live && !local.value)

  const ranking = computed(() => result.value?.ranking ?? null)
  const options = computed(() => (result.value ? toOptions(result.value) : []))
  const selected = computed(() => options.value.find(o => o.id === selectedId.value) ?? null)
  const top = computed(() => options.value[0] ?? null)
  const baseline = computed(() => ranking.value?.baseline ?? null)
  const limitH = computed(() => result.value?.clinician_limit_h ?? request.value?.limitH ?? 6)
  const tooLong = computed(() => ranking.value?.advice === 'consider_emergency_O_or_transfer')
  const noFullSource = computed(() => ranking.value?.advice === 'no_full_source' || (options.value.length > 0 && options.value.every(o => o.partial)))
  /**
   * How much sooner than today's quote the top source may arrive, as an estimated 8-in-10 range in
   * hours (the quote minus the slow end, to the quote minus the fast end). Null unless even the slow
   * end beats the quote. The quote itself is one number with no range; `assumed` when the top source
   * is a hospital, whose dispatch time is assumed from regional-centre data.
   */
  const sooner = computed(() => {
    const b = baseline.value
    const t = top.value
    if (!b?.facility_id || b.quote_hours == null || !t) return null
    const lo = b.quote_hours - t.p90
    return lo >= 0.1 ? { lo, hi: b.quote_hours - t.p10, assumed: t.kind === 'hospital' } : null
  })
  /** The hospital the ranking is for. */
  const requesterName = computed(() => result.value?.requester?.name ?? request.value?.facilityName ?? request.value?.facilityId ?? null)
  const names = computed(() => siteNames(result.value))
  /** Sites passed over (not on the shelf, or no answer in time), with what was recorded. */
  const passed = computed(() => passedOver(audit.value))
  const passedIds = computed(() => passed.value.map(p => p.id))
  const passedReason = (id: string): PassReason | null => passed.value.find(p => p.id === id)?.action ?? null
  /** The clinician's latest recorded decision on this request. */
  const decision = computed<'groupO' | 'transfer' | null>(() => {
    const last = [...audit.value].reverse().find(a => a.action === 'emergency_group_o' || a.action === 'transfer_patient')
    return last ? (last.action === 'emergency_group_o' ? 'groupO' : 'transfer') : null
  })
  /** The source the lab worker picked (cleared again when it was not on the shelf). */
  const pickedId = computed(() => record.value?.selected_facility_id ?? null)
  /** The picked site: a ranked option, or today's way, which may be picked without being listed. */
  const pickedSite = computed<PickedSite | null>(() => {
    const id = pickedId.value
    if (!id) return null
    const option = options.value.find(o => o.id === id) ?? null
    return { id, name: option?.name ?? record.value?.selected_name ?? names.value[id] ?? id, option }
  })
  /** When the source now checking its shelf was picked. */
  const pickedAt = computed(() => (status.value === 'awaiting_shelf' ? [...audit.value].reverse().find(a => a.action === 'pick')?.at ?? null : null))

  const demoQuery = (): Record<string, string> => (local.value || route.query.demo === '1' ? { demo: '1' } : {})
  function linkQuery(pick: string | null, extra: Record<string, string> = {}): Record<string, string> {
    const r = request.value
    if (!r) return demoQuery()
    if (r.id) return { id: r.id, ...demoQuery() }
    const q: Record<string, string> = { group: r.group, units: String(r.units), limit: String(r.limitH) }
    if (viaApi.value) q.facility = r.facilityId
    if (live) q.at = r.requestedAt // the same request time when the link is opened again
    if (pick) q.pick = pick
    return { ...q, ...extra, ...demoQuery() }
  }
  const resultsLink = computed(() => ({ path: '/results', query: linkQuery(selectedId.value) }))
  /** Tracking needs a stored request when steps go to the API; a preview has nothing to track yet. */
  const canTrack = computed(() => !!request.value && (!viaApi.value || !!request.value.id))
  const trackLink = computed(() => (canTrack.value
    ? { path: '/track', query: linkQuery(pickedId.value ?? selectedId.value, { stage: String(statusStage(status.value)) }) }
    : resultsLink.value))

  const body = (r: { facilityId: string; group: string; units: number; limitH: number; requestedAt?: string }): RankInput => ({
    facility_id: r.facilityId,
    patient_group: toApiGroup(r.group),
    units_needed: r.units,
    component: 'RBC',
    limit_h: r.limitH,
    ...(r.requestedAt ? { requested_at: r.requestedAt } : {})
  })

  /** Take a stored request from the server (its record, ranking and full audit trail). */
  function adopt(rec: RequestRecord, res: RankResult | null, trail: AuditEntry[]) {
    local.value = false
    if (res) result.value = res
    record.value = rec
    status.value = rec.status
    audit.value = trail
    request.value = {
      id: rec.id,
      facilityId: rec.facility_id,
      facilityName: rec.facility_name ?? result.value?.requester?.name ?? null,
      group: toDisplayGroup(rec.patient_group),
      units: rec.units_needed,
      limitH: rec.limit_h,
      requestedAt: rec.requested_at,
      createdAt: rec.created_at
    }
    const ids = options.value.map(o => o.id)
    const skip = passedIds.value
    if (rec.selected_facility_id) selectedId.value = rec.selected_facility_id
    else if (!selectedId.value || !ids.includes(selectedId.value) || skip.includes(selectedId.value)) {
      selectedId.value = ids.find(id => !skip.includes(id)) ?? ids[0] ?? null
    }
  }

  // ---------- demo data (static demo, or the example): fictional mock and a local audit list ----------

  function note(action: string, detail: Record<string, unknown> = {}) {
    const last = audit.value[audit.value.length - 1]
    audit.value = [...audit.value, { id: (last?.id ?? 0) + 1, request_id: 'demo', at: eatIso(), action, actor: { user_id: null, org_id: null, org_role: null }, detail }]
  }

  const detailText = (v: unknown) => (typeof v === 'string' && v ? v : null)

  /** The API's workflow rules, applied locally. A pick names its site in `detail` (facility_id, facility_name). */
  function localMove(action: RequestAction, detail: Record<string, unknown> = {}): boolean {
    const next = statusAfter(status.value, action)
    if (!next) {
      toast({ tone: 'warn', title: 'That step is not possible now', body: `The request is ${statusLabel(status.value).toLowerCase()}.` })
      return false
    }
    status.value = next
    const rec = record.value
    if (rec) {
      const pick = action === 'pick'
      const clear = action === 'not_on_shelf' || action === 'confirm_timeout'
      record.value = {
        ...rec,
        status: next,
        selected_facility_id: pick ? detailText(detail.facility_id) : clear ? null : rec.selected_facility_id,
        selected_name: pick ? detailText(detail.facility_name) : clear ? null : rec.selected_name
      }
    }
    note(action, detail)
    return true
  }

  function startDemo(input: SearchInput, pick: string | null = null, stage = 0) {
    // The example always runs for the fictional requester, as on the landing page.
    const res = mockRankResult({ group: input.group, units: input.units, limitH: input.limitH, requestedAt: input.requestedAt, requesterName: local.value ? undefined : hospital.value })
    const rk = res.ranking
    const createdAt = eatIso()
    result.value = res
    status.value = 'open'
    audit.value = []
    // A local stand-in for the server's record, so screens read the pick the same way in both modes.
    record.value = {
      id: 'demo', created_at: createdAt, facility_id: res.requester.facility_id, facility_name: res.requester.name,
      patient_group: rk.request.patient_group, units_needed: rk.request.units_needed, component: 'RBC', limit_h: input.limitH,
      requested_at: rk.request.requested_at, status: 'open', selected_facility_id: null, selected_name: null
    }
    request.value = {
      id: null,
      facilityId: res.requester.facility_id,
      facilityName: res.requester.name,
      group: toDisplayGroup(rk.request.patient_group),
      units: rk.request.units_needed,
      limitH: input.limitH,
      requestedAt: rk.request.requested_at,
      createdAt
    }
    const ids = rk.options.map(o => o.facility_id)
    const base = rk.baseline.facility_id
    selectedId.value = pick && (ids.includes(pick) || pick === base) ? pick : ids[0] ?? null
    note('request_created', {
      patient_group: rk.request.patient_group, units_needed: rk.request.units_needed, component: 'RBC', limit_h: input.limitH,
      requested_at: rk.request.requested_at, as_of_stock_date: rk.request.as_of_stock_date, advice: rk.advice,
      model_used: rk.model_used, option_facility_ids: ids, baseline_facility_id: base
    })
    // A demo link can open part-way through (?stage=1 shelf check ... 4 arrived).
    const first = selectedId.value
    const firstName = first ? rk.options.find(o => o.facility_id === first)?.name ?? (first === base ? rk.baseline.name : null) ?? first : null
    const steps: RequestAction[] = ['pick', 'shelf_confirmed', 'dispatched', 'arrived']
    for (const s of steps.slice(0, first ? stage : 0)) {
      localMove(s, s === 'pick' ? { facility_id: first, facility_name: firstName } : {})
    }
  }

  function demoOr<T>(fn: () => T): T | null {
    try {
      return fn()
    } catch (e) {
      toast({ tone: 'warn', title: 'Check the request', body: e instanceof Error ? e.message : String(e) })
      return null
    }
  }

  // ---------- live (API) ----------

  async function preview(want: SearchInput & { pick: string | null }): Promise<RestoreResult> {
    busy.value = 'restore'
    error.value = null
    try {
      const facilityId = want.facilityId || (await facilities.defaultId())
      if (!facilityId) {
        error.value = facilities.error.value ?? { status: null, code: 'no_facility', message: 'Choose the requesting hospital on the request page.', network: false }
        return 'error'
      }
      const res = await api<RankResult>('/api/rank', { method: 'POST', body: body({ ...want, facilityId }) })
      engineUp()
      const rk = res.ranking
      local.value = false
      result.value = res
      record.value = null
      status.value = 'open'
      audit.value = []
      request.value = {
        id: null,
        facilityId,
        facilityName: res.requester?.name ?? null,
        group: toDisplayGroup(rk.request.patient_group),
        units: rk.request.units_needed,
        limitH: res.clinician_limit_h,
        requestedAt: rk.request.requested_at,
        createdAt: null
      }
      const ids = rk.options.map(o => o.facility_id)
      selectedId.value = want.pick && ids.includes(want.pick) ? want.pick : ids[0] ?? null
      return 'ok'
    } catch (e) {
      error.value = fail(e)
      return 'error'
    } finally {
      busy.value = null
    }
  }

  /** A preview has no server id yet: store it (same inputs, same request time) so every decision is audited. */
  async function ensureStored(): Promise<string> {
    const r = request.value!
    if (r.id) return r.id
    const keep = selectedId.value
    const res = await api<RequestBundle>('/api/requests', { method: 'POST', body: body(r) })
    engineUp()
    adopt(res.request, res.result, res.audit)
    if (keep && options.value.some(o => o.id === keep)) selectedId.value = keep
    await navigateTo({ path: route.path, query: { id: res.request.id, ...demoQuery() } }, { replace: true })
    return res.request.id
  }

  /** A step answered 409: the request changed on another screen (a new pick, a site step). Show the server's state. */
  async function changedElsewhere(id: string, why: string) {
    try {
      const res = await api<RequestBundle>(`/api/requests/${encodeURIComponent(id)}`)
      adopt(res.request, res.result, res.audit)
      toast({ tone: 'warn', title: 'This request changed on another screen', body: `${why} The latest state is on screen now: check it before the next step.`.trim(), ms: 9000 })
    } catch (e) {
      error.value = fail(e)
    }
  }

  /**
   * Record one workflow step on the server. A site step names the selected site (`facilityId`), so
   * the API refuses it (409) when someone has picked another site meanwhile. False when it failed
   * (the user has been told).
   */
  async function step(action: RequestAction, facilityId?: string | null): Promise<boolean> {
    if (busy.value || !request.value) return false
    busy.value = 'event'
    error.value = null
    let id: string | null = null
    try {
      id = await ensureStored()
      const res = await api<RequestUpdate>(`/api/requests/${encodeURIComponent(id)}/events`, {
        method: 'POST',
        body: facilityId ? { action, facility_id: facilityId } : { action }
      })
      record.value = res.request
      status.value = res.request.status
      audit.value = res.audit
      if (res.request.selected_facility_id) selectedId.value = res.request.selected_facility_id
      return true
    } catch (e) {
      const f = apiFailure(e)
      if (id && f.status === 409) await changedElsewhere(id, f.message)
      else error.value = fail(e)
      return false
    } finally {
      busy.value = null
    }
  }

  // ---------- actions ----------

  /** The lab worker submits a request: stored, ranked and audited by the API, then the results. */
  async function search(input: SearchInput) {
    if (busy.value) return
    error.value = null
    local.value = false
    if (!live) {
      if (demoOr(() => startDemo(input)) === null) return
      return navigateTo(resultsLink.value)
    }
    busy.value = 'search'
    try {
      const res = await api<RequestBundle>('/api/requests', { method: 'POST', body: body(input) })
      engineUp()
      selectedId.value = null
      adopt(res.request, res.result, res.audit)
      busy.value = null
      return navigateTo({ path: '/results', query: { id: res.request.id, ...demoQuery() } })
    } catch (e) {
      error.value = fail(e)
    } finally {
      busy.value = null
    }
  }

  /**
   * Put the request named by the URL on screen: ?id= loads a stored request; ?group= (with units,
   * limit, facility, at) runs a preview that stores nothing, or with ?demo=1 the fictional example.
   * `preview: false` for screens that need a stored request.
   */
  async function loadFromQuery(q: LocationQuery, opts: { preview?: boolean } = {}): Promise<RestoreResult> {
    if (import.meta.server) return 'empty'
    if (matches(q)) return 'ok'
    const id = qText(q.id)
    if (id) {
      if (!live) return 'empty'
      busy.value = 'restore'
      error.value = null
      try {
        const res = await api<RequestBundle>(`/api/requests/${encodeURIComponent(id)}`)
        selectedId.value = null
        adopt(res.request, res.result, res.audit)
        return 'ok'
      } catch (e) {
        error.value = fail(e)
        return 'error'
      } finally {
        busy.value = null
      }
    }
    const want = queryInput(q)
    if (want && (!live || q.demo === '1')) {
      // Demo data: the static demo, or the public example, which a signed-out visitor can open.
      local.value = live
      return demoOr(() => startDemo(want, want.pick, want.stage)) === null ? 'error' : 'ok'
    }
    if (want && opts.preview !== false) return preview(want)
    return 'empty'
  }

  /** The state on screen already is the one the URL names (no query: any request on screen). */
  function matches(q: LocationQuery): boolean {
    const r = request.value
    if (!r || !result.value) return false
    const id = qText(q.id)
    if (id) return r.id === id
    const want = queryInput(q)
    if (!want) return true
    return !r.id && local.value === (live && q.demo === '1')
      && r.group === want.group && r.units === want.units && r.limitH === want.limitH
      && (!viaApi.value || !want.facilityId || r.facilityId === want.facilityId)
      && (!want.requestedAt || r.requestedAt.startsWith(want.requestedAt))
  }

  function select(id: string) {
    selectedId.value = id
  }

  /**
   * The lab worker picks a source: a ranked option, or today's way (the baseline site). The
   * supplying site then checks its shelf. Switching away from a site that is checking its shelf
   * reminds the worker to call that site off.
   */
  async function pickSite(id: string, name: string) {
    if (!request.value) return
    const before = status.value === 'awaiting_shelf' && pickedSite.value?.id !== id ? pickedSite.value : null
    const ok = viaApi.value ? await step('pick', id) : localMove('pick', { facility_id: id, facility_name: name })
    if (!ok) return
    toast(before
      ? { tone: 'warn', title: 'Pick switched', body: `Call ${before.name} to stop its shelf check. Ask ${name} to confirm the units are on the shelf.`, ms: 9000 }
      : { tone: 'ok', title: 'Pick recorded', body: `Ask ${name} to confirm the units are on the shelf. A person approves every step.` })
    return navigateTo(trackLink.value)
  }

  /** Pick the selected option. */
  async function confirmSelection() {
    const o = selected.value
    if (!o) return
    return pickSite(o.id, o.name)
  }

  /** A clinician's decision when the wait is too long. Always audited. */
  async function decide(kind: 'groupO' | 'transfer') {
    const action: RequestAction = kind === 'groupO' ? 'emergency_group_o' : 'transfer_patient'
    const ok = viaApi.value ? await step(action) : localMove(action)
    if (!ok) return
    toast(kind === 'groupO'
      ? { tone: 'warn', title: 'Emergency group O recorded', body: 'Saved in the audit log. The lab confirms the units before release.' }
      : { tone: 'warn', title: 'Patient transfer recorded', body: 'Saved in the audit log. A person arranges the transfer.' })
  }

  /**
   * The supplying site's next step (shelf confirmed, then dispatched, then arrived), recorded at the
   * requesting hospital as the site reports it. It names the picked site, so a stale screen cannot
   * book it against another one.
   */
  async function advance() {
    const action = siteStep(status.value)
    if (!action) return
    const ok = viaApi.value ? await step(action, pickedId.value) : localMove(action)
    if (ok) toast({ tone: action === 'arrived' ? 'ok' : 'info', title: STEP_TOAST[action] ?? statusLabel(status.value) })
  }

  /**
   * Move on from the picked site: it said the units are not on the shelf (not_on_shelf), or it did
   * not answer in time (confirm_timeout). Records it against that site, then selects the next source by rank.
   */
  async function nextSource(reason: PassReason = 'not_on_shelf') {
    const prev = pickedSite.value
    const waited = pickedAt.value ? eatTime(pickedAt.value) : null
    const ok = viaApi.value
      ? await step(reason, prev?.id ?? null)
      : localMove(reason, { previous_facility_id: prev?.id ?? null, waited_minutes: waited === null ? null : Math.round((Date.now() - waited) / 6000) / 10 })
    if (!ok) return
    const ids = options.value.map(o => o.id)
    const skip = new Set([...passedIds.value, ...(prev ? [prev.id] : [])])
    const from = prev ? ids.indexOf(prev.id) + 1 : 0
    const next = [...ids.slice(from), ...ids.slice(0, from)].find(id => !skip.has(id)) ?? null
    selectedId.value = next
    const o = options.value.find(x => x.id === next)
    toast(o
      ? { tone: 'info', title: `Next: ${o.name}`, body: 'Check it, then request from it.' }
      : { tone: 'warn', title: 'No other source on the list', body: 'Consider emergency group O or a transfer. A person makes this call.' })
    return navigateTo(resultsLink.value)
  }

  async function cancel() {
    if (viaApi.value && !request.value?.id) return
    const ok = viaApi.value ? await step('cancel') : localMove('cancel')
    if (ok) toast({ tone: 'info', title: 'Request cancelled', body: 'Saved in the audit log.' })
  }

  return {
    live, local, request, result, record, ranking, options, selected, selectedId, top, baseline, limitH, tooLong, noFullSource, sooner,
    requesterName, status, audit, names, passed, passedIds, passedReason, decision, pickedId, pickedSite, pickedAt, busy, error,
    resultsLink, trackLink, canTrack,
    search, loadFromQuery, matches, select, pickSite, confirmSelection, decide, advance, nextSource, cancel
  }
}
