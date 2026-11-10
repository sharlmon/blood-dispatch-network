// Responsive WebP sets generated into /public/images (name-<width>.webp). The ratio reserves space
// before the image loads so nothing jumps.
export const IMAGE_SETS: Record<string, { widths: number[]; ratio: [number, number] }> = {
  hero: { widths: [640, 1024, 1600], ratio: [2600, 1333] },
  ambulance: { widths: [640, 1200], ratio: [1180, 760] },
  'blood-draw': { widths: [480, 900], ratio: [4, 3] },
  'blood-bags': { widths: [480, 800], ratio: [1, 1] },
  community: { widths: [480, 800], ratio: [480, 555] },
  nursery: { widths: [480, 800], ratio: [480, 516] },
  clinic: { widths: [480, 800], ratio: [480, 400] },
  'patient-care': { widths: [480, 900, 1200], ratio: [3, 2] },
  'hand-tube': { widths: [640, 1000], ratio: [2, 3] }
}
