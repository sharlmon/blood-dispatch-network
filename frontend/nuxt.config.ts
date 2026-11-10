// Two build modes:
//  - normal (dev / server): Clerk on (keyless in dev), SSR.
//  - GH_PAGES=1: static SPA for GitHub Pages under a base path. Clerk is only included when a
//    publishable key is provided at build time; otherwise the app runs in open demo mode.
const pages = !!process.env.GH_PAGES
const base = process.env.NUXT_APP_BASE_URL || '/'
const clerkOn = pages ? !!process.env.NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY : true
const apiBase = process.env.NUXT_PUBLIC_API_BASE ?? (pages ? '' : 'http://localhost:5001')

export default defineNuxtConfig({
  compatibilityDate: '2026-11-10',
  ssr: !pages,
  modules: clerkOn ? ['@clerk/nuxt'] : [],
  clerk: {
    signInUrl: `${base}sign-in`,
    signUpUrl: `${base}sign-up`,
    signInFallbackRedirectUrl: `${base}onboarding`,
    signUpFallbackRedirectUrl: `${base}onboarding`
  },
  nitro: pages ? { preset: 'github-pages' } : {},
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      apiBase,
      authEnabled: clerkOn
    }
  },
  app: {
    baseURL: base,
    head: {
      htmlAttrs: { lang: 'en' },
      title: 'Blood Dispatch',
      meta: [{ name: 'theme-color', content: '#b3171e' }, { name: 'description', content: 'Find spare compatible blood nearby with honest arrival windows.' }],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: `${base}favicon.svg` },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Caveat:wght@600;700&display=swap' }
      ]
    }
  }
})
