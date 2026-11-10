import type { Facility, RankResult, RequestAction, RequestBundle, RequestRecord } from '~/utils/engine'
import { toApiGroup } from '~/utils/engine'
import type { DevAuditItem, DevPrealertRun, DevRanking, DevRequest, RecordWithExtras } from '~/utils/devapi'
import { bundleFromDev, createBody, prealertsFromDev, recordFromDev, resultFromDev, stepCall } from '~/utils/devapi'
import { apiFailure } from './useApi'

interface Page<T> { items: T[]; limit: number; offset: number }
type Input = { facilityId: string; group: string; units: number; limitH: number; requestedAt?: string }

/** A request with the extra fields the next step needs (the server's attempt number). */
export type Bundle = RequestBundle & { record: RecordWithExtras }

/**
 * The backend API (backend/docs/api.md) as the screens use it: ranked requests, workflow steps and the
 * evening list, converted to the shapes in utils/engine.ts. Live mode only.
 */
export function useBackend() {
  const { api } = useApi()
  const facilities = useFacilities()

  /** Every facility, read page by page (the API pages at 200). */
  async function allFacilities(): Promise<Facility[]> {
    return facilities.load()
  }

  /** A time the API refuses as "too far from the clock" is sent again without it (it uses its own clock). */
  async function withTime<T>(run: (withTime: boolean) => Promise<T>, wanted: boolean): Promise<T> {
    try {
      return await run(wanted)
    } catch (e) {
      const f = apiFailure(e)
      if (wanted && f.status === 400 && /requested_at/.test(f.message)) return run(false)
      throw e
    }
  }

  async function rank(input: Input): Promise<RankResult> {
    const facs = await allFacilities()
    const res = await withTime(w => api<{ request: { clinician_limit_h: number }; ranking: DevRanking }>('/api/rank', { method: 'POST', body: createBody(input, toApiGroup, w) }), !!input.requestedAt)
    return resultFromDev(res.ranking, res.request.clinician_limit_h, input.facilityId, facs)
  }

  async function auditOf(id: string): Promise<DevAuditItem[]> {
    const rows: DevAuditItem[] = []
    for (let offset = 0; offset < 2000; offset += 200) {
      const page = await api<Page<DevAuditItem>>(`/api/audit?request_id=${encodeURIComponent(id)}&limit=200&offset=${offset}`)
      rows.push(...page.items)
      if (page.items.length < 200) break
    }
    return rows
  }

  async function bundle(detail: DevRequest): Promise<Bundle> {
    const [facs, audit] = await Promise.all([allFacilities(), auditOf(detail.id)])
    return bundleFromDev(detail, audit, facs)
  }

  async function create(input: Input): Promise<Bundle> {
    const detail = await withTime(w => api<DevRequest>('/api/requests', { method: 'POST', body: createBody(input, toApiGroup, w) }), !!input.requestedAt)
    return bundle(detail)
  }

  async function get(id: string): Promise<Bundle> {
    return bundle(await api<DevRequest>(`/api/requests/${encodeURIComponent(id)}`))
  }

  /**
   * Record one step. Null when the server has no such step (a clinician's choice stays on screen).
   * The server checks the status, the supplier and the attempt, and answers 409 when they are stale.
   */
  async function step(rec: RecordWithExtras, action: RequestAction, facilityId?: string | null): Promise<Bundle | null> {
    const call = stepCall(action, rec, facilityId)
    if (!call) return null
    const detail = await api<DevRequest>(call.path, { method: 'POST', body: call.body })
    return bundle(detail)
  }

  /** The newest requests the caller may see (their own hospital's, or any for a network operator). */
  async function recent(limit = 6): Promise<RequestRecord[]> {
    const [page, facs] = await Promise.all([api<Page<DevRequest>>(`/api/requests?limit=${limit}`), allFacilities()])
    return page.items.map(r => recordFromDev(r, facs))
  }

  /** The newest saved pre-alert run (operators only; others get 403 and the page says so). */
  async function prealerts() {
    const list = await api<Page<{ id: string; created_at: string }>>('/api/prealerts/runs?limit=1')
    const latest = list.items[0]
    if (!latest) throw Object.assign(new Error('none'), { status: 404, data: { error: { code: 'not_found', message: 'No evening list has been generated yet.' } } })
    const [run, facs] = await Promise.all([api<DevPrealertRun>(`/api/prealerts/runs/${encodeURIComponent(latest.id)}`), allFacilities()])
    return prealertsFromDev(run, facs, 'API pre-alert run')
  }

  return { recent, rank, create, get, step, prealerts }
}
