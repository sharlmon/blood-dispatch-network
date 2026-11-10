<template>
  <div class="auth">
    <BloodCells />
    <slot />
  </div>
</template>

<style scoped>
.auth { position: relative; min-height: 100dvh; }
.auth > :not(.cells) { position: relative; z-index: 1; }
</style>
