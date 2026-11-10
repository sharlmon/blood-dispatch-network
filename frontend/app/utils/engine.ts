// The Flask API contract (the engine's JSON from docs/RANKING_ENGINE_SPEC.md section 9, wrapped by
// the API), the adapter from an engine option to what the screens show, and small helpers.
// Framework-free on purpose: it runs in plain Node (type stripping) as well as in the app.
// Tested in plain Node: frontend/tests/engine.test.ts (npm test).
import { eatTime, fmtDay, fmtHours } from './format.ts'

// ---------- API contract (field names are exact) ----------

export type EngineAdvice = 'consider_emergency_O_or_transfer' | 'no_full_source'

/** Hours from the request to delivery. p10-p90 is an estimated 80% interval: 8 in 10 arrive inside it. */
export interface EngineEta { p10: number; p50: number; p90: number; wait_p50: number; road_p50: number }

/** One ranked source, exactly as rank_sources() returns it. Stock is the count of as_of_stock_date, unconfirmed. */
export interface EngineOption {
  rank: number
  facility_id: string
  name: string
  facility_type: string
  is_hospital: boolean
  spare: number
  stock_seen: number
  near_expiry: number
  has_backup_power: boolean
  connectivity: string | null
  travel_hours_map: number
  eta: EngineEta
  flags: string[]
  reason: string
  spare_by_group: Record<string, number>
}

/** Today's rule: one quote with no range. All null when no regional centre has enough stock. */
export interface EngineBaseline { facility_id: string | null; name: string | null; quote_hours: number | null; rule: string }

export interface EngineRanking {
  request: { facility_id: string; patient_group: string; units_needed: number; requested_at: string; as_of_stock_date: string }
  mode: 'model' | 'baseline'
  model_used: boolean
  sharing_allowed: boolean
  compatibility_note: string
  stock_note: string
  advice: EngineAdvice | null
  options: EngineOption[]
  baseline: EngineBaseline
}

/** A site on the map. road_km and travel_hours_map run from the site to the requester. */
export interface Site {
  facility_id: string
  name: string
  facility_type: string
  county: string | null
  lat: number | null
  lon: number | null
  road_km: number | null
  travel_hours_map: number | null
}

export type Requester = Omit<Site, 'road_km' | 'travel_hours_map'>

export interface RankResult {
  ranking: EngineRanking
  clinician_limit_h: number
  requester: Requester
  sites: Record<string, Site>
}

export interface RankInput {
  facility_id: string
  patient_group: string
  units_needed: number
  component?: 'RBC'
  requested_at?: string
  limit_h?: number
  mode?: 'model' | 'baseline'
  top_n?: number
}

export type RequestStatus = 'open' | 'awaiting_shelf' | 'confirmed' | 'dispatched' | 'arrived' | 'escalated' | 'cancelled'

export type RequestAction =
  | 'pick' | 'shelf_confirmed' | 'dispatched' | 'arrived' | 'not_on_shelf' | 'confirm_timeout'
  | 'emergency_group_o' | 'transfer_patient' | 'cancel'

export interface RequestRecord {
  id: string
  created_at: string
  facility_id: string
  facility_name: string | null
  patient_group: string
  units_needed: number
  component: string
  limit_h: number
  requested_at: string
  status: RequestStatus
  selected_facility_id: string | null
  selected_name: string | null
}

export interface AuditEntry {
  id: number
  request_id: string
  at: string
  action: string
  actor: { user_id: string | null; org_id: string | null; org_role: string | null }
  detail: Record<string, unknown>
}

export interface Facility {
  facility_id: string
  name: string
  facility_type: string
  is_hospital: boolean
  is_centre: boolean
  is_satellite: boolean
  county: string | null
  lat: number | null
  lon: number | null
  supply_centre_id: string | null
  connectivity: string | null
  has_backup_power: boolean
}

export interface EngineStatus {
  state: 'idle' | 'loading' | 'ready' | 'error'
  model_used: boolean | null
  stock_first: string | null
  stock_last: string | null
  message: string | null
}

export interface HealthResponse { status: string; country: string; engine: EngineStatus }
export interface ApiErrorBody { error: { code: string; message: string } }

/** POST /api/requests and GET /api/requests/<id> */
export interface RequestBundle { request: RequestRecord; result: RankResult; audit: AuditEntry[] }
/** POST /api/requests/<id>/events */
export interface RequestUpdate { request: RequestRecord; audit: AuditEntry[] }

// ---------- What the screens show ----------

