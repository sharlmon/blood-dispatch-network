<script setup lang="ts">
// Floating accessibility menu, bottom-left. Preferences persist on this device (useA11y).
const { prefs, load, set, reset, changed } = useA11y()
const route = useRoute()
// Results and Track are map screens. Phone: the panel is a bottom sheet, so sit just above it. Desktop: the
// panel stops above the corner (see those pages), so the icon stays in the usual bottom-left place.
const lift = computed(() => /^\/(results|track)(\/|$)/.test(route.path))
const open = ref(false)
const btn = ref<HTMLButtonElement | null>(null)
const panel = ref<HTMLElement | null>(null)

onMounted(load)
function close() { open.value = false; nextTick(() => btn.value?.focus()) }
watch(open, v => { if (v) nextTick(() => panel.value?.querySelector<HTMLElement>('button')?.focus()) })
function onDoc(e: MouseEvent) {
  if (open.value && !(e.target as HTMLElement).closest?.('.a11y')) open.value = false
}
onMounted(() => document.addEventListener('pointerdown', onDoc))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDoc))

const sizes = [{ v: 0, label: 'A', title: 'Default text size' }, { v: 1, label: 'A', title: 'Larger text' }, { v: 2, label: 'A', title: 'Largest text' }] as const
const toggles = [
  { k: 'contrast', title: 'High contrast', hint: 'Darker text, stronger borders' },
  { k: 'readable', title: 'Easy reading', hint: 'Wider letters and line spacing' },
  { k: 'links', title: 'Highlight links', hint: 'Underline links and buttons' },
  { k: 'calm', title: 'Calm motion', hint: 'Turn off animations and the intro' },
] as const
</script>

<template>
  <div class="a11y" :class="{ lift }" @keydown.esc="close">
    <button
      ref="btn" type="button" class="fab" :class="{ on: open || changed }" aria-haspopup="dialog"
      :aria-expanded="open" aria-controls="a11y-panel" aria-label="Accessibility options" @click="open = !open"
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="4.6" r="1.8" fill="currentColor" stroke="none" />
        <path d="M4.5 8.2c2.4.9 5 1.3 7.5 1.3s5.1-.4 7.5-1.3M12 9.6v4.2M12 13.8l-3.2 6.2M12 13.8l3.2 6.2" />
      </svg>
    </button>
    <Transition name="pop">
      <section v-if="open" id="a11y-panel" ref="panel" class="panel" role="dialog" aria-label="Accessibility options">
        <header>
          <h2>Accessibility</h2>
          <button type="button" class="x" aria-label="Close accessibility options" @click="close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </header>

        <div class="row">
          <div class="lbl"><b>Text size</b><span>Make everything easier to read</span></div>
          <div class="sizes" role="group" aria-label="Text size">
            <button
              v-for="(s, i) in sizes" :key="s.v" type="button" :class="{ sel: prefs.text === s.v }" :aria-pressed="prefs.text === s.v"
              :aria-label="s.title" :style="{ fontSize: 15 + i * 4 + 'px' }" @click="set('text', s.v)"
            >{{ s.label }}</button>
          </div>
        </div>

        <button
          v-for="t in toggles" :key="t.k" type="button" class="row tog" role="switch" :aria-checked="prefs[t.k]" @click="set(t.k, !prefs[t.k])"
        >
          <span class="lbl"><b>{{ t.title }}</b><span>{{ t.hint }}</span></span>
          <i class="sw" :class="{ on: prefs[t.k] }"><u /></i>
        </button>

        <button type="button" class="reset" :disabled="!changed" @click="reset">Reset to default</button>
      </section>
    </Transition>
  </div>
</template>

<style scoped>
.a11y { position: fixed; left: 20px; bottom: 20px; z-index: 90; }
.fab {
  width: 56px; height: 56px; border-radius: 99px; display: grid; place-items: center; cursor: pointer; color: #fff;
  border: 3px solid var(--paper); background: linear-gradient(180deg, #0e8277, var(--primary-600));
  box-shadow: 0 10px 24px rgba(8, 90, 83, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.28); transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.fab:hover { transform: translateY(-2px); }
.fab:active { transform: scale(0.94); }
.fab.on { background: linear-gradient(180deg, var(--ink-deep), #123f49); }
.panel {
  position: absolute; left: 0; bottom: 70px; width: min(340px, calc((100vw - 24px) / var(--a11y-zoom, 1))); padding: 16px; border-radius: 24px;
  background: #fff; border: 1px solid var(--line); box-shadow: 0 24px 60px rgba(12, 43, 51, 0.28); transform-origin: bottom left; max-height: calc((100dvh - 190px) / var(--a11y-zoom, 1)); overflow-y: auto; overscroll-behavior: contain;
}
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
h2 { margin: 0; font-size: 17px; font-weight: 800; color: var(--ink-deep); }
.x { width: 44px; height: 44px; margin: -8px -8px -8px 0; border: 0; border-radius: 99px; background: none; color: var(--slate); cursor: pointer; display: grid; place-items: center; }
.x:hover { background: var(--primary-50); }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; min-height: 56px; padding: 10px 12px; margin-top: 8px; border-radius: 16px; border: 1px solid var(--line); background: var(--paper); font: inherit; text-align: left; color: var(--ink); }
.tog { cursor: pointer; }
.tog:hover { border-color: var(--primary-500); }
.lbl { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.lbl b { font-size: 14px; font-weight: 800; color: var(--ink-deep); }
.lbl span { font-size: 12.5px; color: var(--slate); line-height: 1.35; }
.sizes { display: flex; gap: 6px; flex: none; }
.sizes button { width: 44px; height: 44px; border-radius: 14px; border: 1.5px solid var(--line); background: #fff; font-family: inherit; font-weight: 800; color: var(--primary-700); cursor: pointer; }
.sizes button.sel { background: var(--primary-600); border-color: var(--primary-600); color: #fff; }
.sw { flex: none; width: 46px; height: 28px; border-radius: 99px; background: #b9c8c6; padding: 3px; transition: background 0.2s ease; }
.sw u { display: block; width: 22px; height: 22px; border-radius: 99px; background: #fff; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.25); transition: transform 0.2s ease; }
.sw.on { background: var(--primary-600); }
.sw.on u { transform: translateX(18px); }
.reset { width: 100%; height: 44px; margin-top: 12px; border-radius: 99px; border: 1.5px solid var(--primary-500); background: #fff; color: var(--primary-700); font: inherit; font-weight: 800; cursor: pointer; }
.reset:disabled { opacity: 0.45; cursor: default; }
.pop-enter-active, .pop-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(8px) scale(0.97); }
/* Phones: sit above the bottom navigation dock. */
@media (max-width: 899px) {
  .a11y { left: 12px; bottom: calc(var(--dock-h, 96px) + 14px + env(safe-area-inset-bottom)); }
  .a11y.lift { bottom: auto; top: calc(28vh - 62px); }
  .a11y.lift .panel { bottom: auto; top: 64px; transform-origin: top left; max-height: calc((100dvh - 28vh - 60px) / var(--a11y-zoom, 1)); }
  .fab { width: 48px; height: 48px; }
}
</style>
