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