export type SourceKind = 'hospital' | 'centre'

/** One source as the screens show it, from an engine option plus the site table. Hours throughout. */
export interface Option {
  id: string
  rank: number
  name: string
  kind: SourceKind
  facilityType: string
  county: string | null
  spare: number
  stockSeen: number
  nearExpiry: number
  spareByGroup: Record<string, number>
  hasBackupPower: boolean
  connectivity: string | null
  travelHoursMap: number | null
  roadKm: number | null
  p10: number
  p50: number
  p90: number
  waitP50: number
  roadP50: number
  flags: string[]
  /** the engine's text, shown verbatim */
  reason: string
  /** the same text, one sentence per item */
  reasons: string[]
  partial: boolean
  /** schematic map position in SourceMap's 400 x 300 viewBox */
  x: number
  y: number
}

/** The engine's reason, one sentence per item. Words and numbers are unchanged. */
export function splitReason(text: string): string[] {
  return text.split(/(?<=[.!?])\s+(?=[A-Z0-9(])/).map(s => s.trim()).filter(Boolean)
}

const YOU = { x: 200, y: 150 }
const REACH = 140 // the farthest site sits this far from YOU
const MIN_R = 46 // keep pins clear of the YOU marker
const MIN_GAP = 30 // two sites in one town would hide each other
const KM_PER_DEG = 111.32
type Spot = { x: number; y: number }

const round1 = (v: number) => Math.round(v * 10) / 10

// Sites closer than MIN_GAP turn around YOU in small steps, so the distance stays true.
function freeSpot(angle: number, r: number, taken: Spot[]): Spot {
  for (let i = 0; i < 16; i++) {
    const a = angle + (i % 2 ? 1 : -1) * Math.ceil(i / 2) * 0.22
    const p = { x: round1(YOU.x + r * Math.cos(a)), y: round1(YOU.y + r * Math.sin(a)) }
    if (taken.every(q => Math.hypot(q.x - p.x, q.y - p.y) >= MIN_GAP)) return p
  }
  return { x: round1(YOU.x + r * Math.cos(angle)), y: round1(YOU.y + r * Math.sin(angle)) }
}

/**
 * Schematic positions: true bearing from the requester (equirectangular km, north up, so y grows
 * southwards), distance scaled so the farthest site is about REACH units from YOU. Sites without
 * coordinates get a fixed spot on a ring by rank.
 */
export function mapSpots(result: RankResult): Record<string, Spot> {
  const me = result.requester
  const offsets = new Map<string, { dx: number; dy: number }>()
  if (me && me.lat != null && me.lon != null) {
    const k = Math.cos((me.lat * Math.PI) / 180) * KM_PER_DEG
    for (const o of result.ranking.options) {
      const s = result.sites?.[o.facility_id]
      if (s && s.lat != null && s.lon != null) offsets.set(o.facility_id, { dx: (s.lon - me.lon) * k, dy: (s.lat - me.lat) * KM_PER_DEG })
    }
  }
  const far = Math.max(0, ...[...offsets.values()].map(v => Math.hypot(v.dx, v.dy)))
  const out: Record<string, Spot> = {}
  const taken: Spot[] = []
  for (const o of result.ranking.options) {
    const v = offsets.get(o.facility_id)
    const d = v ? Math.hypot(v.dx, v.dy) : 0
    const spot = v && far > 0 && d > 0
      ? freeSpot(Math.atan2(-v.dy, v.dx), Math.max(MIN_R, (d / far) * REACH), taken)
      : freeSpot(-Math.PI / 2 + (o.rank - 1) * 2.4, 70 + ((o.rank - 1) % 4) * 20, taken)
    taken.push(spot)
    out[o.facility_id] = spot
  }
  return out
}

/** Adapter: one engine option (plus the result's sites and requester) -> what the screens show. */
export function toOption(o: EngineOption, result: RankResult, spots: Record<string, Spot> = mapSpots(result)): Option {
  const site = result.sites?.[o.facility_id]
  const at = spots[o.facility_id] ?? YOU
  const flags = [...(o.flags ?? [])]
  return {
    id: o.facility_id,
    rank: o.rank,
    name: o.name,
    kind: o.is_hospital ? 'hospital' : 'centre',
    facilityType: o.facility_type,
    county: site?.county ?? null,
    spare: o.spare,
    stockSeen: o.stock_seen,
    nearExpiry: o.near_expiry,
    spareByGroup: { ...(o.spare_by_group ?? {}) },
    hasBackupPower: o.has_backup_power,
    connectivity: o.connectivity ?? null,
    travelHoursMap: o.travel_hours_map ?? site?.travel_hours_map ?? null,
    roadKm: site?.road_km ?? null,
    p10: o.eta.p10,
    p50: o.eta.p50,
    p90: o.eta.p90,
    waitP50: o.eta.wait_p50,
    roadP50: o.eta.road_p50,
    flags,
    reason: o.reason,
    reasons: splitReason(o.reason),
    partial: flags.includes('partial'),
    x: at.x,
    y: at.y
  }
}

export function toOptions(result: RankResult): Option[] {
  const spots = mapSpots(result)
  return result.ranking.options.map(o => toOption(o, result, spots))
}

/** Facility id -> name for every site a result mentions (for audit sentences). */
export function siteNames(result: RankResult | null): Record<string, string> {
  const names: Record<string, string> = {}
  if (!result) return names
  if (result.requester?.facility_id) names[result.requester.facility_id] = result.requester.name
  for (const s of Object.values(result.sites ?? {})) names[s.facility_id] = s.name
  for (const o of result.ranking.options) names[o.facility_id] = o.name
  const b = result.ranking.baseline
  if (b?.facility_id && b.name) names[b.facility_id] = b.name
  return names
}

/** A round upper bound for arrival bars, so long waits (22 h) fit and every card shares one scale. */
export function barMax(...hours: number[]): number {
  const top = Math.max(0, ...hours.filter(Number.isFinite)) * 1.08
  return [4, 6, 8, 12, 16, 24, 36, 48, 72, 96].find(s => s >= top) ?? Math.ceil(top / 24) * 24
}

// ---------- Blood groups ----------

/** As people write them, with a true minus sign. The API takes ASCII "-". */
export const GROUPS = ['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−']

/** "A−", "A–" or "a-" -> "A-"; "Unknown" -> "unknown". */
export function toApiGroup(g: string): string {
  const s = g.trim().replace(/[−–]/g, '-')
  return s.toLowerCase() === 'unknown' ? 'unknown' : s.toUpperCase()
}

/** "A-" -> "A−"; "unknown" -> "Unknown". */
export function toDisplayGroup(g: string): string {
  const s = g.trim()
  return s.toLowerCase() === 'unknown' ? 'Unknown' : s.toUpperCase().replace(/[-–]/g, '−')
}

/** "O+ 21 · O− 1" (groups with spare units only). */
export function spareGroupsText(byGroup: Record<string, number>): string {
  return Object.entries(byGroup).filter(([, n]) => n > 0).map(([g, n]) => `${toDisplayGroup(g)} ${n}`).join(' · ')
}

// ---------- Stock date ----------

const DAY_MS = 86_400_000
const EAT_MS = 3 * 3600_000
const eatDay = (iso: string) => { const t = eatTime(iso); return t === null ? null : Math.floor((t + EAT_MS) / DAY_MS) }

/**
 * Whole days from the stock count (the ranking's as_of_stock_date) to the request's day (EAT).
 * 1 is yesterday's count, the usual case. More after the data ends (the engine then uses the last
 * count), 0 on the data's first day (its own closing count). NaN when a date cannot be read.
 */
export function stockAgeDays(requestedAt: string, asOfStockDate: string): number {
  const asked = eatDay(requestedAt)
  const counted = eatDay(asOfStockDate)
  return asked === null || counted === null ? Number.NaN : asked - counted
}

/**
 * "Count of 30 Oct 2026", plus how old the count is when it is not the day before the request:
 * "Count of 31 Oct 2026, 10 days before this request (the data ends there)".
 */
export function stockCountText(requestedAt: string, asOfStockDate: string): string {
  const day = `Count of ${fmtDay(asOfStockDate)}`
  const age = stockAgeDays(requestedAt, asOfStockDate)
  if (age > 1) return `${day}, ${age} days before this request (the data ends there)`
  if (age === 0) return `${day}, the day of this request (there is no earlier count)`
  if (age < 0) return `${day}, after this request (there is no earlier count)`
  return day
}

// ---------- Flags ----------

const plain = (s: string) => s.replace(/_/g, ' ')
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

const FLAG_LABELS: Record<string, string> = {
  partial: 'Covers part of the request',
  no_backup_power: 'No backup power for the blood fridge',
  low_connectivity_2g: '2G only: confirm by phone',
  group_unknown_emergency_O: 'Group O only (patient group unknown)',
  o_neg_reserve_applied: 'O− reserve kept back'
}
const FLAG_SHORT: Record<string, string> = {
  partial: 'Part only',
  no_backup_power: 'No backup power',
  low_connectivity_2g: '2G only',
  group_unknown_emergency_O: 'Group O only',
  o_neg_reserve_applied: 'O− reserve kept'
}

export function flagLabel(flag: string): string {
  return FLAG_LABELS[flag] ?? cap(plain(flag))
}

/** Compact label for cards. */
export function flagShort(flag: string): string {
  return FLAG_SHORT[flag] ?? cap(plain(flag))
}

// ---------- Request workflow ----------

/** Minutes the supplying site has to confirm the shelf (settings: arrival.confirmation_timeout_minutes). */
export const CONFIRM_TIMEOUT_MIN = 10

export const STATUS_LABELS: Record<RequestStatus, string> = {
  open: 'Open',
  awaiting_shelf: 'Waiting for shelf check',
  confirmed: 'Shelf confirmed',
  dispatched: 'Dispatched',
  arrived: 'Arrived',
  escalated: 'Escalated',
  cancelled: 'Cancelled'
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as RequestStatus] ?? cap(plain(status))
}

