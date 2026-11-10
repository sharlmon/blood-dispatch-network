<script setup lang="ts">
const { public: { apiBase } } = useRuntimeConfig()
const { data: health, error } = await useFetch<{ status: string }>(`${apiBase}/api/health`)
</script>

<template>
  <main style="max-width: 40rem; margin: 3rem auto; font-family: system-ui">
    <h1>Blood Dispatch Network</h1>
    <p v-if="health">API status: {{ health.status }}</p>
    <p v-else-if="error">API unreachable: fall back to the phone process.</p>
  </main>
</template>
