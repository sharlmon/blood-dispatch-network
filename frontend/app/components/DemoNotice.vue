<template>
  <div class="note">
    <h2>Open demo</h2>
    <p>Login is switched off in this build, so there is nothing to sign in to. Try the tool with built-in demo data.</p>
    <NuxtLink to="/request" class="btn btn-primary">Open the demo</NuxtLink>
  </div>
</template>

<style scoped>
.note { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
h2 { margin: 0; font-size: 22px; font-weight: 800; text-transform: uppercase; color: var(--blood-600); }
p { margin: 0; font-size: 15px; line-height: 1.55; font-weight: 500; color: #5a3c3f; }
</style>
