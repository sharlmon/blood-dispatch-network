// Plain Node tests for the framework-free utils (npm test; Node 22.6 or newer, no extra packages).
// The workflow table, the record fields, the audit detail keys and the compatibility table are
// checked against the backend's own Python modules (backend/workflow/store.py and
// backend/engine/compat.py, standard library only), so a change on either side fails here.
// Those checks are skipped when no Python 3 is found.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  GROUPS, STATUS_LABELS, auditSentence, defaultFacilityId, isFinalStatus, mapSpots, passedOver, siteNames, siteStep,
  statusAfter, stockAgeDays, stockCountText, toApiGroup, toDisplayGroup, toOptions
} from '../app/utils/engine.ts'
import type { AuditEntry, EngineRanking, Facility, RankResult, RequestAction, RequestRecord, RequestStatus } from '../app/utils/engine.ts'
import { mockRankResult } from '../app/utils/mock.ts'
import { clockAfter, clockOn, requestClock, requestNeedsDate } from '../app/utils/format.ts'

const repo = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const backend = join(repo, 'backend')
const examples = join(backend, 'engine', 'examples')

// ---------- the backend's own answers ----------

// Reads the backend's compatibility table (backend/engine/compat.py, standard library only).
const PY = String.raw`
import json, sys
sys.path.insert(0, sys.argv[1])
from engine.compat import RED_CELL_COMPATIBILITY
print(json.dumps({"compat": {g: list(u) for g, u in RED_CELL_COMPATIBILITY.items()}}))
`

interface Backend {
  compat: Record<string, string[]>
}

function backendAnswers(): Backend | null {
  const pythons = [join(repo, '.venv', 'bin', 'python'), 'python3', 'python']
  for (const py of pythons) {
    if (py.includes('/') && !existsSync(py)) continue
    try {
      const out = execFileSync(py, ['-I', '-B', '-c', PY, backend], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 60_000 })
      return JSON.parse(out) as Backend
    } catch (e) {
      const err = e as { code?: string; stderr?: string }
      if (err.code === 'ENOENT') continue
      throw new Error(`The backend check script failed with ${py}:\n${err.stderr ?? String(e)}`)
    }
  }
  return null
}

const be = backendAnswers()
const needsPython = { skip: be ? false : 'no Python 3 found to read the backend modules' }

// ---------- blood groups ----------

test('groups convert between the screens and the API', () => {
  assert.equal(toApiGroup('A−'), 'A-')
  assert.equal(toApiGroup(' a– '), 'A-')
  assert.equal(toApiGroup('ab+'), 'AB+')
  assert.equal(toApiGroup('Unknown'), 'unknown')
  assert.equal(toApiGroup(' UNKNOWN '), 'unknown')
  assert.equal(toDisplayGroup('A-'), 'A−')
  assert.equal(toDisplayGroup('o-'), 'O−')
  assert.equal(toDisplayGroup('AB+'), 'AB+')
  assert.equal(toDisplayGroup('unknown'), 'Unknown')
  for (const g of GROUPS) assert.equal(toDisplayGroup(toApiGroup(g)), g)
})

test('every group the screens offer is in the backend compatibility table, and the demo data follows it', needsPython, () => {
  const table = be!.compat
  for (const g of [...GROUPS, 'Unknown']) assert.ok(toApiGroup(g) in table, `${g} is not in engine/compat.py`)
  assert.deepEqual(table.unknown!.slice().sort(), ['O+', 'O-'], 'unknown group means group O only')
  for (const [group, units] of Object.entries(table)) {
    const top = mockRankResult({ group, units: 1, limitH: 6 }).ranking.options[0]
    assert.ok(top, `the demo data has no source for ${group}`)
    assert.deepEqual(Object.keys(top.spare_by_group).sort(), units.slice().sort(), `demo compatibility for ${group}`)
  }
})

// ---------- local workflow (the static demo applies the same rules on screen) ----------

