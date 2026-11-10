<script setup lang="ts">
useHead({ title: 'New request · Blood Dispatch' })

const { search } = useDispatch()
const group = ref('B+')
const product = ref('Red cells')
const units = ref(2)
const limitH = ref(3)

const products = ['Red cells', 'Whole blood']
const submit = () => search({ group: group.value, units: units.value, product: product.value, limitH: limitH.value })
</script>

<template>
  <div class="page">
    <form class="form" @submit.prevent="submit">
      <h1>New request</h1>

      <section class="card block">
        <h2>Patient blood group</h2>
        <BloodGroupPicker v-model="group" />
        <p class="hint">
          <AppIcon name="drop" :size="18" />
          Group unknown? Request group O only, per hospital protocol.
        </p>
      </section>

      <div class="two">
        <section class="card block">
          <h2>Product</h2>
          <div class="stack">
            <button
              v-for="p in products" :key="p" type="button" class="choice" :class="{ on: product === p }"
              :aria-pressed="product === p" @click="product = p"
            >{{ p }}</button>
          </div>
        </section>

        <section class="card block">
          <h2>Units</h2>
          <div class="stepper">
            <button type="button" aria-label="One more unit" @click="units = Math.min(units + 1, 10)">+</button>
            <output class="tnum" aria-live="polite">{{ units }}</output>
            <button type="button" aria-label="One fewer unit" @click="units = Math.max(units - 1, 1)">−</button>
          </div>
        </section>
      </div>

      <section class="card block limit">
        <AppIcon name="clock" :size="24" />
        <div class="grow">
          <h2>Longest the patient can wait</h2>
          <p class="muted small">Used to flag a wait that is too long</p>
        </div>
        <div class="lim">
          <button type="button" aria-label="Shorter limit" @click="limitH = Math.max(1, limitH - 1)">−</button>
          <output class="tnum">{{ limitH }} h</output>
          <button type="button" aria-label="Longer limit" @click="limitH = Math.min(12, limitH + 1)">+</button>
        </div>
      </section>

      <p class="sms">
        <AppIcon name="sms" :size="22" />
        <span>No data? Text <b>{{ group }} {{ units }} RBC {{ limitH }}H</b> to [SHORTCODE].</span>
      </p>

      <button type="submit" class="btn btn-primary go"><AppIcon name="search" /> Find sources</button>
      <SafetyNote />
    </form>
  </div>
</template>

<style scoped>
.page { flex: 1; display: flex; justify-content: center; padding: 20px 16px 28px; }
.form { width: 100%; max-width: 520px; display: flex; flex-direction: column; gap: 14px; }
h1 { margin: 0 0 2px; font-size: 26px; font-weight: 800; letter-spacing: -0.01em; }
h2 { margin: 0 0 10px; font-size: 13px; font-weight: 800; }
.block { padding: 16px; }
.hint { display: flex; align-items: center; gap: 10px; margin: 12px 0 0; padding: 10px 12px; border-radius: 12px; background: var(--paper); color: var(--slate); font-size: 12.5px; font-weight: 600; }
.two { display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; }
.stack { display: flex; flex-direction: column; gap: 8px; }
.choice { min-height: 44px; border-radius: 12px; border: 1px solid var(--line); background: var(--white); font-weight: 700; font-size: 14px; }
.choice.on { background: var(--blood-50); border: 2px solid var(--blood-500); color: var(--blood-700); font-weight: 800; }
.stepper { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.stepper button, .lim button { width: 48px; height: 44px; border-radius: 12px; border: 1px solid var(--line); background: var(--white); font-size: 22px; font-weight: 700; }
.stepper output { font-size: 36px; font-weight: 800; line-height: 1; }
.limit { display: flex; align-items: center; gap: 12px; color: var(--amber-500); }
.limit h2 { margin: 0; color: var(--ink); }
.grow { flex: 1; }
.small { margin: 1px 0 0; font-size: 12px; font-weight: 600; }
.lim { display: flex; align-items: center; gap: 8px; color: var(--ink); }
.lim output { min-width: 44px; text-align: center; font-size: 20px; font-weight: 800; }
.sms { display: flex; align-items: center; gap: 10px; margin: 4px 0; padding: 11px 14px; border-radius: 14px; background: var(--azure-50); color: var(--azure-600); font-size: 12.5px; font-weight: 600; }
.sms span { color: var(--ink); line-height: 1.35; }
.go { min-height: 54px; font-size: 16px; }
</style>
