<script setup lang="ts">
// Dialog that is a centred card on desktop and a bottom sheet on phones.
const open = defineModel<boolean>({ required: true })
const props = withDefaults(defineProps<{ title: string; sub?: string; wide?: boolean }>(), { sub: '', wide: false })

const dlg = ref<HTMLElement | null>(null)
let last: HTMLElement | null = null
const uid = useId()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { open.value = false; return }
  if (e.key !== 'Tab' || !dlg.value) return
  const f = [...dlg.value.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter(x => x.offsetParent !== null)
  if (!f.length) return
  const first = f[0]!, end = f[f.length - 1]!
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); end.focus() }
  else if (!e.shiftKey && document.activeElement === end) { e.preventDefault(); first.focus() }
}
watch(open, async (v) => {
  if (!import.meta.client) return
  document.documentElement.style.overflow = v ? 'hidden' : ''
  if (v) {
    last = document.activeElement as HTMLElement | null
    window.addEventListener('keydown', onKey)
    await nextTick()
    dlg.value?.focus()
  } else {
    window.removeEventListener('keydown', onKey)
    last?.focus?.()
  }
})
onBeforeUnmount(() => { if (import.meta.client) { window.removeEventListener('keydown', onKey); document.documentElement.style.overflow = '' } })
</script>

<template>
  <Teleport to="body">
    <Transition name="m">
      <div v-if="open" class="back" @click.self="open = false">
        <div ref="dlg" class="dlg" :class="{ wide: props.wide }" role="dialog" aria-modal="true" :aria-labelledby="uid" tabindex="-1">
          <span class="grab" aria-hidden="true" />
          <header>
            <span class="hd"><h2 :id="uid">{{ title }}</h2><p v-if="sub">{{ sub }}</p></span>
            <button type="button" class="x" aria-label="Close" @click="open = false"><AppIcon name="close" :size="20" /></button>
          </header>
          <div class="body"><slot /></div>
          <footer v-if="$slots.footer"><slot name="footer" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.back { position: fixed; inset: 0; z-index: 110; background: rgba(59, 10, 14, 0.5); backdrop-filter: blur(5px); display: grid; place-items: center; padding: 16px; }
.dlg { width: 100%; max-width: 480px; max-height: min(86dvh, 720px); display: flex; flex-direction: column; border-radius: 34px 38px 34px 40px / 38px 34px 40px 34px; background: linear-gradient(180deg, #fff, #f3f8f7); border: 1.5px solid var(--primary-500); box-shadow: 0 30px 80px rgba(4, 40, 38, 0.45); outline: none; overflow: hidden; }
.dlg.wide { max-width: 640px; }
.grab { display: none; width: 44px; height: 5px; border-radius: 99px; background: #c9dbd8; margin: 10px auto 0; }
header { display: flex; align-items: flex-start; gap: 12px; padding: 20px 20px 8px 24px; }
.hd { flex: 1; min-width: 0; }
h2 { margin: 0; font-size: 20px; font-weight: 800; color: var(--ink-deep); line-height: 1.2; }
.hd p { margin: 4px 0 0; font-size: 13.5px; font-weight: 600; color: #44545f; line-height: 1.4; }
.x { width: 44px; height: 44px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: #fff; display: grid; place-items: center; color: var(--primary-700); flex-shrink: 0; transition: transform 0.2s ease; }
.x:hover { transform: rotate(90deg); }
.body { padding: 8px 20px 20px 24px; overflow-y: auto; overscroll-behavior: contain; }
footer { padding: 12px 20px 20px; border-top: 1px solid #e2ece9; display: flex; gap: 10px; flex-wrap: wrap; }
footer > :deep(*) { flex: 1; min-width: 140px; }
.m-enter-active, .m-leave-active { transition: opacity 0.25s ease; }
.m-enter-active .dlg { transition: transform 0.4s cubic-bezier(0.2, 1.1, 0.3, 1), opacity 0.3s ease; }
.m-leave-active .dlg { transition: transform 0.22s ease, opacity 0.2s ease; }
.m-enter-from, .m-leave-to { opacity: 0; }
.m-enter-from .dlg, .m-leave-to .dlg { transform: translateY(24px) scale(0.94); opacity: 0; }
@media (max-width: 599px) {
  .back { place-items: end center; padding: 0; }
  .dlg { max-width: none; max-height: 88dvh; border-radius: 34px 34px 0 0; border-bottom: 0; }
  .grab { display: block; }
  .m-enter-from .dlg, .m-leave-to .dlg { transform: translateY(100%); }
  .body { padding-bottom: calc(20px + env(safe-area-inset-bottom)); }
}
</style>