export function isFinalStatus(status: string): boolean {
  return status === 'arrived' || status === 'cancelled'
}

/** How far tracking has got: 0 sent, 1 shelf check, 2 shelf confirmed, 3 dispatched, 4 arrived. */
export function statusStage(status: string): number {
  return ({ awaiting_shelf: 1, confirmed: 2, dispatched: 3, arrived: 4 } as Record<string, number>)[status] ?? 0
}

const CLINICAL: RequestStatus[] = ['open', 'escalated', 'awaiting_shelf', 'confirmed', 'dispatched']
// The API's workflow rules. Used by the static demo and to show only possible steps; the server decides.
const MOVES: Record<RequestAction, { from: RequestStatus[]; to: RequestStatus | null }> = {
  pick: { from: ['open', 'escalated', 'awaiting_shelf'], to: 'awaiting_shelf' },
  shelf_confirmed: { from: ['awaiting_shelf'], to: 'confirmed' },
  dispatched: { from: ['confirmed'], to: 'dispatched' },
  arrived: { from: ['dispatched'], to: 'arrived' },
  not_on_shelf: { from: ['awaiting_shelf'], to: 'open' },
  confirm_timeout: { from: ['awaiting_shelf'], to: 'open' },
  emergency_group_o: { from: CLINICAL, to: null },
  transfer_patient: { from: CLINICAL, to: null },
  cancel: { from: ['open', 'escalated', 'awaiting_shelf', 'confirmed'], to: 'cancelled' }
}

