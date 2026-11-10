/** Round hours to the nearest 5 minutes and return whole minutes. */
function toMinutes(h: number): number {
  return Math.max(0, Math.round((h * 60) / 5) * 5)
}

/** 1.5 -> [{n:'1',u:'h'},{n:'30',u:'m'}], 0.75 -> [{n:'45',u:'m'}], 2 -> [{n:'2',u:'h'}] */
export function fmtParts(h: number): { n: string; u: 'h' | 'm' }[] {
  const t = toMinutes(h)
  const hh = Math.floor(t / 60)
  const mm = t % 60
  const parts: { n: string; u: 'h' | 'm' }[] = []
  if (hh) parts.push({ n: String(hh), u: 'h' })
  if (mm || !hh) parts.push({ n: String(mm), u: 'm' })
  return parts
}

/** "1h 30m", "2h", "45m" */
export function fmtHours(h: number): string {
  return fmtParts(h).map(p => p.n + p.u).join(' ')
}

/** "1h to 2h 15m" */
export function fmtRange(p10: number, p90: number): string {
  return `${fmtHours(p10)} to ${fmtHours(p90)}`
}

/** Clock time (HH:MM) that is `hours` after `from` (HH:MM). */
export function etaClock(from: string, hours: number): string {
  const [hh, mm] = from.split(':').map(Number)
  const total = ((hh ?? 0) * 60 + (mm ?? 0) + toMinutes(hours)) % (24 * 60)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

export function nowClock(): string {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** "31 km" */
export function fmtKm(km: number): string {
  return `${Math.round(km)} km`
}

// ---------- East Africa Time (UTC+3 all year, no daylight saving) ----------

const EAT_MS = 3 * 3600_000
const DAY_MS = 86_400_000
const HAS_OFFSET = /(?:[zZ]|[+-]\d{2}:?\d{2})$/
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const pad = (n: number) => String(n).padStart(2, '0')

/** The EAT wall clock of an ISO time, held in a Date read with getUTC*. Times without an offset are already EAT. */
function eatWall(iso: string): Date | null {
  if (!iso) return null
  const t = HAS_OFFSET.test(iso) ? Date.parse(iso) + EAT_MS : Date.parse(iso.length === 10 ? `${iso}T00:00:00Z` : `${iso}Z`)
  return Number.isNaN(t) ? null : new Date(t)
}

const hhmm = (d: Date) => `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
const dayStart = (d: Date) => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
const dayClock = (d: Date) => `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${hhmm(d)}`

/** "00:58" (EAT) */
export function eatClock(iso: string): string {
  const d = eatWall(iso)
  return d ? hhmm(d) : ''
}

/** "30 Oct 2026" from "2026-10-30" or any ISO time (EAT). */
export function fmtDay(iso: string): string {
  const d = eatWall(iso)
  return d ? `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` : iso
}

/**
 * Clock time `hours` after the ISO time `from` (EAT), to 5 minutes; says so when it is a later day.
 * `dated` gives the day as well ("31 Oct, 03:35"), for a request that is not from today.
 */
export function clockAfter(from: string, hours: number, dated = false): string {
  const d = eatWall(from)
  if (!d) return ''
  const t = new Date(d.getTime() + toMinutes(hours) * 60_000)
  if (dated) return dayClock(t)
  const days = Math.round((dayStart(t) - dayStart(d)) / DAY_MS)
  return days === 0 ? hhmm(t) : days === 1 ? `${hhmm(t)} next day` : `${hhmm(t)} (+${days} days)`
}

const isToday = (d: Date, now: number) => dayStart(d) === dayStart(new Date(now + EAT_MS))

/** "22:41" when the ISO time is today (EAT), else "31 Oct, 00:58"; always dated when `dated`. */
export function clockOn(iso: string, dated = false, now: number = Date.now()): string {
  const d = eatWall(iso)
  if (!d) return ''
  return dated || !isToday(d, now) ? dayClock(d) : hhmm(d)
}

const LOGGED_SLACK_MS = 15 * 60_000

/**
 * True when clocks counted from a request need their day: the request time is more than 15
 * minutes from when the request was logged (`logged`, else now for a preview), as with the API's
 * demo clock or a back-dated link, or it is not today (EAT).
 */
export function requestNeedsDate(requestedAt: string, logged: string | null = null, now: number = Date.now()): boolean {
  const d = eatWall(requestedAt)
  if (!d) return false
  const ref = (logged ? eatTime(logged) : null) ?? now
  return Math.abs(d.getTime() - EAT_MS - ref) > LOGGED_SLACK_MS || !isToday(d, now)
}

/** The request's clock: "00:58", or "31 Oct, 00:58" when it needs its day (see requestNeedsDate). */
export function requestClock(requestedAt: string, logged: string | null = null, now: number = Date.now()): string {
  return clockOn(requestedAt, requestNeedsDate(requestedAt, logged, now), now)
}

/** "Just now", "18 min ago", "Today, 22:40", "Yesterday, 22:40", "Mon, 03:10", "3 Nov, 08:05" (EAT). */
export function fmtWhen(iso: string, now: number = Date.now()): string {
  const d = eatWall(iso)
  if (!d) return ''
  const mins = Math.round((now + EAT_MS - d.getTime()) / 60_000)
  if (Math.abs(mins) < 1) return 'Just now'
  if (mins > 0 && mins < 60) return `${mins} min ago`
  const days = Math.round((dayStart(new Date(now + EAT_MS)) - dayStart(d)) / DAY_MS)
  if (days === 0) return `Today, ${hhmm(d)}`
  if (days === 1) return `Yesterday, ${hhmm(d)}`
  if (days > 1 && days < 7) return `${DAYS[d.getUTCDay()]}, ${hhmm(d)}`
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${hhmm(d)}`
}

/** Milliseconds since the epoch for an ISO time (no offset = EAT). */
export function eatTime(iso: string): number | null {
  const d = eatWall(iso)
  return d ? d.getTime() - EAT_MS : null
}

/** Now (or `at`) as an ISO time with the +03:00 offset. */
export function eatIso(at: number = Date.now()): string {
  const d = new Date(at + EAT_MS)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${hhmm(d)}:${pad(d.getUTCSeconds())}+03:00`
}
