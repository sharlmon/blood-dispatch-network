<script setup lang="ts">
// One hand hands a bag of blood to another, on a loop. Pure SVG + CSS, off under reduced motion.
</script>

<template>
  <svg class="hands" viewBox="0 0 320 190" role="img" aria-label="One hand passes a bag of blood to another hand">
    <g transform="translate(138 70)"><g class="a"><HandHold /></g></g>
    <g transform="translate(182 70)"><g class="b"><HandHold flip /></g></g>
    <g transform="translate(160 72)">
      <g class="bag">
        <path d="M-3 0v-5h6v5" stroke="#7e1015" stroke-width="1.8" fill="none" stroke-linecap="round" />
        <rect x="-12" y="0" width="24" height="32" rx="7" fill="#e86a63" stroke="#7e1015" stroke-width="2" />
        <rect x="-6" y="9" width="12" height="10" rx="2" fill="#fff" stroke="#b3171e" stroke-width="1.3" />
        <path d="M-8 6c-1 4-1 9 0 13" stroke="#fff" stroke-width="2" fill="none" opacity="0.7" stroke-linecap="round" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.hands { width: 100%; height: auto; display: block; overflow: hidden; }
.a, .b { animation-duration: 6.5s; animation-iteration-count: infinite; animation-timing-function: ease-in-out; }
.a { animation-name: armA; }
.b { animation-name: armB; }
.bag { animation: bag 6.5s ease-in-out infinite; opacity: 0; }
@keyframes armA { 0%, 5% { translate: -10px 0; } 18%, 34% { translate: 6px 0; } 52%, 100% { translate: -10px 0; } }
@keyframes armB { 0%, 25% { translate: 10px 0; } 40%, 56% { translate: -6px 0; } 76%, 100% { translate: 10px 0; } }
@keyframes bag {
  0% { opacity: 0; translate: -16px 0; }
  8% { opacity: 1; translate: -16px 0; }
  18%, 32% { translate: -4px 0; }
  46%, 56% { translate: 0 0; }
  76%, 92% { translate: 14px 0; opacity: 1; }
  100% { opacity: 0; translate: 14px 0; }
}
@media (prefers-reduced-motion: reduce) { .bag { opacity: 1; } }
</style>
