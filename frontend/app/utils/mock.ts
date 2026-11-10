// MOCK data and ranking. Replace with the Flask API (POST /api/requests) when the
// ranking engine lands. Shapes mirror what the engine is expected to return.
export type SourceKind = 'hospital' | 'centre'

export interface Option {
  id: string
  name: string
  kind: SourceKind
  spare: string
  km: number
  p10: number
  p50: number
  p90: number
  /** schematic map position, viewBox 400 x 300 */
  x: number
  y: number
  reasons: string[]
  kept: string
}

export interface DispatchRequest {
  id: string
  group: string
  units: number
  product: string
  limitH: number
  openedAt: string
}

export const GROUPS = ['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−']

const isRare = (g: string) => g.endsWith('−') || g.startsWith('AB')

export function mockRank(req: DispatchRequest): { options: Option[]; baseline: string } {
  const sub = req.group.endsWith('−') ? 'O−' : 'O+'
  let options: Option[]
  if (!isRare(req.group)) {
    options = [
      { id: 'lakeview', name: 'Lakeview District Hospital', kind: 'hospital', spare: `3 spare ${req.group}`, km: 31, p10: 1, p50: 1.5, p90: 2.2, x: 300, y: 70, kept: '3 of 6 spare. O− reserve untouched.',
        reasons: [`Has 3 spare ${req.group}, enough for your ${req.units} units.`, 'Fastest: most likely 1½ h, almost certainly 1 to 2¼ h.', 'Shares only what it can spare, so it stays above its minimum.'] },
      { id: 'hillcrest', name: 'Hillcrest Hospital', kind: 'hospital', spare: `2 spare ${sub}`, km: 58, p10: 1.8, p50: 2.3, p90: 3, x: 90, y: 112, kept: '2 of 5 spare. O− reserve untouched.',
        reasons: [`Has 2 spare ${sub}, which your patient can safely receive.`, 'Second fastest road time.', 'Shares only what it can spare.'] },
      { id: 'central', name: 'Central Regional Blood Centre', kind: 'centre', spare: '12 spare compatible', km: 96, p10: 2, p50: 2.5, p90: 3.5, x: 290, y: 238, kept: 'Centre: all compatible units available.',
        reasons: ['Largest stock, 12 compatible units.', 'Slowest of the three, but the range is tight.', 'Supply centre, no safety stock to protect.'] }
    ]
  } else {
    options = [
      { id: 'central', name: 'Central Regional Blood Centre', kind: 'centre', spare: `4 spare ${req.group}`, km: 188, p10: 3, p50: 3.5, p90: 5, x: 300, y: 70, kept: 'Centre: O− reserve kept.',
        reasons: [`Has 4 spare ${req.group}, enough for your ${req.units} units.`, 'Most likely 3½ h, almost certainly 3 to 5 h.', 'Wait may pass your limit.'] },
      { id: 'northgate', name: 'Northgate Hospital', kind: 'hospital', spare: `1 spare ${sub}`, km: 142, p10: 3.4, p50: 4.1, p90: 5, x: 90, y: 112, kept: '1 of 3 spare. O− reserve untouched.',
        reasons: [`Has 1 spare ${sub}, not enough alone for ${req.units} units.`, 'Slow road time.', 'Shares only what it can spare.'] }
    ]
  }
  return { options, baseline: 'Today\'s way: Central Blood Centre, about 4 h, no range.' }
}
