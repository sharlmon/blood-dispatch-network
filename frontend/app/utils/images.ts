// Responsive WebP sets generated into /public/images (name-<width>.webp). The ratio reserves space
// before the image loads so nothing jumps.
export const IMAGE_SETS: Record<string, { widths: number[]; ratio: [number, number] }> = {
  transfusion: { widths: [640, 1024, 1600], ratio: [3, 2] },
  ambulance: { widths: [640, 1200], ratio: [1180, 760] },
  'blood-draw': { widths: [480, 900], ratio: [4, 3] },
  'blood-bags': { widths: [480, 800], ratio: [1, 1] },
  paramedics: { widths: [480, 800], ratio: [3, 2] },
  'care-team': { widths: [480, 800], ratio: [1400, 1811] },
  'patient-care': { widths: [480, 900, 1200], ratio: [3, 2] },
  'hand-tube': { widths: [640, 1000], ratio: [2, 3] }
}
