// MOCK data and ranking. Replace with the Flask API (POST /api/requests) when the
// ranking engine lands. Shapes mirror what the engine is expected to return.
import { fmtHours, fmtRange } from './format'

export type SourceKind = 'hospital' | 'centre'

export interface Option {
  id: string
  name: string
  kind: SourceKind
  spare: string
  /** compatible units this site can spare */
  avail: number
  km: number
  p10: number
  p50: number
  p90: number
  /** schematic map position, viewBox 400 x 300 */
  x: number
  y: number
  reasons: string[]
  kept: string
  /** spare units shared out of total units on the shelf (hospitals only) */
  spareN?: number
  totalN?: number
}

export interface DispatchRequest {
  id: string
  group: string
  units: number
  product: string
  limitH: number
  openedAt: string
  /** the patient's group was unknown, so group O was requested per protocol */
  unknownGroup?: boolean
}

export const GROUPS = ['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−']
export const BASELINE_HOURS = 4 // the current way takes about 4 h with no range

const isRare = (g: string) => g.endsWith('−') || g.startsWith('AB')

type Raw = Omit<Option, 'reasons' | 'kept' | 'spare'> & { spareLabel: string }

function describe(o: Raw, i: number, req: DispatchRequest): Option {
  const enough = o.avail >= req.units
  const reasons = [
    enough ? `Has ${o.avail} spare ${o.spareLabel}, enough for your ${req.units} units.` : `Has ${o.avail} spare ${o.spareLabel}, not enough alone for ${req.units} units.`,
    `${i === 0 ? 'Fastest: most likely' : 'Most likely'} ${fmtHours(o.p50)}, almost certainly ${fmtRange(o.p10, o.p90)}.`,
    o.p90 > req.limitH ? 'The slow end may pass your limit.' : `Inside your ${req.limitH}h limit even at the slow end.`,
    o.kind === 'hospital' ? 'Shares only what it can spare, so it stays above its minimum.' : 'Supply centre, no safety stock to protect.'
  ]
  const { spareLabel, ...rest } = o
  return {
    ...rest,
    spare: `${o.avail} spare ${spareLabel}`,
    reasons,
    kept: o.kind === 'hospital' ? `${o.spareN} of ${o.totalN} spare. O− reserve untouched.` : 'Centre: all compatible units available. O− reserve kept.'
  }
}

export function mockRank(req: DispatchRequest): { options: Option[]; baseline: string } {
  const g = req.group
  const sub = g.endsWith('−') ? 'O−' : 'O+'
  const raw: Raw[] = !isRare(g)
    ? [
        { id: 'lakeview', name: 'Lakeview District Hospital', kind: 'hospital', spareLabel: g, avail: 3, km: 31, p10: 1, p50: 1.5, p90: 2.2, x: 300, y: 70, spareN: 3, totalN: 6 },
        { id: 'hillcrest', name: 'Hillcrest Hospital', kind: 'hospital', spareLabel: sub, avail: 2, km: 58, p10: 1.8, p50: 2.3, p90: 3, x: 90, y: 112, spareN: 2, totalN: 5 },
        { id: 'central', name: 'Central Regional Blood Centre', kind: 'centre', spareLabel: 'compatible', avail: 12, km: 96, p10: 2, p50: 2.5, p90: 3.5, x: 290, y: 238 }
      ]
    : [
        { id: 'central', name: 'Central Regional Blood Centre', kind: 'centre', spareLabel: g, avail: 4, km: 188, p10: 3, p50: 3.5, p90: 5, x: 300, y: 70 },
        { id: 'northgate', name: 'Northgate Hospital', kind: 'hospital', spareLabel: sub, avail: 1, km: 142, p10: 3.4, p50: 4.1, p90: 5, x: 90, y: 112, spareN: 1, totalN: 3 }
      ]
  return { options: raw.map((o, i) => describe(o, i, req)), baseline: 'Today\'s way: Central Blood Centre, about 4 h, no range.' }
}

export interface RecentRequest {
  group: string
  units: number
  where: string
  status: 'Dispatched' | 'Arrived' | 'Escalated'
  when: string
  urgent: boolean
}

/** Sample history for the request page (mock). */
export const RECENT: RecentRequest[] = [
  { group: 'B+', units: 2, where: 'Lakeview District Hospital', status: 'Dispatched', when: '18 min ago', urgent: true },
  { group: 'O+', units: 1, where: 'Central Regional Blood Centre', status: 'Arrived', when: 'Yesterday, 22:40', urgent: false },
  { group: 'A−', units: 2, where: 'Group O given, patient moved', status: 'Escalated', when: 'Mon, 03:10', urgent: true },
  { group: 'O−', units: 3, where: 'Hillcrest Hospital', status: 'Arrived', when: 'Sun, 19:25', urgent: false },
  { group: 'AB+', units: 1, where: 'Central Regional Blood Centre', status: 'Arrived', when: 'Sat, 08:05', urgent: false },
  { group: 'B−', units: 2, where: 'Lakeview District Hospital', status: 'Dispatched', when: 'Fri, 23:50', urgent: true }
]