test('the local rules: a pick, the shelf check, dispatch and arrival, in that order', () => {
  assert.equal(statusAfter('open', 'pick'), 'awaiting_shelf')
  assert.equal(statusAfter('awaiting_shelf', 'shelf_confirmed'), 'confirmed')
  assert.equal(statusAfter('confirmed', 'dispatched'), 'dispatched')
  assert.equal(statusAfter('dispatched', 'arrived'), 'arrived')
  assert.equal(statusAfter('open', 'dispatched'), null, 'no dispatch before the shelf is confirmed')
  assert.equal(statusAfter('open', 'arrived'), null)
  assert.equal(statusAfter('dispatched', 'cancel'), null, 'no cancelling once dispatched')
  assert.equal(statusAfter('awaiting_shelf', 'not_on_shelf'), 'open')
  assert.equal(statusAfter('open', 'emergency_group_o'), 'escalated')
})

test('the site step is the next one a supplying site takes', () => {
  assert.equal(siteStep('open'), null)
  assert.equal(siteStep('awaiting_shelf'), 'shelf_confirmed')
  assert.equal(siteStep('confirmed'), 'dispatched')
  assert.equal(siteStep('dispatched'), 'arrived')
  assert.equal(siteStep('arrived'), null)
  assert.ok(isFinalStatus('arrived') && isFinalStatus('cancelled') && !isFinalStatus('dispatched'))
  assert.deepEqual(Object.keys(STATUS_LABELS).sort(), ['arrived', 'awaiting_shelf', 'cancelled', 'confirmed', 'dispatched', 'escalated', 'open'])
})

// ---------- requesting hospital ----------

const hospital = (facility_id: string, name: string): Facility => ({
  facility_id, name, facility_type: 'county_hospital', is_hospital: true, is_centre: false, is_satellite: false,
  county: null, lat: null, lon: null, supply_centre_id: null, connectivity: '4G', has_backup_power: true
})
// Sorted by name, as GET /api/facilities returns them: Busia comes first.
const HOSPITALS = [hospital('HSP-015', 'Busia County Referral Hospital'), hospital('HSP-004', 'Westlands Private Hospital')]

test('the requesting hospital is never guessed', () => {
  assert.equal(defaultFacilityId(HOSPITALS, null, null), null, 'no alphabetical fallback')
  assert.equal(defaultFacilityId(HOSPITALS, null, 'westlands-private-hospital'), null)
  assert.equal(defaultFacilityId(HOSPITALS, 'HSP-999', null, 'Your hospital'), null)
  assert.equal(defaultFacilityId([], 'HSP-004', 'hsp-004', 'Westlands Private Hospital'), null)
})

test('the requesting hospital: saved choice, else the organisation slug, else its exact name', () => {
  assert.equal(defaultFacilityId(HOSPITALS, 'HSP-004', 'hsp-015', 'Busia County Referral Hospital'), 'HSP-004')
  assert.equal(defaultFacilityId(HOSPITALS, 'HSP-999', ' HSP-004 ', null), 'HSP-004')
  assert.equal(defaultFacilityId(HOSPITALS, null, 'hsp-004', 'Busia County Referral Hospital'), 'HSP-004')
  assert.equal(defaultFacilityId(HOSPITALS, null, 'westlands', '  westlands private HOSPITAL '), 'HSP-004')
  assert.equal(defaultFacilityId(HOSPITALS, null, null, 'Westlands Private'), null, 'a partial name is not a match')
})

// ---------- stock date ----------

test('stock age is whole days from the count to the request day (EAT)', () => {
  assert.equal(stockAgeDays('2026-10-31T00:58:20', '2026-10-30'), 1)
  assert.equal(stockAgeDays('2026-11-10T22:41:07', '2026-10-31'), 10)
  assert.equal(stockAgeDays('2026-11-10T22:41:07+03:00', '2026-10-31'), 10)
  assert.equal(stockAgeDays('2026-11-10T20:30:00Z', '2026-10-31'), 10, '23:30 EAT')
  assert.equal(stockAgeDays('2026-11-10T21:30:00Z', '2026-10-31'), 11, 'already 11 Nov in EAT')
  assert.equal(stockAgeDays('2025-11-01T08:00:00', '2025-11-01'), 0, 'first day: its own closing count')
  assert.ok(Number.isNaN(stockAgeDays('not a time', '2026-10-31')))
})

