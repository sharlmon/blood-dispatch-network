<script setup lang="ts">
// Phone menu: a hamburger in the header that opens a sheet. The bottom bar handles the main
// destinations; this sheet holds account, hospital, status and secondary links.
const { public: { authEnabled, demoAuth } } = useRuntimeConfig()
const { account, signOut } = useDemoAccount()
const { toast } = useToast()
const leave = () => { signOut(); open.value = false; navigateTo('/'); toast({ title: 'Signed out', body: 'See you next time.' }) }
const { hospital } = useSite()
const route = useRoute()
const open = ref(route.query.menu === 'open')

watch(() => route.fullPath, () => { open.value = false })
watch(open, (v) => { if (import.meta.client) document.documentElement.style.overflow = v ? 'hidden' : '' })
const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') open.value = false }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey); document.documentElement.style.overflow = '' })

const tools = [
  { to: '/prealerts', icon: 'bell', label: 'Pre-alerts', sub: 'Hospitals to review for a top-up' },
  { to: '/evidence', icon: 'evidence', label: 'Evidence', sub: 'How well the estimates held up' }
]
const links = [
  { hash: '#how', icon: 'route', label: 'How it works' },
  { hash: '#data', icon: 'results', label: 'The data' },
  { hash: '#phone', icon: 'sms', label: 'Who uses it, and SMS' },
  { hash: '#safe', icon: 'warning', label: 'Built to be safe' }
]
</script>

<template>
  <button type="button" class="burger" :class="{ open }" :aria-expanded="open" aria-controls="phone-menu" aria-label="Menu" @click="open = !open">
    <i /><i /><i />
  </button>

  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="overlay" @click.self="open = false">
        <nav id="phone-menu" class="sheet" aria-label="Menu">
          <div class="top">
            <BrandLogo :size="34" />
            <button type="button" class="x" aria-label="Close menu" @click="open = false"><AppIcon name="back" :size="20" /></button>
          </div>

          <p class="lab">Tools</p>
          <ul class="links">
            <li v-for="t in tools" :key="t.to">
              <NuxtLink :to="t.to" class="link tool" @click="open = false"><IconBadge size="md"><AppIcon :name="t.icon" :size="22" /></IconBadge><span class="lt">{{ t.label }}<small>{{ t.sub }}</small></span></NuxtLink>
            </li>
          </ul>

          <p class="lab">About the project</p>
          <ul class="links">
            <li v-for="l in links" :key="l.hash">
              <NuxtLink :to="{ path: '/', hash: l.hash }" class="link" @click="open = false"><IconBadge size="md"><AppIcon :name="l.icon" :size="22" /></IconBadge>{{ l.label }}</NuxtLink>
            </li>
          </ul>

          <div class="acct">
            <template v-if="authEnabled">
              <Show when="signed-in">
                <p class="lab">Your hospital</p>
                <OrganizationSwitcher :hide-personal="true" after-select-organization-url="/request" />
              </Show>
              <Show when="signed-out">
                <NuxtLink to="/sign-in" class="btn btn-primary">Sign in</NuxtLink>
              </Show>
            </template>
            <template v-else-if="demoAuth">
              <template v-if="account">
                <p class="lab">Signed in as</p>
                <p class="hosp">{{ account.hospital }} <span class="demo">{{ account.name }}</span></p>
                <button type="button" class="btn" @click="leave">Sign out</button>
              </template>
              <template v-else>
                <NuxtLink to="/sign-in" class="btn btn-primary">Sign in</NuxtLink>
                <NuxtLink to="/sign-up" class="btn">Create account</NuxtLink>
              </template>
            </template>
            <template v-else>
              <p class="lab">Your hospital</p>
              <p class="hosp">{{ hospital }} <span class="demo">demo data</span></p>
            </template>
          </div>

          <p class="foot">You decide. Crossmatch every unit before use. If the tool is down, use the phone process.</p>
        </nav>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.burger { width: 46px; height: 46px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: #fff; display: grid; place-content: center; gap: 5px; flex-shrink: 0; }
.burger i { display: block; width: 20px; height: 2.5px; border-radius: 99px; background: var(--primary-700); transition: transform 0.25s ease, opacity 0.2s ease; }
.burger.open i:nth-child(1) { transform: translateY(7.5px) rotate(45deg); }
.burger.open i:nth-child(2) { opacity: 0; }
.burger.open i:nth-child(3) { transform: translateY(-7.5px) rotate(-45deg); }
@media (min-width: 900px) { .burger { display: none; } }

.overlay { position: fixed; inset: 0; z-index: 80; background: rgba(59, 10, 14, 0.45); backdrop-filter: blur(4px); }
.sheet { position: absolute; left: 12px; right: 12px; top: 12px; max-height: calc(100dvh - 24px); overflow-y: auto; padding: 16px 16px 20px; border-radius: 34px 38px 34px 40px / 38px 34px 40px 34px; background: linear-gradient(180deg, #fff, #f3f8f7); border: 1.5px solid var(--primary-500); box-shadow: 0 30px 70px rgba(4, 40, 38, 0.4); display: flex; flex-direction: column; gap: 14px; }
.top { display: flex; align-items: center; justify-content: space-between; }
.x { width: 46px; height: 46px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: #fff; display: grid; place-items: center; color: var(--primary-700); transform: rotate(90deg); }
.links { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.link { display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 6px 18px 6px 6px; border-radius: 99px; border: 1.5px solid #d8e4e2; background: #fff; text-decoration: none; color: var(--ink); font-weight: 800; font-size: 16px; }
.link.tool.router-link-active { border-color: var(--primary-500); background: var(--primary-50); }
.lt { display: flex; flex-direction: column; line-height: 1.2; }
.lt small { font-size: 12px; font-weight: 600; color: #5d6d78; margin-top: 2px; }
.acct { padding: 14px 16px; border-radius: 26px; background: var(--primary-50); display: flex; flex-direction: column; gap: 8px; }
.lab { margin: 0; font-size: 11.5px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #5d6d78; }
.hosp { margin: 0; font-size: 16px; font-weight: 800; color: var(--primary-700); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.demo { padding: 3px 10px; border-radius: 99px; background: var(--teal-50); color: var(--teal-600); font-size: 11.5px; }
.foot { margin: 0; text-align: center; font-size: 12px; font-weight: 600; color: var(--slate); line-height: 1.5; }
.sheet-enter-active, .sheet-leave-active { transition: opacity 0.2s ease; }
.sheet-enter-active .sheet, .sheet-leave-active .sheet { transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet, .sheet-leave-to .sheet { transform: translateY(-24px) scale(0.98); }
@media (prefers-reduced-motion: reduce) { .sheet-enter-active .sheet, .sheet-leave-active .sheet { transition: none; } }
</style>
