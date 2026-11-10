<script setup lang="ts">
// Dropdown that uses the app theme (the native one cannot be styled). Popover on desktop, sheet on phones.
// Long lists scroll, keep the active option in view, and jump to an option when you type its first letters.
export interface Opt { value: string; label?: string; hint?: string }
const model = defineModel<string>({ required: true })
const props = defineProps<{ options: (string | Opt)[]; label: string; placeholder?: string; disabled?: boolean }>()

const opts = computed<Opt[]>(() => props.options.map(o => typeof o === 'string' ? { value: o } : o))
const current = computed(() => opts.value.find(o => o.value === model.value))
const shown = computed(() => current.value?.label ?? current.value?.value ?? props.placeholder ?? model.value)
const open = ref(false)
const sheet = ref(false)
const active = ref(0)
const btn = ref<HTMLButtonElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const pos = reactive({ top: 0, left: 0, minWidth: 0, up: false })
const uid = useId()
const MAX_H = 360

function place() {
  const r = btn.value!.getBoundingClientRect()
  const h = Math.min(opts.value.length * 52 + 16, MAX_H)
  pos.up = window.innerHeight - r.bottom < h + 16 && r.top > h
  pos.top = pos.up ? r.top - 8 : r.bottom + 8
  pos.minWidth = Math.max(r.width, 240)
  pos.left = Math.min(Math.max(12, r.right - pos.minWidth), window.innerWidth - pos.minWidth - 12)
}
function reveal(block: ScrollLogicalPosition = 'nearest') {
  nextTick(() => document.getElementById(`${uid}-${active.value}`)?.scrollIntoView({ block }))
}
async function toggle() {
  if (props.disabled) return
  if (open.value) { open.value = false; return }
  sheet.value = window.matchMedia('(max-width: 599px)').matches
  active.value = Math.max(0, opts.value.findIndex(o => o.value === model.value))
  if (!sheet.value) place()
  open.value = true
  await nextTick()
  pop.value?.focus()
  reveal('center')
}
function pick(o: Opt) { model.value = o.value; open.value = false; btn.value?.focus() }

let typed = ''
let typedAt = 0
function typeAhead(ch: string) {
  const now = Date.now()
  typed = now - typedAt > 700 ? ch : typed + ch
  typedAt = now
  const i = opts.value.findIndex(o => (o.label ?? o.value).toLowerCase().startsWith(typed))
  if (i >= 0) { active.value = i; reveal() }
}
function onKey(e: KeyboardEvent) {
  const n = opts.value.length
  if (!n) return
  if (e.key === 'ArrowDown') { e.preventDefault(); active.value = (active.value + 1) % n; reveal() }
  else if (e.key === 'ArrowUp') { e.preventDefault(); active.value = (active.value - 1 + n) % n; reveal() }
  else if (e.key === 'Home') { e.preventDefault(); active.value = 0; reveal() }
  else if (e.key === 'End') { e.preventDefault(); active.value = n - 1; reveal() }
  else if (e.key === 'Enter' || (e.key === ' ' && Date.now() - typedAt > 700)) { e.preventDefault(); pick(opts.value[active.value]!) }
  else if (e.key === 'Escape' || e.key === 'Tab') { open.value = false; btn.value?.focus() }
  else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); typeAhead(e.key.toLowerCase()) }
}
function away(e: MouseEvent) {
  if (!open.value || sheet.value) return
  const t = e.target as Node
  if (!pop.value?.contains(t) && !btn.value?.contains(t)) open.value = false
}
// Close when the page scrolls, but not when the list itself scrolls.
const onScroll = (e: Event) => { if (!pop.value?.contains(e.target as Node)) open.value = false }
const close = () => { open.value = false }
onMounted(() => { document.addEventListener('mousedown', away); window.addEventListener('resize', close); window.addEventListener('scroll', onScroll, true) })
onBeforeUnmount(() => { document.removeEventListener('mousedown', away); window.removeEventListener('resize', close); window.removeEventListener('scroll', onScroll, true) })
</script>

