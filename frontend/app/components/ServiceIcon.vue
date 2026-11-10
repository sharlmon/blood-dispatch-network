<script setup lang="ts">
// Illustrated duotone icons (pink fill, brick outline) for services and sections.
withDefaults(defineProps<{ name: 'find' | 'bag' | 'ambulance' | 'confirm' | 'window' | 'bell' | 'sms' | 'pen' | 'shield'; size?: number }>(), { size: 30 })
const DROP = 'M24 6c6.5 7.6 11 13.2 11 19a11 11 0 0 1-22 0c0-5.8 4.5-11.4 11-19z'
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 48 48" fill="none" stroke="#7e1015" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'find'">
      <path :d="DROP" fill="#f4b9b3" transform="translate(-3 -2)" />
      <path d="M17 18c-1.4 2-2.4 3.5-2.4 5.2" stroke="#fff" stroke-width="2" />
      <circle cx="29" cy="30" r="7.5" fill="#fff" stroke="#b3171e" stroke-width="2.2" />
      <path d="M34.5 35.5 41 42" stroke="#b3171e" stroke-width="3.4" />
    </template>
    <template v-else-if="name === 'bag'">
      <path d="M20 10V6.5h8V10" />
      <rect x="13" y="10" width="22" height="27" rx="7" fill="#e86a63" />
      <path d="M17 15c-1 3-1 8 0 11" stroke="#fff" stroke-width="2" opacity="0.7" />
      <rect x="19" y="19" width="10" height="9" rx="2" fill="#fff" stroke="#b3171e" />
      <path d="M22 22.5h4M22 25h3" stroke="#b3171e" stroke-width="1.4" />
      <path d="M24 37v3.5a3 3 0 0 0 3 3h2.5" stroke="#b3171e" stroke-width="2.4" />
    </template>
    <template v-else-if="name === 'ambulance'">
      <path d="M4 33V19a3 3 0 0 1 3-3h20v17z" fill="#fff" />
      <path d="M27 21h7.500l6 6.500V33H27z" fill="#f4b9b3" />
      <path d="M30 24h4l3 3.500h-7z" fill="#fff" stroke-width="1.4" />
      <path d="M15.500 20v8M11.500 24h8" stroke="#b3171e" stroke-width="3" />
      <circle cx="13" cy="35" r="4" fill="#fff" />
      <circle cx="34.500" cy="35" r="4" fill="#fff" />
    </template>
    <template v-else-if="name === 'confirm'">
      <path :d="DROP" fill="#f4b9b3" transform="translate(-3 -1)" />
      <circle cx="31" cy="31" r="9.500" fill="#fff" stroke="#b3171e" stroke-width="2.200" />
      <path d="M26.500 31l3 3 5.500-6" stroke="#0b7f73" stroke-width="2.800" />
    </template>
    <template v-else-if="name === 'window'">
      <path :d="DROP" fill="#f4b9b3" />
      <path d="M13 31h22M13 27v8M35 27v8" stroke="#b3171e" stroke-width="2.200" />
      <circle cx="24" cy="31" r="3.200" fill="#fff" stroke="#b3171e" stroke-width="2" />
    </template>
    <template v-else-if="name === 'bell'">
      <path d="M12 32V22a12 12 0 0 1 24 0v10l3 3H9z" fill="#f4b9b3" />
      <path d="M20 40h8" stroke-width="2.400" />
      <path d="M24 17c2.800 3.300 4.200 5.300 4.200 7.300a4.200 4.200 0 0 1-8.400 0c0-2 1.400-4 4.200-7.300z" fill="#fff" stroke="#b3171e" stroke-width="1.600" />
    </template>
    <template v-else-if="name === 'sms'">
      <path d="M7 9h34a3 3 0 0 1 3 3v19a3 3 0 0 1-3 3H21l-9 8v-8H7a3 3 0 0 1-3-3V12a3 3 0 0 1 3-3z" fill="#f4b9b3" />
      <path d="M24 14.500c3.200 3.700 4.800 5.900 4.800 8.200a4.800 4.800 0 0 1-9.600 0c0-2.300 1.600-4.500 4.800-8.200z" fill="#fff" stroke="#b3171e" stroke-width="1.800" />
    </template>
    <template v-else-if="name === 'pen'">
      <path d="M31 8l9 9L18 39l-11 3 3-11z" fill="#f4b9b3" />
      <path d="M27 12l9 9" />
      <path d="M10 31l7 7" />
    </template>
    <template v-else>
      <path d="M24 5l16 6v12c0 9-6.500 16-16 20C14.500 39 8 32 8 23V11z" fill="#f4b9b3" />
      <path d="M24 15c2.800 3.300 4.200 5.300 4.200 7.300a4.200 4.200 0 0 1-8.400 0c0-2 1.400-4 4.200-7.300z" fill="#fff" stroke="#b3171e" stroke-width="1.600" />
    </template>
  </svg>
</template>
