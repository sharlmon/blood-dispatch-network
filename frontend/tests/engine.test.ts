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

// Runs every action from every status through workflow.store.Store (a temporary SQLite file), and
// records one trail with each kind of step, so the frontend reads the real audit detail keys.
const PY = String.raw`
import json, os, sys, tempfile
sys.path.insert(0, sys.argv[1])
from workflow.store import RECORD_FIELDS, SITE_STEPS, STATUSES, TRANSITIONS, InvalidTransition, Store
from engine.compat import RED_CELL_COMPATIBILITY

ACTOR = {"user_id": "user_lab", "org_id": "org_requester", "org_role": "org:member"}
RESULT = {
    "ranking": {
        "request": {"facility_id": "HSP-R", "patient_group": "O+", "units_needed": 2,
                    "requested_at": "2026-11-10T22:41:00", "as_of_stock_date": "2026-10-31"},
        "mode": "model", "model_used": True, "advice": None,
        "options": [{"facility_id": "HSP-B", "name": "Lending Hospital", "rank": 1},
                    {"facility_id": "RBTC-A", "name": "Centre A", "rank": 2}],
        "baseline": {"facility_id": "RBTC-Z", "name": "Centre Z", "quote_hours": 9.0, "rule": "today"},
    },
    "clinician_limit_h": 6,
    "requester": {"facility_id": "HSP-R", "name": "Requesting Hospital"},
    "sites": {"HSP-B": {"facility_id": "HSP-B", "name": "Lending Hospital"},
              "RBTC-A": {"facility_id": "RBTC-A", "name": "Centre A"},
              "RBTC-Z": {"facility_id": "RBTC-Z", "name": "Centre Z"}},
}
# How to bring a new request to each status.
REACH = {
    "open": [],
    "awaiting_shelf": [("pick", "HSP-B")],
    "confirmed": [("pick", "HSP-B"), ("shelf_confirmed", None)],
    "dispatched": [("pick", "HSP-B"), ("shelf_confirmed", None), ("dispatched", None)],
    "arrived": [("pick", "HSP-B"), ("shelf_confirmed", None), ("dispatched", None), ("arrived", None)],
    "escalated": [("emergency_group_o", None)],
    "cancelled": [("cancel", None)],
}
out = {"statuses": list(STATUSES), "record_fields": list(RECORD_FIELDS), "site_steps": sorted(SITE_STEPS),
       "unreached": sorted(set(STATUSES) - set(REACH)), "result": RESULT,
       "compat": {g: list(u) for g, u in RED_CELL_COMPATIBILITY.items()}, "after": {}}
with tempfile.TemporaryDirectory() as tmp:
    store = Store(os.path.join(tmp, "workflow.db"))
    for action in TRANSITIONS:
        for status in STATUSES:
            if status not in REACH:
                continue
            rid = store.create_request(RESULT, component="RBC", actor=ACTOR)[0]["id"]
            for a, f in REACH[status]:
                store.record_event(rid, a, f, actor=ACTOR)
            try:
                rec, _ = store.record_event(rid, action, "RBTC-A" if action == "pick" else None, actor=ACTOR)
                out["after"].setdefault(action, {})[status] = rec["status"]
            except InvalidTransition:
                out["after"].setdefault(action, {})[status] = None
    rid = store.create_request(RESULT, component="RBC", actor=ACTOR)[0]["id"]
    trails = []
    for action, site in [("pick", "HSP-B"), ("not_on_shelf", "HSP-B"), ("pick", "RBTC-A"), ("confirm_timeout", "RBTC-A"),
                         ("pick", "HSP-B"), ("shelf_confirmed", "HSP-B"), ("dispatched", "HSP-B"), ("arrived", "HSP-B")]:
        record, trail = store.record_event(rid, action, site, actor=ACTOR)
        trails.append(trail)
    out["record"], out["trails"] = record, trails
    rid = store.create_request(RESULT, component="RBC", actor=ACTOR)[0]["id"]
    out["baseline_pick"] = store.record_event(rid, "pick", "RBTC-Z", actor=ACTOR)[1]
print(json.dumps(out))
`