/** Status after `action`, or null when the action is not allowed from `status`. */
export function statusAfter(status: RequestStatus, action: RequestAction): RequestStatus | null {
  const move = MOVES[action]
  if (!move || !move.from.includes(status)) return null
  // A clinical decision escalates an open request; later on it is only recorded.
  return move.to ?? (status === 'open' ? 'escalated' : status)
}

/** The supplying site's next step. The requesting hospital records it as the site reports it (there is no site screen yet). */
export function siteStep(status: RequestStatus): RequestAction | null {
  return status === 'awaiting_shelf' ? 'shelf_confirmed' : status === 'confirmed' ? 'dispatched' : status === 'dispatched' ? 'arrived' : null
}

const text = (v: unknown) => (typeof v === 'string' && v ? v : null)
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const unitsWord = (n: number) => `${n} ${n === 1 ? 'unit' : 'units'}`

/** What a person recorded when moving on from a site: it said the units are not there, or it did not answer. */
export type PassReason = 'not_on_shelf' | 'confirm_timeout'
export interface PassedSite { id: string; action: PassReason }

/**
 * Sites the audit trail says were not on the shelf (not_on_shelf) or did not answer in time
 * (confirm_timeout), oldest first. A later pick of the same site takes it off the list.
 */
export function passedOver(audit: AuditEntry[]): PassedSite[] {
  const out = new Map<string, PassReason>()
  for (const a of audit) {
    const d = a.detail ?? {}
    if (a.action === 'pick') {
      const id = text(d.facility_id)
      if (id) out.delete(id)
    } else if (a.action === 'not_on_shelf' || a.action === 'confirm_timeout') {
      const id = [d.previous_facility_id, d.facility_id, d.selected_facility_id].map(text).find(v => v !== null)
      if (id) {
        out.delete(id) // keep the order of the latest entry
        out.set(id, a.action)
      }
    }
  }
  return [...out].map(([id, action]) => ({ id, action }))
}

