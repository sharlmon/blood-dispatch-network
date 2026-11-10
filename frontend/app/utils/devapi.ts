// Adapter between the backend API on `dev` (docs: backend/docs/api.md) and the shapes the screens
// were built on (utils/engine.ts). Framework-free: it runs in plain Node for the tests.
//
// The API keeps one request record with the engine's ranking, a status (pending, awaiting_confirmation,
// confirmed, dispatched, received, cancelled) and an audit list. The screens read a RequestBundle:
// the record, the ranking with the sites' positions, and an audit trail. This file converts one to
// the other and builds the call for each workflow step. It decides nothing about blood: the server
// owns every rule, and every step is still taken by a person.
import type {
  AuditEntry, EngineRanking, Facility, RankResult, RequestAction, RequestBundle, RequestRecord, RequestStatus, Requester, Site
} from './engine.ts'

const EAT_MS = 3 * 3600_000
const pad = (n: number) => String(n).padStart(2, '0')

/** An ISO time as East Africa Time, with the +03:00 offset ("2026-10-31T01:04:00+03:00"). */
export function eatStamp(iso: string): string {
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return iso
  return `${eatLocal(t)}+03:00`
}

/** An ISO time as East Africa Time with no offset, the way the engine echoes the request time. */
export function eatLocal(ms: number): string {
  const d = new Date(ms + EAT_MS)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
}

export function eatNoOffset(iso: string): string {
  const t = Date.parse(iso)
  return Number.isFinite(t) ? eatLocal(t) : iso
}

/** A request time typed or linked on a screen (EAT, no offset) as the API wants it (with the offset). */
export function apiTime(eat: string): string {
  return /([zZ]|[+-]\d\d:?\d\d)$/.test(eat) ? eat : `${eat.length === 16 ? `${eat}:00` : eat}+03:00`
}

// ---------- shapes the API returns ----------

export interface DevFacility { id: string; name: string; kind: 'hospital' | 'centre'; details?: Record<string, unknown> }

export interface DevRanking extends Omit<EngineRanking, 'request'> {
  request: EngineRanking['request']
}

export interface DevRequest {
  id: string
  facility_id: string
  blood_group: string
  units: number
  status: string
  supplier_id: string | null
  attempt: number
  deadline: string | null
  created_at: string
  updated_at: string
  request?: { facility_id: string; patient_group: string; units_needed: number; component: string; requested_at: string; clinician_limit_h: number }
  ranking?: DevRanking
  selected_option?: { facility_id: string; name: string } | null
  allocations?: { blood_group: string; product: string; units: number }[]
}

export interface DevAuditItem {
  id: number
  request_id: string
  action: string
  created_at: string
  details: Record<string, unknown> & { actor?: { user_id?: string | null; org_id?: string | null; org_role?: string | null } }
}

/** What the screens keep on the request record besides the engine fields: the step the server expects next. */
export interface RecordExtras { attempt: number; deadline: string | null }

const CENTRE_TYPE = 'regional_blood_centre'
const SATELLITE_PREFIX = 'SAT-'

const text = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

// ---------- facilities ----------

export function facilityFromDev(f: DevFacility): Facility {
  const d = f.details ?? {}
  const type = text(d.facility_type) ?? (f.kind === 'centre' ? CENTRE_TYPE : 'hospital')
  const isCentre = f.kind === 'centre'
  const isSatellite = f.id.startsWith(SATELLITE_PREFIX)
  return {
    facility_id: f.id,
    name: f.name || text(d.name) || f.id,
    facility_type: type,
    is_hospital: !isCentre && !isSatellite,
    is_centre: isCentre,
    is_satellite: isSatellite,
    county: text(d.county),
    lat: num(d.lat),
    lon: num(d.lon),
    supply_centre_id: text(d.supply_centre_id),
    connectivity: text(d.connectivity),
    has_backup_power: !!d.has_blood_fridge_backup_power
  }
}

function brief(f: Facility | undefined, id: string): Requester {
  return {
    facility_id: id,
    name: f?.name ?? id,
    facility_type: f?.facility_type ?? '',
    county: f?.county ?? null,
    lat: f?.lat ?? null,
    lon: f?.lon ?? null
  }
}

// ---------- ranking ----------