test('the stock wording dates the count and says how old it is', () => {
  assert.equal(stockCountText('2026-10-31T00:58:20', '2026-10-30'), 'Count of 30 Oct 2026')
  assert.equal(stockCountText('2026-11-10T22:41:07', '2026-10-31'), 'Count of 31 Oct 2026, 10 days before this request (the data ends there)')
  assert.equal(stockCountText('2026-11-01T09:00:00', '2026-10-31'), 'Count of 31 Oct 2026')
  assert.equal(stockCountText('2025-11-01T08:00:00', '2025-11-01'), 'Count of 1 Nov 2025, the day of this request (there is no earlier count)')
})

// ---------- clocks ----------

test('request clocks carry their day when they are not when the request was logged, or not today', () => {
  const now = Date.parse('2026-11-10T19:45:00Z') // 22:45 EAT
  const logged = '2026-11-10T22:41:07+03:00'
  assert.equal(requestNeedsDate('2026-11-10T22:41:00', logged, now), false)
  assert.equal(requestClock('2026-11-10T22:41:00', logged, now), '22:41')
  assert.equal(requestNeedsDate('2026-10-31T00:58:00', logged, now), true, 'demo clock')
  assert.equal(requestClock('2026-10-31T00:58:00', logged, now), '31 Oct, 00:58')
  assert.equal(requestClock('2026-11-10T20:00:00', null, now), '10 Nov, 20:00', 'a preview counts from now')
  assert.equal(requestClock('2026-11-09T22:41:00', '2026-11-09T22:41:07+03:00', now), '9 Nov, 22:41', 'yesterday')
  assert.equal(clockAfter('2026-10-31T00:58:00', 2.6), '03:33')
  assert.equal(clockAfter('2026-10-31T00:58:00', 2.6, true), '31 Oct, 03:33')
  assert.equal(clockAfter('2026-10-31T22:58:00', 2.6), '01:33 next day')
  assert.equal(clockOn('2026-11-10T08:05:00', false, now), '08:05')
  assert.equal(clockOn('2026-11-03T08:05:00', false, now), '3 Nov, 08:05')
})

// ---------- adapter ----------

const exampleFiles = readdirSync(examples).filter(f => f.endsWith('.json')).sort()

test('the engine examples are found', () => {
  for (const f of ['baseline_mode.json', 'full_source.json', 'partial.json', 'too_long.json']) assert.ok(exampleFiles.includes(f), f)
})

for (const file of exampleFiles) {
  test(`adapter keeps the engine's numbers and words: ${file}`, () => {
    const ranking = JSON.parse(readFileSync(join(examples, file), 'utf8')) as EngineRanking
    const result: RankResult = {
      ranking,
      clinician_limit_h: 6,
      requester: { facility_id: ranking.request.facility_id, name: 'Requesting hospital', facility_type: 'county_hospital', county: null, lat: null, lon: null },
      sites: {}
    }
    const options = toOptions(result)
    assert.equal(options.length, ranking.options.length)
    options.forEach((o, i) => {
      const e = ranking.options[i]!
      assert.equal(o.id, e.facility_id)
      assert.equal(o.rank, e.rank)
      assert.equal(o.name, e.name)
      assert.equal(o.kind, e.is_hospital ? 'hospital' : 'centre')
      assert.deepEqual([o.p10, o.p50, o.p90, o.waitP50, o.roadP50], [e.eta.p10, e.eta.p50, e.eta.p90, e.eta.wait_p50, e.eta.road_p50])
      assert.ok(o.p10 <= o.p50 && o.p50 <= o.p90, 'every estimate has a range')
      assert.deepEqual([o.spare, o.stockSeen, o.nearExpiry], [e.spare, e.stock_seen, e.near_expiry])
      assert.deepEqual(o.spareByGroup, e.spare_by_group)
      assert.equal(Object.values(o.spareByGroup).reduce((a, b) => a + b, 0), o.spare, 'spare by group adds up to spare')
      assert.deepEqual(o.flags, e.flags)
      assert.equal(o.partial, e.flags.includes('partial'))
      assert.equal(o.reason, e.reason, 'reason verbatim')
      assert.equal(o.reasons.join(' '), e.reason, 'split into sentences without changing a word')
      assert.ok(Number.isFinite(o.x) && Number.isFinite(o.y))
    })
    const names = siteNames(result)
    for (const e of ranking.options) assert.equal(names[e.facility_id], e.name)
    if (ranking.baseline.facility_id) assert.equal(names[ranking.baseline.facility_id], ranking.baseline.name)
    assert.equal(stockAgeDays(ranking.request.requested_at, ranking.request.as_of_stock_date), 1)
  })
}