<template>
  <button ref="btn" type="button" class="trig" :class="{ open, empty: !current }" :disabled="disabled" aria-haspopup="listbox" :aria-expanded="open" :aria-label="`${label}: ${shown}`" @click="toggle">
    <span>{{ shown }}</span>
    <svg width="12" height="8" viewBox="0 0 12 8" aria-hidden="true"><path d="M1 1l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
  </button>

  <Teleport to="body">
    <Transition name="pp">
      <div v-if="open && !sheet" ref="pop" class="pop" :class="{ up: pos.up }" role="listbox" tabindex="-1" :aria-label="label" :aria-activedescendant="`${uid}-${active}`"
        :style="{ top: pos.top + 'px', left: pos.left + 'px', minWidth: pos.minWidth + 'px', maxHeight: MAX_H + 'px' }" @keydown="onKey">
        <div v-for="(o, i) in opts" :id="`${uid}-${i}`" :key="o.value" role="option" :aria-selected="o.value === model" class="opt" :class="{ on: o.value === model, act: i === active }" @mouseenter="active = i" @click="pick(o)">
          <span class="t"><b>{{ o.label ?? o.value }}</b><small v-if="o.hint">{{ o.hint }}</small></span>
          <AppIcon v-if="o.value === model" name="check" :size="18" />
        </div>
      </div>
    </Transition>
  </Teleport>

  <AppModal v-if="sheet" v-model="open" :title="label">
    <div class="sheetlist" role="listbox" :aria-label="label">
      <button v-for="(o, i) in opts" :id="`${uid}-${i}`" :key="o.value" type="button" role="option" :aria-selected="o.value === model" class="sopt" :class="{ on: o.value === model }" @click="pick(o)">
        <span class="t"><b>{{ o.label ?? o.value }}</b><small v-if="o.hint">{{ o.hint }}</small></span>
        <AppIcon v-if="o.value === model" name="check" :size="20" />
      </button>
    </div>
  </AppModal>
</template>

<style scoped>
.trig { min-height: 44px; max-width: 100%; padding: 0 16px 0 18px; border-radius: 99px; border: 1.5px solid #c9dbd8; background: #fff; color: var(--primary-700); font-weight: 800; font-size: 14px; display: inline-flex; align-items: center; gap: 10px; transition: box-shadow 0.2s ease, border-color 0.2s ease; }
.trig span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.trig svg { flex-shrink: 0; transition: transform 0.25s ease; }
.trig.empty span { color: #5d6d78; }
.trig:disabled { opacity: 0.6; cursor: progress; }
.trig.open { border-color: var(--primary-500); box-shadow: 0 0 0 4px rgba(10, 107, 98, 0.14); }
.trig.open svg { transform: rotate(180deg); }
.pop { position: fixed; z-index: 130; padding: 8px; border-radius: 24px; background: rgba(255, 255, 255, 0.98); border: 1.5px solid var(--primary-500); box-shadow: 0 24px 50px rgba(4, 40, 38, 0.28); outline: none; transform-origin: top right; overflow-y: auto; overscroll-behavior: contain; max-width: calc(100vw - 24px); }
.pop.up { transform: translateY(-100%); transform-origin: bottom right; }
.opt, .sopt { display: flex; align-items: center; gap: 10px; min-height: 48px; padding: 6px 14px; border-radius: 16px; cursor: pointer; color: var(--ink); width: 100%; text-align: left; background: transparent; border: 0; font: inherit; }
.opt + .opt { margin-top: 2px; }
.t { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.t b { font-size: 14.5px; font-weight: 800; }
.t small { font-size: 12.5px; font-weight: 600; color: #5d6d78; }
.opt.act { background: var(--primary-50); }
.opt.on, .sopt.on { color: var(--primary-700); }
.opt svg, .sopt svg { color: var(--primary-500); flex-shrink: 0; }
.sheetlist { display: grid; gap: 8px; }
.sopt { min-height: 56px; padding: 8px 18px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: #fff; }
.sopt.on { background: var(--primary-50); border-color: var(--primary-500); }
.pp-enter-active { transition: opacity 0.18s ease, transform 0.28s cubic-bezier(0.2, 1.1, 0.3, 1); }
.pp-leave-active { transition: opacity 0.12s ease; }
.pp-enter-from, .pp-leave-to { opacity: 0; }
.pp-enter-from { transform: translateY(-6px) scale(0.96); }
.pop.up.pp-enter-from { transform: translateY(-100%) translateY(6px) scale(0.96); }
</style>