interface Backend {
  statuses: string[]
  record_fields: string[]
  site_steps: string[]
  unreached: string[]
  result: RankResult
  compat: Record<string, string[]>
  after: Record<string, Record<string, string | null>>
  record: RequestRecord
  trails: AuditEntry[][]
  baseline_pick: AuditEntry[]
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

// ---------- workflow mirror ----------

test('the workflow rules match backend/workflow/store.py for every action from every status', needsPython, () => {
  assert.deepEqual(be!.unreached, [], 'a new status: teach this test (and the frontend) how to reach it')
  assert.deepEqual(Object.keys(STATUS_LABELS).sort(), be!.statuses.slice().sort())
  const actions = Object.keys(be!.after).sort()
  assert.deepEqual(actions, ['arrived', 'cancel', 'confirm_timeout', 'dispatched', 'emergency_group_o', 'not_on_shelf', 'pick', 'shelf_confirmed', 'transfer_patient'])
  for (const action of actions) {
    for (const status of be!.statuses) {
      const server = be!.after[action]![status] ?? null
      assert.equal(statusAfter(status as RequestStatus, action as RequestAction), server, `${action} from ${status}`)
    }
  }
})

test('the site step is the one the backend allows next, and it names the selected site', needsPython, () => {
  for (const status of be!.statuses) {
    const step = siteStep(status as RequestStatus)
    const allowed = ['shelf_confirmed', 'dispatched', 'arrived'].filter(a => be!.after[a]![status] !== null)
    assert.deepEqual(step ? [step] : [], allowed, status)
    if (step) assert.ok(be!.site_steps.includes(step), `${step} must be a site step (it sends facility_id)`)
  }
  assert.ok(be!.site_steps.includes('not_on_shelf') && be!.site_steps.includes('confirm_timeout'))
  assert.ok(isFinalStatus('arrived') && isFinalStatus('cancelled') && !isFinalStatus('dispatched'))
})

test('the request record has the backend fields', needsPython, () => {
  const fixture: RequestRecord = {
    id: '', created_at: '', facility_id: '', facility_name: null, patient_group: '', units_needed: 0, component: '',
    limit_h: 0, requested_at: '', status: 'open', selected_facility_id: null, selected_name: null
  }
  assert.deepEqual(Object.keys(fixture).sort(), be!.record_fields.slice().sort())
  assert.deepEqual(Object.keys(be!.record).sort(), be!.record_fields.slice().sort())
})

// ---------- audit trail ----------

test('passed-over sites come from the real audit detail keys, and a later pick clears a site', needsPython, () => {
  const t = be!.trails
  for (const entry of t[t.length - 1]!) {
    if (entry.action === 'not_on_shelf' || entry.action === 'confirm_timeout') {
      assert.ok('previous_facility_id' in entry.detail && 'waited_minutes' in entry.detail, entry.action)
    }
    if (entry.action === 'pick') assert.ok('facility_id' in entry.detail && 'facility_name' in entry.detail)
  }
  assert.deepEqual(passedOver(t[1]!), [{ id: 'HSP-B', action: 'not_on_shelf' }])
  assert.deepEqual(passedOver(t[3]!), [{ id: 'HSP-B', action: 'not_on_shelf' }, { id: 'RBTC-A', action: 'confirm_timeout' }])
  assert.deepEqual(passedOver(t[4]!), [{ id: 'RBTC-A', action: 'confirm_timeout' }], 'HSP-B was picked again')
  assert.deepEqual(passedOver(t[t.length - 1]!), [{ id: 'RBTC-A', action: 'confirm_timeout' }])
  assert.deepEqual(passedOver(be!.baseline_pick), [])
})

test('audit sentences read the backend detail, date the stock count and say who recorded site steps', needsPython, () => {
  const trail = be!.trails[be!.trails.length - 1]!
  const names = siteNames(be!.result)
  const creator = trail[0]!.actor.org_id
  const says = (action: string, org: string | null = creator) => auditSentence(trail.find(a => a.action === action)!, names, org)
  assert.equal(says('request_created'),
    'Lab worker sent the request: O+, 2 units, wait limit 6h. The engine suggested 2 sources from the stock count of 31 Oct 2026, 10 days before this request (the data ends there).')
  assert.equal(says('pick'), 'Lab worker picked Lending Hospital.')
  assert.equal(says('not_on_shelf'), 'Lending Hospital said the units are not on the shelf. Back to the list of sources.')
  assert.match(says('confirm_timeout'), /^No shelf confirmation from Centre A after \d+ min\. Back to the list of sources\.$/)
  assert.equal(says('shelf_confirmed'), 'Recorded by the requesting hospital: the supplying site confirmed the units are on the shelf.')
  assert.equal(says('dispatched'), 'Recorded by the requesting hospital: the supplying site dispatched the units.')
  assert.equal(says('shelf_confirmed', null), 'Supplying site confirmed the units are on the shelf.')
  assert.equal(auditSentence(be!.baseline_pick[be!.baseline_pick.length - 1]!, names, creator), 'Lab worker picked Centre Z.')
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
