<script setup lang="ts">
// Demo sign in / create account. Accounts live in this browser only; there is no password.
const props = defineProps<{ mode: 'in' | 'up' }>()
const { find, signUp, signIn } = useDemoAccount()
const route = useRoute()

const name = ref('')
const email = ref(typeof route.query.email === 'string' ? route.query.email : '')
const hospital = ref('')
const role = ref('Lab worker')
const error = ref('')
const busy = ref(false)

const roles = ['Lab worker', 'Clinician', 'Blood centre staff']
const sites = ['Lakeview District Hospital', 'Hillcrest Hospital', 'Central Regional Blood Centre']

const validEmail = (e: string) => /^\S+@\S+\.\S+$/.test(e.trim())

function submit() {
  error.value = ''
  if (!validEmail(email.value)) { error.value = 'Enter an email like you@hospital.org.'; return }
  if (props.mode === 'in') {
    if (!signIn(email.value)) { error.value = 'We have no account for that email here yet. Create one in a few seconds.'; return }
  } else {
    if (name.value.trim().length < 2) { error.value = 'Add your name.'; return }
    if (hospital.value.trim().length < 2) { error.value = 'Add your hospital or centre.'; return }
    signUp({ name: name.value, email: email.value, hospital: hospital.value, role: role.value })
  }
  busy.value = true
  navigateTo('/request')
}
</script>

<template>
  <div class="dform">
    <div class="seg" role="tablist" aria-label="Sign in or create account">
      <NuxtLink to="/sign-in" role="tab" :aria-selected="mode === 'in'" :class="{ on: mode === 'in' }">Sign in</NuxtLink>
      <NuxtLink to="/sign-up" role="tab" :aria-selected="mode === 'up'" :class="{ on: mode === 'up' }">Create account</NuxtLink>
    </div>

    <h2>{{ mode === 'in' ? 'Welcome back' : 'Set up your hospital' }}</h2>
    <p class="lead">{{ mode === 'in' ? 'Sign in to request blood for your hospital.' : 'Takes a few seconds. Anyone can try it, and nothing leaves this device.' }}</p>

    <form novalidate @submit.prevent="submit">
      <template v-if="mode === 'up'">
        <label class="f" for="d-name"><span>Your name</span>
          <input id="d-name" v-model="name" type="text" autocomplete="name" placeholder="Amina Otieno" enterkeyhint="next">
        </label>
      </template>

      <label class="f" for="d-email"><span>Work email</span>
        <input id="d-email" v-model="email" type="email" inputmode="email" autocomplete="email" placeholder="you@hospital.org" enterkeyhint="next">
      </label>

      <template v-if="mode === 'up'">
        <label class="f" for="d-site"><span>Hospital or centre</span>
          <input id="d-site" v-model="hospital" type="text" list="d-sites" autocomplete="organization" placeholder="Type or pick your hospital">
          <datalist id="d-sites"><option v-for="s in sites" :key="s" :value="s" /></datalist>
        </label>

        <fieldset class="f roles">
          <legend>Your role</legend>
          <div class="chips">
            <label v-for="r in roles" :key="r" class="chip-r" :class="{ on: role === r }">
              <input v-model="role" type="radio" name="d-role" :value="r"><span>{{ r }}</span>
            </label>
          </div>
        </fieldset>
      </template>

      <p v-if="error" class="err" role="alert">
        <AppIcon name="warning" :size="18" />
        <span>{{ error }}
          <NuxtLink v-if="mode === 'in'" :to="{ path: '/sign-up', query: { email } }">Create account</NuxtLink>
        </span>
      </p>

      <button type="submit" class="go" :disabled="busy">{{ mode === 'in' ? 'Sign in' : 'Create account and continue' }}</button>
    </form>

    <p class="swap">
      <template v-if="mode === 'in'">New here? <NuxtLink to="/sign-up">Create an account</NuxtLink></template>
      <template v-else>Already have one? <NuxtLink to="/sign-in">Sign in</NuxtLink></template>
    </p>
    <NuxtLink to="/request?demo=1" class="try">Or try it without an account</NuxtLink>
  </div>
</template>

<style scoped>
.dform { display: flex; flex-direction: column; }
.seg { display: grid; grid-template-columns: 1fr 1fr; padding: 4px; border-radius: 99px; background: var(--blood-50); border: 1.5px solid #f0d3cf; margin-bottom: 22px; }
.seg a { min-height: 44px; display: grid; place-items: center; border-radius: 99px; text-decoration: none; font-weight: 800; font-size: 14px; color: var(--blood-700); transition: background 0.2s ease, color 0.2s ease; }
.seg a.on { background: linear-gradient(180deg, #c3282c, #9a1319); color: #fff; box-shadow: 0 6px 14px rgba(179, 23, 30, 0.3); }
h2 { margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.02em; text-transform: uppercase; color: var(--blood-600); line-height: 1.05; }
.lead { margin: 8px 0 20px; font-size: 15px; line-height: 1.5; font-weight: 500; color: #5a3c3f; }
form { display: grid; gap: 16px; }
.f { display: grid; gap: 7px; border: 0; padding: 0; margin: 0; min-width: 0; }
.f > span, .f > legend { font-size: 13px; font-weight: 800; color: var(--wine); padding: 0; }
.f input { width: 100%; min-height: 52px; box-sizing: border-box; border-radius: 99px; border: 1.5px solid #e6d3cf; background: #fff; padding: 0 20px; font: inherit; font-size: 16px; color: var(--ink); transition: border-color 0.2s ease, box-shadow 0.2s ease; }
.f input::placeholder { color: #9a8486; }
.f input:focus { outline: none; border-color: var(--blood-500); box-shadow: 0 0 0 4px rgba(179, 23, 30, 0.14); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip-r { position: relative; }
.chip-r input { position: absolute; opacity: 0; inset: 0; width: 100%; height: 100%; min-height: 0; cursor: pointer; margin: 0; }
.chip-r span { display: inline-flex; align-items: center; min-height: 44px; padding: 0 16px; border-radius: 99px; border: 1.5px solid #e6d3cf; background: #fff; font-weight: 700; font-size: 14px; color: var(--ink); transition: all 0.2s ease; }
.chip-r.on span { background: var(--blood-50); border-color: var(--blood-500); color: var(--blood-700); }
.chip-r:focus-within span { box-shadow: 0 0 0 4px rgba(179, 23, 30, 0.14); }
.err { margin: 0; display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; border-radius: 18px; background: #fff3d9; color: #6a3f00; font-size: 14px; font-weight: 600; line-height: 1.45; }
.err svg { flex-shrink: 0; margin-top: 1px; }
.err a { color: var(--blood-700); font-weight: 800; margin-left: 4px; }
.go { min-height: 56px; border: 0; border-radius: 99px; background: linear-gradient(180deg, #c3282c, #9a1319); color: #fff; font: inherit; font-weight: 800; font-size: 17px; box-shadow: 0 14px 26px rgba(179, 23, 30, 0.35); cursor: pointer; transition: transform 0.15s ease, box-shadow 0.2s ease; }
.go:active { transform: scale(0.98); }
.go:disabled { opacity: 0.7; }
.swap { margin: 18px 0 0; text-align: center; font-size: 14px; font-weight: 600; color: #5a3c3f; }
.swap a { color: var(--blood-700); font-weight: 800; }
.try { margin-top: 6px; min-height: 44px; display: grid; place-items: center; text-align: center; font-size: 14px; font-weight: 700; color: var(--slate); }
@media (prefers-reduced-motion: reduce) { .go, .seg a, .f input, .chip-r span { transition: none; } }
</style>
