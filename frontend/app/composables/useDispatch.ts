import type { LocationQuery } from 'vue-router'
import type { ApiFailure } from './useApi'
import type { AuditEntry, RankInput, RankResult, RequestAction, RequestBundle, RequestRecord, RequestStatus, RequestUpdate } from '~/utils/engine'
import { passedOver, siteNames, siteStep, statusAfter, statusLabel, statusStage, toApiGroup, toDisplayGroup, toOptions } from '~/utils/engine'
import { mockRankResult } from '~/utils/mock'
import { eatIso } from '~/utils/format'

/** The request on screen. `id` is the server id (BDN-...), or null for a preview or the static demo. */
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

export type RestoreResult = 'ok' | 'empty' | 'error'
type Busy = 'search' | 'restore' | 'event' | null

const STEP_TOAST: Partial<Record<RequestAction, string>> = {
  shelf_confirmed: 'Supplying site confirmed the shelf',
  dispatched: 'Units dispatched',
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
 * API calls run on the client only.
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

  const ranking = computed(() => result.value?.ranking ?? null)
  const options = computed(() => (result.value ? toOptions(result.value) : []))
  const selected = computed(() => options.value.find(o => o.id === selectedId.value) ?? null)
  const top = computed(() => options.value[0] ?? null)
  const baseline = computed(() => ranking.value?.baseline ?? null)
  const limitH = computed(() => result.value?.clinician_limit_h ?? request.value?.limitH ?? 6)
  const tooLong = computed(() => ranking.value?.advice === 'consider_emergency_O_or_transfer')
  const noFullSource = computed(() => ranking.value?.advice === 'no_full_source' || (options.value.length > 0 && options.value.every(o => o.partial)))
  /** Hours sooner than today's single-number quote; 0 when no regional centre has enough stock. */
  const sooner = computed(() => {
    const q = baseline.value?.quote_hours
    return q != null && baseline.value?.facility_id && top.value ? q - top.value.p50 : 0
  })
  const names = computed(() => siteNames(result.value))
  const passed = computed(() => passedOver(audit.value))
  /** The clinician's latest recorded decision on this request. */
  const decision = computed<'groupO' | 'transfer' | null>(() => {
    const last = [...audit.value].reverse().find(a => a.action === 'emergency_group_o' || a.action === 'transfer_patient')
    return last ? (last.action === 'emergency_group_o' ? 'groupO' : 'transfer') : null
  })
  /** The source the lab worker picked (cleared again when it was not on the shelf). */
  const pickedId = computed(() => record.value?.selected_facility_id ?? null)
  /** When the source now checking its shelf was picked. */
  const pickedAt = computed(() => (status.value === 'awaiting_shelf' ? [...audit.value].reverse().find(a => a.action === 'pick')?.at ?? null : null))

  const demoQuery = (): Record<string, string> => (route.query.demo === '1' ? { demo: '1' } : {})
  function linkQuery(pick: string | null, extra: Record<string, string> = {}): Record<string, string> {
    const r = request.value
    if (!r) return demoQuery()
    if (r.id) return { id: r.id, ...demoQuery() }
    const q: Record<string, string> = { group: r.group, units: String(r.units), limit: String(r.limitH) }
    if (live) { q.facility = r.facilityId; q.at = r.requestedAt }
    if (pick) q.pick = pick
    return { ...q, ...extra, ...demoQuery() }
  }
  const resultsLink = computed(() => ({ path: '/results', query: linkQuery(selectedId.value) }))
  /** Tracking needs a stored request in live mode; a preview has nothing to track yet. */
  const canTrack = computed(() => !!request.value && (!live || !!request.value.id))
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
    if (rec.selected_facility_id) selectedId.value = rec.selected_facility_id
    else if (!selectedId.value || !ids.includes(selectedId.value) || passed.value.includes(selectedId.value)) {
      selectedId.value = ids.find(id => !passed.value.includes(id)) ?? ids[0] ?? null
    }
  }

  // ---------- static demo (no API): fictional mock and a local audit list ----------

  function note(action: string, detail: Record<string, unknown> = {}) {
    const last = audit.value[audit.value.length - 1]
    audit.value = [...audit.value, { id: (last?.id ?? 0) + 1, request_id: 'demo', at: eatIso(), action, actor: { user_id: null, org_id: null, org_role: null }, detail }]
  }

  function localMove(action: RequestAction, detail: Record<string, unknown> = {}): boolean {
    const next = statusAfter(status.value, action)
    if (!next) {
      toast({ tone: 'warn', title: 'That step is not possible now', body: `The request is ${statusLabel(status.value).toLowerCase()}.` })
      return false
    }
    status.value = next
    const rec = record.value
    if (rec) {
      const pick = action === 'pick' ? selected.value : null
      const clear = action === 'not_on_shelf' || action === 'confirm_timeout'
      record.value = {
        ...rec,
        status: next,
        selected_facility_id: pick ? pick.id : clear ? null : rec.selected_facility_id,
        selected_name: pick ? pick.name : clear ? null : rec.selected_name
      }
    }
    note(action, detail)
    return true
  }

  function startDemo(input: SearchInput, pick: string | null = null, stage = 0) {
    const res = mockRankResult({ group: input.group, units: input.units, limitH: input.limitH, requestedAt: input.requestedAt, requesterName: hospital.value })
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
    selectedId.value = pick && ids.includes(pick) ? pick : ids[0] ?? null
    note('request_created', {
      patient_group: rk.request.patient_group, units_needed: rk.request.units_needed, component: 'RBC', limit_h: input.limitH,
      requested_at: rk.request.requested_at, as_of_stock_date: rk.request.as_of_stock_date, advice: rk.advice,
      model_used: rk.model_used, option_facility_ids: ids, baseline_facility_id: rk.baseline.facility_id
    })
    // A demo link can open part-way through (?stage=1 shelf check ... 4 arrived).
    const steps: RequestAction[] = ['pick', 'shelf_confirmed', 'dispatched', 'arrived']
    for (const s of steps.slice(0, selectedId.value ? stage : 0)) {
      localMove(s, s === 'pick' ? { facility_id: selected.value?.id ?? null, facility_name: selected.value?.name ?? null } : {})
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

  /** Record one workflow step on the server. False when it failed (the user has been told). */
  async function step(action: RequestAction, facilityId?: string | null): Promise<boolean> {
    if (busy.value || !request.value) return false
    busy.value = 'event'
    error.value = null
    try {
      const id = await ensureStored()
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
      error.value = fail(e)
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
   * limit, facility, at) runs a preview that stores nothing. `preview: false` for screens that need a stored request.
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
    if (want && !live) return demoOr(() => startDemo(want, want.pick, want.stage)) === null ? 'error' : 'ok'
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
    return !r.id && r.group === want.group && r.units === want.units && r.limitH === want.limitH
      && (!live || !want.facilityId || r.facilityId === want.facilityId)
      && (!want.requestedAt || r.requestedAt.startsWith(want.requestedAt))
  }

  function select(id: string) {
    selectedId.value = id
  }

  /** The lab worker picks the selected source; the supplying site then checks its shelf. */
  async function confirmSelection() {
    const o = selected.value
    if (!o || !request.value) return
    const ok = live ? await step('pick', o.id) : localMove('pick', { facility_id: o.id, facility_name: o.name })
    if (!ok) return
    toast({ tone: 'ok', title: 'Pick recorded', body: `Ask ${o.name} to confirm the units are on the shelf. A person approves every step.` })
    return navigateTo(trackLink.value)
  }

  /** A clinician's decision when the wait is too long. Always audited. */
  async function decide(kind: 'groupO' | 'transfer') {
    const action: RequestAction = kind === 'groupO' ? 'emergency_group_o' : 'transfer_patient'
    const ok = live ? await step(action) : localMove(action)
    if (!ok) return
    toast(kind === 'groupO'
      ? { tone: 'warn', title: 'Emergency group O recorded', body: 'Saved in the audit log. The lab confirms the units before release.' }
      : { tone: 'warn', title: 'Patient transfer recorded', body: 'Saved in the audit log. A person arranges the transfer.' })
  }

  /** Demo only: stands in for the supplying site (shelf confirmed, then dispatched, then arrived). */
  async function advance() {
    const action = siteStep(status.value)
    if (!action) return
    const ok = live ? await step(action) : localMove(action)
    if (ok) toast({ tone: action === 'arrived' ? 'ok' : 'info', title: STEP_TOAST[action] ?? statusLabel(status.value) })
  }

  /** The picked site does not have the units (or did not answer in time): record it, select the next source by rank. */
  async function nextSource(reason: 'not_on_shelf' | 'confirm_timeout' = 'not_on_shelf') {
    const prev = options.value.find(o => o.id === pickedId.value) ?? selected.value
    const ok = live ? await step(reason) : localMove(reason, { facility_id: prev?.id ?? null, facility_name: prev?.name ?? null })
    if (!ok) return
    const ids = options.value.map(o => o.id)
    const skip = new Set([...passed.value, ...(prev ? [prev.id] : [])])
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
    if (live && !request.value?.id) return
    const ok = live ? await step('cancel') : localMove('cancel')
    if (ok) toast({ tone: 'info', title: 'Request cancelled', body: 'Saved in the audit log.' })
  }

  return {
    live, request, result, record, ranking, options, selected, selectedId, top, baseline, limitH, tooLong, noFullSource, sooner,
    status, audit, names, passed, decision, pickedId, pickedAt, busy, error, resultsLink, trackLink, canTrack,
    search, loadFromQuery, matches, select, confirmSelection, decide, advance, nextSource, cancel
  }
}
