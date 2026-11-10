import { mockRank, BASELINE_HOURS, type DispatchRequest, type Option } from '~/utils/mock'
import { nowClock } from '~/utils/format'

export interface AuditEntry { at: string; text: string }

export function useDispatch() {
  const request = useState<DispatchRequest | null>('dispatch.request', () => null)
  const options = useState<Option[]>('dispatch.options', () => [])
  const baseline = useState<string>('dispatch.baseline', () => '')
  const selectedId = useState<string | null>('dispatch.selected', () => null)
  const stage = useState<number>('dispatch.stage', () => 0) // 0 sent, 1 awaiting shelf, 2 dispatched, 3 arrived
  const audit = useState<AuditEntry[]>('dispatch.audit', () => [])

  const { toast } = useToast()
  const selected = computed(() => options.value.find(o => o.id === selectedId.value) ?? null)
  const top = computed(() => options.value[0] ?? null)
  const sooner = computed(() => (top.value ? BASELINE_HOURS - top.value.p50 : 0))
  const tooLong = computed(() => !!request.value && !!top.value && top.value.p90 > request.value.limitH)

  function log(text: string) {
    audit.value = [...audit.value, { at: nowClock(), text }]
  }

  /** Run the (mock) ranking and set state without navigating. */
  function load(input: Omit<DispatchRequest, 'id' | 'openedAt'>, pick?: string) {
    request.value = { ...input, id: `#${1042 + Math.floor(Math.random() * 50)}`, openedAt: nowClock() }
    const r = mockRank(request.value)
    options.value = r.options
    baseline.value = r.baseline
    selectedId.value = r.options.find(o => o.id === pick)?.id ?? r.options[0]?.id ?? null
    stage.value = 0
    audit.value = []
    log(`Request ${request.value.id}: ${input.group}, ${input.units} units, ${input.product}`)
  }

  function search(input: Omit<DispatchRequest, 'id' | 'openedAt'>) {
    load(input)
    return navigateTo('/results')
  }

  /** Rebuild state from a shareable link such as /results?group=B%2B&units=2&limit=3 */
  function loadFromQuery(q: Record<string, unknown>, pick?: string) {
    const group = String(q.group ?? '')
    if (!group) return false
    load({ group, units: Number(q.units) || 2, product: String(q.product ?? 'Red cells'), limitH: Number(q.limit) || 3 }, pick)
    return true
  }

  function select(id: string) {
    selectedId.value = id
  }

  function confirmSelection() {
    if (!selected.value) return
    stage.value = 1
    log(`Lab worker chose ${selected.value.name}. Waiting for shelf check.`)
    toast({ tone: 'ok', title: 'Request sent', body: `${selected.value.name} will confirm the shelf. A person approves every step.` })
    return navigateTo('/track')
  }

  function decide(kind: 'groupO' | 'transfer') {
    log(kind === 'groupO' ? 'Clinician chose emergency group O.' : 'Clinician chose to transfer the patient.')
    toast({ tone: 'warn', title: kind === 'groupO' ? 'Emergency group O recorded' : 'Transfer recorded', body: 'Saved in the audit log. Crossmatch every unit before use.' })
  }

  function advance() {
    if (stage.value >= 3) return
    stage.value += 1
    const texts = ['', 'Awaiting shelf check', 'Supplier confirmed the shelf and dispatched.', 'Units arrived. Lab worker checks every bag.']
    log(texts[stage.value] ?? '')
    toast({ tone: stage.value === 3 ? 'ok' : 'info', title: texts[stage.value] ?? '' })
  }

  return { request, options, baseline, selectedId, selected, top, sooner, tooLong, stage, audit, search, load, loadFromQuery, select, confirmSelection, decide, advance, log }
}
