// Every 30 seconds the logo re-forms: the shared tick makes each BrandMark replay its animation,
// and the tab icon plays the same drops-gathering animation frame by frame.
const PERIOD = 30_000
const FRAMES = 20
const FRAME_MS = 75

export default defineNuxtPlugin(() => {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const tick = useState('logo-tick', () => 0)

  const DROP = new Path2D('M32 5 C40 16 50 27 50 39 A18 18 0 0 1 14 39 C14 27 24 16 32 5 Z')
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 64
  const ctx = canvas.getContext('2d')
  const link = () => document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  const ease = (t: number) => 1 - Math.pow(1 - t, 3)

  function draw(t: number) {
    if (!ctx) return
    ctx.clearRect(0, 0, 64, 64)
    ctx.fillStyle = '#fff'
    ctx.beginPath(); ctx.roundRect(0, 0, 64, 64, 14); ctx.fill()
    const dirs = [[0, -1], [1, 0], [0, 1], [-1, 0]]
    ;[0, 90, 180, 270].forEach((a, i) => {
      const k = Math.min(1, Math.max(0, (t * 1.25) - i * 0.07))
      const e = ease(k)
      const out = (1 - e) * 34
      const s = 0.35 + 0.65 * e
      ctx.save()
      ctx.globalAlpha = Math.min(1, k * 3)
      ctx.translate(32 + dirs[i]![0]! * out, 32 + dirs[i]![1]! * out)
      ctx.scale(s, s)
      ctx.rotate(((1 - e) * 50 * Math.PI) / 180)
      ctx.translate(-32, -32)
      ctx.translate(4, 4); ctx.scale(0.875, 0.875)
      ctx.translate(32, 32); ctx.rotate((a * Math.PI) / 180); ctx.translate(-32, -32)
      ctx.translate(32, 35.5); ctx.scale(0.41, 0.41); ctx.translate(-32, -5)
      ctx.fillStyle = i === 0 ? '#1b1b1f' : '#b3171e'
      ctx.fill(DROP)
      ctx.restore()
    })
  }

  function favicon() {
    const el = link()
    if (!el) return
    const original = el.href
    const type = el.type
    let f = 0
    el.type = 'image/png'
    const id = setInterval(() => {
      draw(f / (FRAMES - 1))
      el.href = canvas.toDataURL('image/png')
      if (++f >= FRAMES) { clearInterval(id); el.type = type; el.href = original }
    }, FRAME_MS)
  }

  setInterval(() => { tick.value++; favicon() }, PERIOD)
})
