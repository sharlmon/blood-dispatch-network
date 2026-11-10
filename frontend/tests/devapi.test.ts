// Plain Node tests (npm test) for utils/devapi.ts, against responses recorded from the real backend
// (tests/fixtures/dev-api.json: made by running the Flask app on a small test dataset).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  apiTime, auditFromDev, bundleFromDev, createBody, eatNoOffset, eatStamp, facilityFromDev, prealertsFromDev, resultFromDev, statusFromDev, stepCall
} from '../app/utils/devapi.ts'
import type { DevRequest } from '../app/utils/devapi.ts'
import { auditSentence, passedOver, toApiGroup, toOptions } from '../app/utils/engine.ts'

const fx = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'dev-api.json'), 'utf8'))
const facilities = fx.facilities.items.map(facilityFromDev)

test('times become East Africa Time', () => {
  assert.equal(eatStamp('2026-03-09T22:00:00+00:00'), '2026-03-10T01:00:00+03:00')
  assert.equal(eatNoOffset('2026-03-09T22:00:00+00:00'), '2026-03-10T01:00:00')
  assert.equal(apiTime('2026-10-31T00:58'), '2026-10-31T00:58:00+03:00')
  assert.equal(apiTime('2026-10-31T00:58:00'), '2026-10-31T00:58:00+03:00')
  assert.equal(apiTime('2026-10-31T00:58:00+03:00'), '2026-10-31T00:58:00+03:00')
})

test('facilities: kind, type, position and backup power', () => {
  const h = facilities.find((f: { facility_id: string }) => f.facility_id === 'HSP-R')
  assert.ok(h.is_hospital && !h.is_centre)
  assert.equal(h.facility_type, 'district_hospital')
  assert.equal(h.county, 'Kisumu')
  assert.equal(h.lat, -0.1)
  assert.equal(h.has_backup_power, true)
  const c = facilities.find((f: { facility_id: string }) => f.facility_id === 'RBTC-A')
  assert.ok(c.is_centre && !c.is_hospital)
  assert.equal(c.facility_type, 'regional_blood_centre')
  assert.equal(c.lat, null)
  assert.ok(!facilityFromDev({ id: 'SAT-001', name: 'Satellite', kind: 'hospital' }).is_hospital, 'a satellite is not a requesting hospital')
})

test('statuses read the way the screens name them', () => {
  assert.equal(statusFromDev('pending'), 'open')
  assert.equal(statusFromDev('awaiting_confirmation'), 'awaiting_shelf')
  assert.equal(statusFromDev('confirmed'), 'confirmed')
  assert.equal(statusFromDev('dispatched'), 'dispatched')
  assert.equal(statusFromDev('received'), 'arrived')
  assert.equal(statusFromDev('cancelled'), 'cancelled')
})

test('a created request becomes a bundle: record, ranking with sites, audit', () => {
  const b = bundleFromDev(fx.created as DevRequest, fx.audit.items.slice(0, 1), facilities)
  assert.equal(b.request.status, 'open')
  assert.equal(b.request.facility_name, 'Hospital')
  assert.equal(b.request.patient_group, 'A+')
  assert.equal(b.request.units_needed, 3)
  assert.equal(b.request.limit_h, 6)
  assert.equal(b.request.requested_at, '2026-03-10T01:00:00')
  assert.equal(b.record.attempt, 0)
  assert.equal(b.result.ranking.request.requested_at, '2026-03-10T01:00:00')
  assert.equal(b.result.requester.name, 'Hospital')
  assert.equal(b.result.requester.lat, -0.1)
  assert.deepEqual(Object.keys(b.result.sites).sort(), ['RBTC-A', 'RBTC-B'])
  assert.equal(b.result.sites['RBTC-A']!.travel_hours_map, 2)
  const opts = toOptions(b.result)
  assert.equal(opts[0]!.id, 'RBTC-A')
  assert.equal(b.audit[0]!.action, 'request_created')
  assert.deepEqual(b.audit[0]!.detail.option_facility_ids, ['RBTC-A', 'RBTC-B'])
  assert.equal(b.audit[0]!.actor.org_id, 'org_demo')
})

test('a pick names the supplier and the attempt the next step must quote', () => {
  const b = bundleFromDev(fx.picked as DevRequest, fx.audit.items, facilities)
  assert.equal(b.request.status, 'awaiting_shelf')
  assert.equal(b.request.selected_facility_id, 'RBTC-A')
  assert.equal(b.request.selected_name, 'Centre A')
  assert.equal(b.record.attempt, 1)
  assert.equal(b.audit[1]!.action, 'pick')
  assert.equal(auditSentence(b.audit[1]!, { 'RBTC-A': 'Centre A' }), 'Lab worker picked Centre A.')
  assert.match(auditSentence(b.audit[0]!, {}), /^Lab worker sent the request: A\+, 3 units, wait limit 6h\. The engine suggested 2 sources/)
})

