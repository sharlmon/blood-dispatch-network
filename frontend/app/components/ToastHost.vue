<script setup lang="ts">
const { toasts, dismiss } = useToast()
const icon = { ok: 'check', info: 'bell', warn: 'warning', error: 'warning' } as const
</script>

<template>
  <Teleport to="body">
    <div class="toasts" aria-live="polite" aria-atomic="false">
      <TransitionGroup name="t" tag="div" class="stack">
        <div v-for="t in toasts" :key="t.id" class="toast" :class="t.tone" :role="t.tone === 'error' || t.tone === 'warn' ? 'alert' : 'status'">
          <IconBadge size="sm" :tone="t.tone === 'ok' ? 'teal' : t.tone === 'info' ? 'soft' : 'amber'"><AppIcon :name="icon[t.tone]" :size="18" /></IconBadge>
          <span class="tx"><b>{{ t.title }}</b><small v-if="t.body">{{ t.body }}</small></span>
          <button type="button" class="x" aria-label="Dismiss" @click="dismiss(t.id)"><AppIcon name="close" :size="16" /></button>
          <i v-if="t.ms > 0" class="bar" :style="{ animationDuration: t.ms + 'ms' }" />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toasts { position: fixed; z-index: 120; right: 16px; top: 96px; width: min(380px, calc(100vw - 32px)); pointer-events: none; }
.stack { display: flex; flex-direction: column; gap: 10px; }
.toast { pointer-events: auto; position: relative; overflow: hidden; display: flex; align-items: center; gap: 12px; padding: 12px 12px 14px 12px; border-radius: 22px; background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px); border: 1.5px solid #ecd5d1; box-shadow: var(--sh-3); }
.toast.ok { border-color: #9fd6cd; }
.toast.warn, .toast.error { border-color: #ecc98a; }
.tx { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.tx b { font-size: 14px; color: var(--ink); }
.tx small { font-size: 13px; font-weight: 600; color: #5a3c3f; line-height: 1.4; margin-top: 1px; }
.x { width: 32px; height: 32px; border-radius: 99px; display: grid; place-items: center; color: var(--slate); background: transparent; border: 0; flex-shrink: 0; }
.x:hover { background: var(--blood-50); }
.bar { position: absolute; left: 0; bottom: 0; height: 3px; width: 100%; background: var(--blood-500); transform-origin: left; animation: toastbar linear forwards; opacity: 0.7; }
.ok .bar { background: var(--teal-600); }
.warn .bar, .error .bar { background: var(--amber-700); }
@keyframes toastbar { to { transform: scaleX(0); } }
.t-enter-active { transition: transform 0.45s cubic-bezier(0.2, 1.1, 0.3, 1), opacity 0.3s ease; }
.t-leave-active { transition: transform 0.3s ease, opacity 0.25s ease; position: absolute; width: 100%; }
.t-move { transition: transform 0.35s ease; }
.t-enter-from { opacity: 0; transform: translateX(40px) scale(0.92); }
.t-leave-to { opacity: 0; transform: translateX(40px) scale(0.95); }
@media (max-width: 899px) {
  .toasts { top: auto; bottom: calc(var(--dock-h, 96px) + 8px); right: 12px; left: 12px; width: auto; }
  .t-enter-from, .t-leave-to { transform: translateY(24px) scale(0.95); }
}
</style>