test('map positions keep north up and the true bearing', () => {
  const site = (facility_id: string, lat: number, lon: number) => ({ facility_id, name: facility_id, facility_type: 'regional_blood_centre', county: null, lat, lon, road_km: 50, travel_hours_map: 1 })
  const option = (facility_id: string, rank: number) => ({
    rank, facility_id, name: facility_id, facility_type: 'regional_blood_centre', is_hospital: false, spare: 4, stock_seen: 4, near_expiry: 0,
    has_backup_power: true, connectivity: '4G', travel_hours_map: 1, eta: { p10: 1, p50: 2, p90: 3, wait_p50: 1, road_p50: 1 }, flags: [], reason: '', spare_by_group: { 'O+': 4 }
  })
  const result = {
    ranking: { request: { facility_id: 'ME', patient_group: 'O+', units_needed: 1, requested_at: '2026-10-31T00:58:00', as_of_stock_date: '2026-10-30' }, options: ['N', 'E', 'S', 'W'].map((id, i) => option(id, i + 1)) },
    clinician_limit_h: 6,
    requester: { facility_id: 'ME', name: 'Me', facility_type: 'county_hospital', county: null, lat: 0, lon: 35 },
    sites: { N: site('N', 0.5, 35), E: site('E', 0, 35.5), S: site('S', -0.5, 35), W: site('W', 0, 34.5) }
  } as unknown as RankResult
  const at = mapSpots(result)
  assert.ok(at.N!.y < 150 && Math.abs(at.N!.x - 200) < 1, 'north is up')
  assert.ok(at.S!.y > 150 && Math.abs(at.S!.x - 200) < 1, 'south is down')
  assert.ok(at.E!.x > 200 && Math.abs(at.E!.y - 150) < 1, 'east is right')
  assert.ok(at.W!.x < 200 && Math.abs(at.W!.y - 150) < 1, 'west is left')
})

test('the demo data follows the engine rules for advice', () => {
  const ok = mockRankResult({ group: 'B+', units: 2, limitH: 6, requestedAt: '2026-10-31T00:58:00' }).ranking
  assert.equal(ok.advice, null)
  assert.equal(ok.request.as_of_stock_date, '2026-10-30')
  const late = mockRankResult({ group: 'B+', units: 2, limitH: 1, requestedAt: '2026-10-31T00:58:00' }).ranking
  assert.equal(late.advice, 'consider_emergency_O_or_transfer')
  const part = mockRankResult({ group: 'O−', units: 40, limitH: 72, requestedAt: '2026-10-31T00:58:00' }).ranking
  assert.equal(part.advice, 'no_full_source')
  assert.ok(part.options.length > 0 && part.options.every(o => o.flags.includes('partial')))
  const unknown = mockRankResult({ group: 'Unknown', units: 1, limitH: 6 }).ranking
  assert.ok(unknown.options.every(o => o.flags.includes('group_unknown_emergency_O') && Object.keys(o.spare_by_group).every(g => g.startsWith('O'))))
})
