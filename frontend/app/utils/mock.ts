// Demo data for the static build (no API) and the landing-page illustration ONLY. The sites,
// stock and coordinates are fictional. It answers in the engine's JSON shape (RankResult) and
// follows the engine's rules (fixed compatibility table, safety stock, sort order, advice), so
// every screen runs through the same adapter as live data. Never used when an API is configured.
import type { EngineAdvice, EngineOption, RankResult, Requester, Site } from './engine.ts'
import { toApiGroup } from './engine.ts'
import { eatIso } from './format.ts'

// Spec section 5: patient group -> acceptable red cell unit groups. Unknown: group O only.
const COMPAT: Record<string, string[]> = {
  'O-': ['O-'],
  'O+': ['O+', 'O-'],
  'A-': ['A-', 'O-'],
  'A+': ['A+', 'A-', 'O+', 'O-'],
  'B-': ['B-', 'O-'],
  'B+': ['B+', 'B-', 'O+', 'O-'],
  'AB-': ['AB-', 'A-', 'B-', 'O-'],
  'AB+': ['AB+', 'AB-', 'A+', 'A-', 'B+', 'B-', 'O+', 'O-'],
  unknown: ['O-', 'O+']
}
const MIN_KEEP = 2
const O_NEG_RESERVE = 2
const WAIT_H = 0.9 // made-up dispatch wait for the demo network
const ROAD_RATIO = 1.15
const QUOTE_EXTRA_H = 2
const NEAR_EXPIRY_DAYS = 10
const COMPATIBILITY_NOTE = 'From a fixed table. A qualified person crossmatches and releases every unit.'
const STOCK_NOTE = "Yesterday's closing count. Unconfirmed until the supplying site confirms."
const BASELINE_RULE = 'Supply centre first, then the nearest regional centres. Quote = map time + 2 h.'
const UNKNOWN_NOTE = 'Emergency group O per hospital protocol. Lab confirms before release.'

export const DEMO_REQUESTER: Requester = {
  facility_id: 'DEMO-HILLSIDE', name: 'Hillside Hospital', facility_type: 'county_hospital', county: 'Demo county', lat: 0.3, lon: 35.8
}
const SUPPLY_CENTRE = 'DEMO-CENTRAL'

interface DemoSite {
  id: string
  name: string
  type: string
  county: string
  hospital: boolean
  /** km east and north of the requester */
  east: number
  north: number
  roadKm: number
  mapH: number
  backup: boolean
  connectivity: string
  stock: Record<string, number>
  usual?: Record<string, number>
  expiring?: Record<string, number>
}

const SITES: DemoSite[] = [
  {
    id: 'DEMO-LAKEVIEW', name: 'Lakeview District Hospital', type: 'district_hospital', county: 'Lakeview', hospital: true,
    east: 19, north: 16, roadKm: 31, mapH: 0.55, backup: true, connectivity: '4G',
    stock: { 'O+': 9, 'O-': 2, 'A+': 7, 'A-': 1, 'B+': 6, 'B-': 1, 'AB+': 2, 'AB-': 0 },
    usual: { 'O+': 6, 'O-': 2, 'A+': 5, 'A-': 1, 'B+': 3, 'B-': 1, 'AB+': 2, 'AB-': 0 },
    expiring: { 'B+': 1 }
  },
  {
    id: 'DEMO-HILLCREST', name: 'Hillcrest Hospital', type: 'county_hospital', county: 'Hillcrest', hospital: true,
    east: -42, north: 12, roadKm: 58, mapH: 1, backup: true, connectivity: '3G',
    stock: { 'O+': 8, 'O-': 2, 'A+': 4, 'A-': 1, 'B+': 3, 'B-': 0, 'AB+': 1, 'AB-': 0 },
    usual: { 'O+': 6, 'O-': 2, 'A+': 4, 'A-': 1, 'B+': 3, 'B-': 0, 'AB+': 1, 'AB-': 0 }
  },
  {
    id: 'DEMO-CENTRAL', name: 'Central Regional Blood Centre', type: 'regional_blood_centre', county: 'Central', hospital: false,
    east: 35, north: -62, roadKm: 96, mapH: 1.6, backup: true, connectivity: '4G',
    stock: { 'O+': 12, 'O-': 3, 'A+': 8, 'A-': 2, 'B+': 6, 'B-': 1, 'AB+': 3, 'AB-': 1 },
    expiring: { 'O+': 2 }
  },
  {
    id: 'DEMO-NORTHGATE', name: 'Northgate Hospital', type: 'county_referral', county: 'Northgate', hospital: true,
    east: -64, north: 96, roadKm: 142, mapH: 2.4, backup: false, connectivity: '2G',
    stock: { 'O+': 5, 'O-': 3, 'A+': 3, 'A-': 2, 'B+': 2, 'B-': 0, 'AB+': 1, 'AB-': 0 },
    usual: { 'O+': 4, 'O-': 1, 'A+': 3, 'A-': 1, 'B+': 2, 'B-': 0, 'AB+': 1, 'AB-': 0 }
  },
  {
    id: 'DEMO-EASTFIELD', name: 'Eastfield Regional Blood Centre', type: 'regional_blood_centre', county: 'Eastfield', hospital: false,
    east: 150, north: 30, roadKm: 188, mapH: 3.1, backup: true, connectivity: '4G',
    stock: { 'O+': 20, 'O-': 6, 'A+': 10, 'A-': 3, 'B+': 7, 'B-': 2, 'AB+': 2, 'AB-': 1 }
  }
]

