import type { ApiFailure } from './useApi'
import type { Facility } from '~/utils/engine'
import { defaultFacilityId } from '~/utils/engine'

const KEY = 'bdn-facility'
let inflight: Promise<Facility[]> | null = null

/** The requesting facility chosen on this device (only its id is kept). */
export function readSavedFacility(): string | null {
  try { return localStorage.getItem(KEY) } catch { return null }
}

export function saveFacility(id: string) {
  try { localStorage.setItem(KEY, id) } catch { /* private mode: the choice lasts until reload */ }
}

/** Facilities from the engine data (GET /api/facilities), loaded once on the client. */
export function useFacilities() {
  const { public: { authEnabled } } = useRuntimeConfig()
  const { api, fail, live } = useApi()
  const list = useState<Facility[] | null>('facilities.list', () => null)
  const state = useState<'idle' | 'loading' | 'ready' | 'error'>('facilities.state', () => 'idle')
  const error = useState<ApiFailure | null>('facilities.error', () => null)
  // A hospital's Clerk organisation slug may be its facility id (for example "hsp-004").
  const org = authEnabled ? useOrganization().organization : null
  // Or its name may be the hospital's name (Clerk organisation or demo account). "Your hospital" is
  // useSite's stand-in when there is none, so it never matches.
  const { hospital } = useSite()
  const accountHospital = () => (hospital.value && hospital.value !== 'Your hospital' ? hospital.value : null)

  const hospitals = computed(() => (list.value ?? []).filter(f => f.is_hospital))

  async function load(): Promise<Facility[]> {
    if (!live || import.meta.server) return []
    if (list.value) return list.value
    if (!inflight) {
      state.value = 'loading'
      error.value = null
      inflight = api<{ facilities: Facility[] }>('/api/facilities')
        .then((r) => { list.value = r.facilities; state.value = 'ready'; return r.facilities })
        .catch((e: unknown) => { state.value = 'error'; error.value = fail(e, { quiet: true }); return [] as Facility[] })
        .finally(() => { inflight = null })
    }
    return inflight
  }

  /**
   * Saved choice, else the hospital whose id is the organisation slug or whose name is the account's
   * hospital, else null: never a guess, the lab worker then chooses.
   */
  async function defaultId(): Promise<string | null> {
    await load()
    return defaultFacilityId(hospitals.value, readSavedFacility(), org?.value?.slug ?? null, accountHospital())
  }

  const name = (id: string | null | undefined) => (id ? list.value?.find(f => f.facility_id === id)?.name ?? null : null)

  return { list, state, error, hospitals, load, defaultId, name }
}