test('steps become the API calls, quoting the supplier, attempt and units', () => {
  const rec = { id: 'abc/1', selected_facility_id: 'RBTC-A', attempt: 2, units_needed: 3 }
  assert.deepEqual(stepCall('pick', rec, 'RBTC-B'), { path: '/api/requests/abc%2F1/pick', body: { supplier_id: 'RBTC-B' } })
  assert.deepEqual(stepCall('shelf_confirmed', rec, 'RBTC-A'), { path: '/api/requests/abc%2F1/confirm', body: { supplier_id: 'RBTC-A', attempt: 2, confirmed_units: 3 } })
  assert.deepEqual(stepCall('shelf_confirmed', rec), { path: '/api/requests/abc%2F1/confirm', body: { supplier_id: 'RBTC-A', attempt: 2, confirmed_units: 3 } })
  assert.deepEqual(stepCall('dispatched', rec), { path: '/api/requests/abc%2F1/dispatch', body: { supplier_id: 'RBTC-A', attempt: 2 } })
  assert.deepEqual(stepCall('arrived', rec), { path: '/api/requests/abc%2F1/receive', body: { received_units: 3 } })
  assert.equal(stepCall('not_on_shelf', rec)!.path, '/api/requests/abc%2F1/reject')
  assert.equal(stepCall('confirm_timeout', rec)!.path, '/api/requests/abc%2F1/reject')
  assert.equal(stepCall('cancel', rec)!.path, '/api/requests/abc%2F1/cancel')
  assert.equal(stepCall('emergency_group_o', rec), null, 'a clinician choice is not a server step')
  assert.equal(stepCall('transfer_patient', rec), null)
})

test('a rejected supplier is passed over, and the dead end is told plainly', () => {
  const b = bundleFromDev(fx.rejected as DevRequest, fx.audit_rejected.items, facilities)
  assert.equal(b.request.status, 'open')
  assert.equal(b.request.selected_facility_id, null)
  assert.deepEqual(passedOver(b.audit), [{ id: 'RBTC-A', action: 'not_on_shelf' }])
  const names = { 'RBTC-A': 'Centre A', 'RBTC-B': 'Centre B' }
  const says = (action: string) => auditSentence(b.audit.find(a => a.action === action)!, names)
  assert.equal(says('not_on_shelf'), 'Centre A said the units are not on the shelf. Back to the list of sources.')
  assert.match(says('supplier_skipped'), /^Centre B could not be reserved/)
  assert.match(says('sources_exhausted'), /phone process/)
})

test('a request that went all the way ends as arrived', () => {
  const b = bundleFromDev(fx.received as DevRequest, fx.audit_received.items, facilities)
  assert.equal(b.request.status, 'arrived')
  assert.deepEqual(b.audit.map(a => a.action), ['request_created', 'pick', 'shelf_confirmed', 'dispatched', 'arrived'])
  assert.equal(b.audit[2]!.detail.confirmed_units, 3)
})

test('a lapsed confirmation names the site that did not answer', () => {
  const items = [
    { id: 1, request_id: 'r', action: 'created', created_at: '2026-03-09T22:00:00+00:00', details: { actor: { user_id: 'u', org_id: 'o', org_role: null }, patient_group: 'A+', units_needed: 3, clinician_limit_h: 6, requested_at: '2026-03-09T22:00:00+00:00' } },
    { id: 2, request_id: 'r', action: 'pick', created_at: '2026-03-09T22:00:00+00:00', details: { supplier_id: 'RBTC-A' } },
    { id: 3, request_id: 'r', action: 'confirmation_expired', created_at: '2026-03-09T22:10:00+00:00', details: { attempt: 1 } }
  ]
  const trail = auditFromDev(items, fx.created as DevRequest, facilities)
  assert.deepEqual(passedOver(trail), [{ id: 'RBTC-A', action: 'confirm_timeout' }])
  assert.equal(auditSentence(trail[2]!, { 'RBTC-A': 'Centre A' }), 'No shelf confirmation from Centre A after 10 min. Back to the list of sources.')
})

test('a preview (POST /api/rank) becomes a result with sites on the map', () => {
  const r = resultFromDev(fx.rank.ranking, fx.rank.request.clinician_limit_h, 'HSP-R', facilities)
  assert.equal(r.clinician_limit_h, 6)
  assert.equal(r.requester.facility_id, 'HSP-R')
  assert.equal(toOptions(r).length, 2)
})

test('the request body uses the API field names and an offset time', () => {
  const input = { facilityId: 'HSP-R', group: 'A−', units: 2, limitH: 4, requestedAt: '2026-10-31T00:58' }
  assert.deepEqual(createBody(input, toApiGroup), {
    facility_id: 'HSP-R', patient_group: 'A-', units_needed: 2, component: 'RBC', clinician_limit_h: 4, requested_at: '2026-10-31T00:58:00+03:00'
  })
  assert.equal('requested_at' in createBody(input, toApiGroup, false), false)
})

test('the evening list carries facility names', () => {
  const run = { id: 'p', created_at: '2026-03-09T15:00:00+00:00', result: { generated_at: '2026-03-10T18:00:00+03:00', stock_as_of: '2026-03-09', alerts: [{ facility_id: 'RBTC-A', blood_group: 'O+' }], missing_snapshot: [{ facility_id: 'RBTC-B' }], assumptions: ['x'] } }
  const l = prealertsFromDev(run, facilities, 'API pre-alert run')
  assert.equal(l.alerts[0]!.facility_name, 'Centre A')
  assert.equal(l.missing_snapshot[0]!.facility_name, 'Centre B')
  assert.equal(l.stock_as_of, '2026-03-09')
})
