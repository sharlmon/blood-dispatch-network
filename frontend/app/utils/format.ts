/** Hours as quarter-hour text: 1.5 -> "1½ h", 2.25 -> "2¼ h". */
export function fmtHours(h: number): string {
  const q = Math.round(h * 4) / 4
  const whole = Math.floor(q)
  const f = q - whole
  const frac = f === 0 ? '' : f === 0.25 ? '¼' : f === 0.5 ? '½' : '¾'
  return `${whole || ''}${frac} h`.trim()
}

export function fmtRange(p10: number, p90: number): string {
  return `${fmtHours(p10).replace(' h', '')} to ${fmtHours(p90)}`
}

export function nowClock(): string {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
