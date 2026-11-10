<script setup lang="ts">
// A pinching hand, drawn in a local frame where the pinch point is (0,0) and the hand
// comes in from the upper left. `flip` mirrors it for a hand coming from the right.
withDefaults(defineProps<{ flip?: boolean; angle?: number }>(), { angle: 32 })
</script>

<template>
  <g :transform="flip ? 'scale(-1 1)' : undefined">
    <g :transform="`rotate(${angle})`">
      <g transform="translate(-92 -24)" stroke="#7e1015" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" fill="#f7d9d1">
        <!-- forearm, tapering to the wrist -->
        <path d="M-150 -26 L-6 -12 Q6 -10 6 2 Q6 14 -6 16 L-150 34 Z" />
        <path d="M-120 -16 L-8 -4" stroke="#b3171e" stroke-width="1.6" fill="none" />
        <path d="M-100 8 C-60 8 -34 2 -6 4" stroke="#b3171e" stroke-width="1.2" fill="none" opacity="0.7" />
        <!-- back of the hand -->
        <path d="M-2 -14 Q28 -24 50 -14 Q64 -8 64 6 Q64 20 48 26 Q22 32 -2 16 Z" />
        <!-- curled fingers under the palm -->
        <path d="M44 20 Q58 20 62 12 Q64 26 52 30 Q44 30 40 24 Z" />
        <path d="M32 24 Q46 26 50 18 Q52 34 40 36 Q32 36 28 29 Z" />
        <!-- index finger, curving down to the pinch -->
        <path d="M46 -12 Q80 -16 94 2 Q100 12 94 22 Q90 26 86 22 Q88 12 82 6 Q70 -2 48 2 Z" />
        <!-- thumb, coming up to meet it -->
        <path d="M34 14 Q62 34 90 28 Q98 26 94 20 Q88 16 80 18 Q64 20 46 6 Z" />
        <path d="M60 -6 Q70 -8 78 -4" stroke="#b3171e" stroke-width="1" fill="none" opacity="0.6" />
      </g>
    </g>
  </g>
</template>