const r1 = (v: number) => Math.round(v * 10) / 10
const r4 = (v: number) => Math.round(v * 1e4) / 1e4
const h = (v: number) => v.toFixed(1)
const unitsWord = (n: number) => (n === 1 ? 'unit' : 'units')

function site(s: DemoSite): Site {
  const lat0 = DEMO_REQUESTER.lat ?? 0
  const lon0 = DEMO_REQUESTER.lon ?? 0
  return {
    facility_id: s.id, name: s.name, facility_type: s.type, county: s.county,
    lat: r4(lat0 + s.north / 110.57), lon: r4(lon0 + s.east / (111.32 * Math.cos((lat0 * Math.PI) / 180))),
    road_km: s.roadKm, travel_hours_map: s.mapH
  }
}

// Spec section 6: a hospital keeps max(usual level, 2) per group and its O- reserve; a centre lends all.
function spareOf(s: DemoSite, g: string): number {
  const stock = s.stock[g] ?? 0
  if (!s.hospital) return stock
  const keep = Math.max(s.usual?.[g] ?? 0, MIN_KEEP, g === 'O-' ? O_NEG_RESERVE : 0)
  return Math.max(0, stock - keep)
}

function reasonFor(o: EngineOption, need: number, unknown: boolean): string {
  const parts = [o.is_hospital
    ? `Yesterday's count shows ${o.spare} spare compatible ${unitsWord(o.spare)} above its own safety stock (unconfirmed).`
    : `Regional centre: yesterday's count shows ${o.spare} compatible ${unitsWord(o.spare)} (unconfirmed).`]
  if (o.flags.includes('partial')) parts.push(`Can cover only ${o.spare} of the ${need} units needed.`)
  const timing = `${h(o.eta.wait_p50)} h to pack and dispatch, ${h(o.eta.road_p50)} h on the road. Most likely ${h(o.eta.p50)} h; 8 in 10 arrive within ${h(o.eta.p10)}-${h(o.eta.p90)} h.`
  parts.push(o.is_hospital ? `Hospital dispatch time is assumed from regional-centre data: about ${timing}` : `About ${timing}`)
  if (o.near_expiry) parts.push(`${o.near_expiry} ${unitsWord(o.near_expiry)} ${o.near_expiry === 1 ? 'expires' : 'expire'} within ${NEAR_EXPIRY_DAYS} days, so sharing them avoids waste.`)
  if (o.flags.includes('no_backup_power')) parts.push('Its blood fridge has no backup power.')
  if (o.flags.includes('low_connectivity_2g')) parts.push('It has 2G only, so confirmation may be slow.')
  if (o.is_hospital) parts.push('The lending hospital must agree before any unit moves.')
  if (unknown) parts.push(UNKNOWN_NOTE)
  return parts.join(' ')
}

export interface MockRankInput {
  /** patient group in either form ("A−" or "A-"), or "Unknown" */
  group: string
  units: number
  limitH: number
  /** EAT, no offset; defaults to now */
  requestedAt?: string
  requesterName?: string
}