/**
 * One plain sentence per audit entry. `names` maps facility ids to names. `creatorOrg` is the
 * organisation that created the request (the first entry's actor): the requesting hospital, which
 * records the supplying site's steps by phone, as there is no supplying-site screen yet.
 */
export function auditSentence(entry: AuditEntry, names: Record<string, string> = {}, creatorOrg: string | null = null): string {
  const d = entry.detail ?? {}
  const site = (idKeys: string[], nameKeys: string[]) => {
    for (const k of nameKeys) { const v = text(d[k]); if (v) return v }
    for (const k of idKeys) { const v = text(d[k]); if (v) return names[v] ?? v }
    return 'the site'
  }
  const previous = () => site(['previous_facility_id', 'facility_id', 'selected_facility_id'], ['previous_name', 'facility_name', 'selected_name'])
  const byRequester = !!creatorOrg && entry.actor?.org_id === creatorOrg
  switch (entry.action) {
    case 'request_created': {
      const g = text(d.patient_group)
      const units = num(d.units_needed)
      const limit = num(d.limit_h)
      const parts = [
        g ? (g.toLowerCase() === 'unknown' ? 'group unknown, so group O only' : toDisplayGroup(g)) : null,
        units !== null ? unitsWord(units) : null,
        limit !== null ? `wait limit ${fmtHours(limit)}` : null
      ].filter(Boolean)
      let s = `Lab worker sent the request${parts.length ? `: ${parts.join(', ')}` : ''}.`
      if (Array.isArray(d.option_facility_ids)) {
        const n = d.option_facility_ids.length
        const asOf = text(d.as_of_stock_date)
        const asked = text(d.requested_at)
        const count = asOf ? (asked ? stockCountText(asked, asOf) : `Count of ${fmtDay(asOf)}`) : null
        s += ` The engine suggested ${n} ${n === 1 ? 'source' : 'sources'}${count ? ` from the stock ${count.charAt(0).toLowerCase()}${count.slice(1)}` : ''}.`
      }
      if (d.advice === 'consider_emergency_O_or_transfer') s += ' It warned the wait may be too long.'
      else if (d.advice === 'no_full_source') s += ' No single site had all the units.'
      return s
    }
    case 'pick': return `Lab worker picked ${site(['facility_id', 'selected_facility_id'], ['facility_name', 'selected_name', 'name'])}.`
    case 'shelf_confirmed': return byRequester
      ? 'Recorded by the requesting hospital: the supplying site confirmed the units are on the shelf.'
      : 'Supplying site confirmed the units are on the shelf.'
    case 'dispatched': return byRequester
      ? 'Recorded by the requesting hospital: the supplying site dispatched the units.'
      : 'Supplying site dispatched the units.'
    case 'arrived': return 'Units arrived. The lab checks every bag before use.'
    case 'not_on_shelf': return `${cap(previous())} said the units are not on the shelf. Back to the list of sources.`
    case 'confirm_timeout': {
      const waited = num(d.waited_minutes)
      return `No shelf confirmation from ${previous()} ${waited !== null ? `after ${Math.round(waited)} min` : `within ${CONFIRM_TIMEOUT_MIN} minutes`}. Back to the list of sources.`
    }
    case 'emergency_group_o': return 'Clinician chose emergency group O.'
    case 'transfer_patient': return 'Clinician chose to transfer the patient.'
    case 'cancel': return 'Request cancelled.'
    default: return `${cap(plain(entry.action))}.`
  }
}

/**
 * Requesting facility to preselect: the one saved on this device, else the one whose id matches
 * the organisation slug (for example "hsp-004"), else the one whose name is the organisation's
 * name (trimmed, any case), else null. Never a guess such as the first hospital: a ranking made
 * for the wrong place points people at the wrong sources, so the lab worker chooses.
 */
export function defaultFacilityId(hospitals: Facility[], stored: string | null, orgSlug: string | null, orgName: string | null = null): string | null {
  if (stored && hospitals.some(h => h.facility_id === stored)) return stored
  const slug = orgSlug?.trim().toLowerCase()
  const bySlug = slug ? hospitals.find(h => h.facility_id.toLowerCase() === slug) : undefined
  if (bySlug) return bySlug.facility_id
  const name = orgName?.trim().toLowerCase()
  const byName = name ? hospitals.find(h => (h.name ?? '').trim().toLowerCase() === name) : undefined
  return byName?.facility_id ?? null
}