/** The engine's ranking with its request time shown in EAT, plus the sites on the map. */
export function resultFromDev(ranking: DevRanking, limitH: number, requesterId: string, facilities: Facility[]): RankResult {
  const byId = new Map(facilities.map(f => [f.facility_id, f]))
  const rk: EngineRanking = { ...ranking, request: { ...ranking.request, requested_at: eatNoOffset(ranking.request.requested_at) } }
  const sites: Record<string, Site> = {}
  const add = (id: string | null | undefined, hours: number | null) => {
    if (!id || sites[id]) return
    sites[id] = { ...brief(byId.get(id), id), road_km: null, travel_hours_map: hours }
  }
  for (const o of rk.options) add(o.facility_id, o.travel_hours_map)
  add(rk.baseline.facility_id, null)
  return { ranking: rk, clinician_limit_h: limitH, requester: brief(byId.get(requesterId), requesterId), sites }
}

// ---------- the request record ----------

/** The server's status as the screens name it. */
export function statusFromDev(status: string): RequestStatus {
  switch (status) {
    case 'awaiting_confirmation': return 'awaiting_shelf'
    case 'received': return 'arrived'
    case 'confirmed': case 'dispatched': case 'cancelled': return status
    default: return 'open' // pending
  }
}

export type RecordWithExtras = RequestRecord & RecordExtras

export function recordFromDev(d: DevRequest, facilities: Facility[]): RecordWithExtras {
  const byId = new Map(facilities.map(f => [f.facility_id, f]))
  const payload = d.request
  return {
    id: d.id,
    created_at: eatStamp(d.created_at),
    facility_id: d.facility_id,
    facility_name: byId.get(d.facility_id)?.name ?? null,
    patient_group: payload?.patient_group ?? d.blood_group,
    units_needed: payload?.units_needed ?? d.units,
    component: 'RBC',
    limit_h: payload?.clinician_limit_h ?? 6,
    requested_at: eatNoOffset(payload?.requested_at ?? d.created_at),
    status: statusFromDev(d.status),
    selected_facility_id: d.supplier_id,
    selected_name: d.supplier_id ? (d.selected_option?.name ?? byId.get(d.supplier_id)?.name ?? null) : null,
    attempt: d.attempt,
    deadline: d.deadline
  }
}

// ---------- audit trail ----------

/**
 * The API's audit rows as the trail the screens read. A row that says "the next source was tried" is
 * kept apart from a person's pick, and a lapsed confirmation names the site that did not answer
 * (the API's row only carries the attempt number).
 */
export function auditFromDev(items: DevAuditItem[], d: DevRequest, facilities: Facility[]): AuditEntry[] {
  const names = new Map(facilities.map(f => [f.facility_id, f.name]))
  const name = (id: string | null) => (id ? names.get(id) ?? id : null)
  const out: AuditEntry[] = []
  let supplier: string | null = null
  let pickedAt: number | null = null
  for (const row of items) {
    const raw = row.details ?? {}
    const { actor: a, ...rest } = raw as Record<string, unknown> & { actor?: { user_id?: string | null; org_id?: string | null; org_role?: string | null } }
    const actor = { user_id: a?.user_id ?? null, org_id: a?.org_id ?? null, org_role: a?.org_role ?? null }
    const at = eatStamp(row.created_at)
    const make = (action: string, detail: Record<string, unknown>): AuditEntry => ({ id: row.id, request_id: row.request_id, at, action, actor, detail })
    const sid = text(rest.supplier_id)
    switch (row.action) {
      case 'created': {
        const rk = d.ranking
        out.push(make('request_created', {
          patient_group: rest.patient_group, units_needed: rest.units_needed, component: 'RBC', limit_h: rest.clinician_limit_h,
          requested_at: eatNoOffset(String(rest.requested_at ?? row.created_at)),
          as_of_stock_date: rk?.request.as_of_stock_date, advice: rk?.advice ?? null, model_used: rk?.model_used,
          option_facility_ids: rk?.options.map(o => o.facility_id) ?? [], baseline_facility_id: rk?.baseline.facility_id ?? null
        }))
        break
      }
      case 'pick':
        supplier = sid
        pickedAt = Date.parse(row.created_at)
        out.push(make('pick', { facility_id: sid, facility_name: name(sid) }))
        break
      case 'next_supplier_selected':
        supplier = sid
        pickedAt = Date.parse(row.created_at)
        out.push(make('next_supplier_selected', { facility_id: sid, facility_name: name(sid), attempt: rest.attempt }))
        break
      case 'confirm':
        out.push(make('shelf_confirmed', { facility_id: sid, facility_name: name(sid), confirmed_units: rest.confirmed_units }))
        break
      case 'dispatch':
        out.push(make('dispatched', { facility_id: sid, facility_name: name(sid) }))
        break
      case 'receive':
        out.push(make('arrived', { received_units: rest.received_units }))
        break
      case 'reject':
        out.push(make('not_on_shelf', { previous_facility_id: sid ?? supplier, previous_name: name(sid ?? supplier), reason: rest.reason }))
        supplier = null
        break
      case 'confirmation_expired': {
        const waited = pickedAt !== null ? Math.max(0, (Date.parse(row.created_at) - pickedAt) / 60_000) : null
        out.push(make('confirm_timeout', { previous_facility_id: supplier, previous_name: name(supplier), waited_minutes: waited, attempt: rest.attempt }))
        supplier = null
        break
      }
      case 'supplier_skipped':
        out.push(make('supplier_skipped', { facility_id: sid, facility_name: name(sid), reason: rest.reason }))
        break
      case 'cancel':
        out.push(make('cancel', { reason: rest.reason }))
        break
      default:
        out.push(make(row.action, rest))
    }
  }
  return out
}