/** Rank the fictional demo network for one request, in the API's RankResult shape. */
export function mockRankResult(input: MockRankInput): RankResult {
  const group = toApiGroup(input.group)
  const accept = COMPAT[group]
  if (!accept) throw new Error(`Patient group ${input.group} is not in the compatibility table.`)
  const need = Math.max(1, Math.round(input.units))
  const unknown = group === 'unknown'
  const requestedAt = input.requestedAt || eatIso().slice(0, 19)
  const asOf = new Date(Date.parse(`${requestedAt.slice(0, 10)}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10)

  const all = SITES.map((s) => {
    const byGroup = Object.fromEntries(accept.map(g => [g, spareOf(s, g)]))
    const spare = Object.values(byGroup).reduce((a, b) => a + b, 0)
    const road = Math.round(s.mapH * ROAD_RATIO * 100) / 100
    const p50 = WAIT_H + road
    const flags = [
      ...(s.backup ? [] : ['no_backup_power']),
      ...(s.connectivity === '2G' ? ['low_connectivity_2g'] : []),
      ...(unknown ? ['group_unknown_emergency_O'] : [])
    ]
    const option: EngineOption = {
      rank: 0, facility_id: s.id, name: s.name, facility_type: s.type, is_hospital: s.hospital,
      spare,
      stock_seen: accept.reduce((a, g) => a + (s.stock[g] ?? 0), 0),
      near_expiry: Math.min(spare, accept.reduce((a, g) => a + (s.expiring?.[g] ?? 0), 0)),
      has_backup_power: s.backup, connectivity: s.connectivity, travel_hours_map: s.mapH,
      eta: { p10: r1(p50 * 0.68), p50: r1(p50), p90: r1(p50 * 1.45), wait_p50: WAIT_H, road_p50: road },
      flags, reason: '', spare_by_group: byGroup
    }
    return { s, option }
  })

  // Spec section 8: quarter-hour p50, near-expiry first, backup power first, most spare.
  const order = (a: EngineOption, b: EngineOption) =>
    Math.round(a.eta.p50 * 4) / 4 - Math.round(b.eta.p50 * 4) / 4 || b.near_expiry - a.near_expiry
    || Number(b.has_backup_power) - Number(a.has_backup_power) || b.spare - a.spare || a.facility_id.localeCompare(b.facility_id)
  const full = all.filter(x => x.option.spare >= need).map(x => x.option).sort(order)
  const picked = (full.length ? full : all.filter(x => x.option.spare > 0).map(x => ({ ...x.option, flags: [...x.option.flags, 'partial'] })).sort(order)).slice(0, 5)
  const options = picked.map((o, i) => {
    const ranked = { ...o, rank: i + 1 }
    return { ...ranked, reason: reasonFor(ranked, need, unknown) }
  })

  const centres = all.filter(x => !x.s.hospital && x.option.spare >= need)
    .sort((a, b) => Number(b.s.id === SUPPLY_CENTRE) - Number(a.s.id === SUPPLY_CENTRE) || a.s.roadKm - b.s.roadKm)
  const base = centres[0]?.s
  const advice: EngineAdvice | null = options[0] && options[0].eta.p90 > input.limitH ? 'consider_emergency_O_or_transfer' : full.length ? null : 'no_full_source'

  const sites: Record<string, Site> = {}
  for (const s of SITES) if (options.some(o => o.facility_id === s.id) || s.id === base?.id) sites[s.id] = site(s)

  return {
    ranking: {
      request: { facility_id: DEMO_REQUESTER.facility_id, patient_group: group, units_needed: need, requested_at: requestedAt, as_of_stock_date: asOf },
      mode: 'model',
      model_used: true,
      sharing_allowed: true,
      compatibility_note: COMPATIBILITY_NOTE,
      stock_note: STOCK_NOTE,
      advice,
      options,
      baseline: base
        ? { facility_id: base.id, name: base.name, quote_hours: r1(base.mapH + QUOTE_EXTRA_H), rule: BASELINE_RULE }
        : { facility_id: null, name: null, quote_hours: null, rule: BASELINE_RULE }
    },
    clinician_limit_h: input.limitH,
    requester: { ...DEMO_REQUESTER, name: input.requesterName || DEMO_REQUESTER.name },
    sites
  }
}

export interface RecentRequest {
  group: string
  units: number
  where: string
  status: 'Dispatched' | 'Arrived' | 'Escalated'
  when: string
  urgent: boolean
}

/** Sample history for the request page in the static demo (fictional). */
export const RECENT: RecentRequest[] = [
  { group: 'B+', units: 2, where: 'Lakeview District Hospital', status: 'Dispatched', when: '18 min ago', urgent: true },
  { group: 'O+', units: 1, where: 'Central Regional Blood Centre', status: 'Arrived', when: 'Yesterday, 22:40', urgent: false },
  { group: 'A−', units: 2, where: 'Group O given, patient moved', status: 'Escalated', when: 'Mon, 03:10', urgent: true },
  { group: 'O−', units: 3, where: 'Hillcrest Hospital', status: 'Arrived', when: 'Sun, 19:25', urgent: false },
  { group: 'AB+', units: 1, where: 'Central Regional Blood Centre', status: 'Arrived', when: 'Sat, 08:05', urgent: false },
  { group: 'B−', units: 2, where: 'Lakeview District Hospital', status: 'Dispatched', when: 'Fri, 23:50', urgent: true }
]