export function bundleFromDev(d: DevRequest, audit: DevAuditItem[], facilities: Facility[]): RequestBundle & { record: RecordWithExtras } {
  const record = recordFromDev(d, facilities)
  if (!d.ranking) throw new Error('This request has no saved ranking. Cancel it and make a new one.')
  const result = resultFromDev(d.ranking, record.limit_h, d.facility_id, facilities)
  return { request: record, record, result, audit: auditFromDev(audit, d, facilities) }
}

// ---------- workflow steps ----------

export interface StepCall { path: string; body: Record<string, unknown> }

/**
 * The API call for one step the screens know, or null for a step the server does not record
 * (a clinician's choice to use group O or to transfer: it stays on screen and the phone process
 * carries it out). The server checks status, supplier, attempt and units and answers 409 otherwise.
 */
export function stepCall(action: RequestAction, rec: Pick<RecordWithExtras, 'id' | 'selected_facility_id' | 'attempt' | 'units_needed'>, facilityId?: string | null): StepCall | null {
  const base = `/api/requests/${encodeURIComponent(rec.id)}`
  const supplier = facilityId ?? rec.selected_facility_id
  switch (action) {
    case 'pick': return { path: `${base}/pick`, body: { supplier_id: facilityId } }
    case 'shelf_confirmed': return { path: `${base}/confirm`, body: { supplier_id: supplier, attempt: rec.attempt, confirmed_units: rec.units_needed } }
    case 'dispatched': return { path: `${base}/dispatch`, body: { supplier_id: supplier, attempt: rec.attempt } }
    case 'arrived': return { path: `${base}/receive`, body: { received_units: rec.units_needed } }
    case 'not_on_shelf': return { path: `${base}/reject`, body: { supplier_id: supplier, attempt: rec.attempt, reason: 'Units not on the shelf' } }
    case 'confirm_timeout': return { path: `${base}/reject`, body: { supplier_id: supplier, attempt: rec.attempt, reason: 'No shelf confirmation in time' } }
    case 'cancel': return { path: `${base}/cancel`, body: { reason: 'Cancelled by the lab worker' } }
    default: return null
  }
}

/** The body for a new request or a preview. `requestedAt` is EAT; the API wants an offset. */
export function createBody(r: { facilityId: string; group: string; units: number; limitH: number; requestedAt?: string }, toApiGroup: (g: string) => string, withTime = true): Record<string, unknown> {
  return {
    facility_id: r.facilityId,
    patient_group: toApiGroup(r.group),
    units_needed: r.units,
    component: 'RBC',
    clinician_limit_h: r.limitH,
    ...(withTime && r.requestedAt ? { requested_at: apiTime(r.requestedAt) } : {})
  }
}

// ---------- pre-alerts ----------

export interface DevPrealertRun {
  id: string
  created_at: string
  result: {
    generated_at?: string
    stock_as_of?: string
    alerts?: Record<string, unknown>[]
    missing_snapshot?: Record<string, unknown>[]
    assumptions?: string[]
  }
}

const str = (v: unknown, fallback = '') => (typeof v === 'string' ? v : fallback)

/** A saved pre-alert run as the evening list: facility names added, nothing else changed. */
export function prealertsFromDev(run: DevPrealertRun, facilities: Facility[], source: string, synthetic = true) {
  const names = new Map(facilities.map(f => [f.facility_id, f.name]))
  const name = (r: Record<string, unknown>) => names.get(str(r.facility_id)) ?? null
  const r = run.result ?? {}
  return {
    generated_at: str(r.generated_at, run.created_at),
    stock_as_of: str(r.stock_as_of),
    alerts: (r.alerts ?? []).map(a => ({ ...a, facility_name: name(a) })),
    missing_snapshot: (r.missing_snapshot ?? []).map(m => ({ ...m, facility_name: name(m) })),
    assumptions: r.assumptions ?? [],
    synthetic_data: synthetic,
    source
  }
}
