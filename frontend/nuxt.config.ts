import { fileURLToPath } from 'node:url'

// Two build modes:
//  - normal (dev / server): Clerk on (keyless in dev), SSR.
//  - GH_PAGES=1: static SPA for GitHub Pages under a base path. Clerk is only included when a
//    publishable key is provided at build time; otherwise the app runs in open demo mode.
const pages = !!process.env.GH_PAGES
const base = process.env.NUXT_APP_BASE_URL || '/'
const clerkOn = process.env.DEMO_AUTH ? false : pages ? !!process.env.NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY : true
// scripts/deploy-pages.sh always sets NUXT_PUBLIC_API_BASE (empty unless the shell gives one), so
// the localhost API in a developer's frontend/.env never reaches the Pages build.
const apiBase = process.env.NUXT_PUBLIC_API_BASE ?? (pages ? '' : 'http://localhost:5001')
// No API: the static demo. Decided at build time, so a server built with an API and started with
// NUXT_PUBLIC_API_BASE='' has no results files to show; build it without the API instead.
const staticDemo = apiBase === ''

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
  nitro: {
    ...(pages ? { preset: 'github-pages' } : {}),
    // Only the static demo serves the committed DS2 results (aggregate, synthetic) at
    // <baseURL>results-data/, for its evidence and pre-alert pages. With an API they come from
    // the API, and the pre-alert list (prealerts.json) stays behind its sign-in. Nothing reads
    // arrival_model.json, which the API does not serve either.
    ...(staticDemo
      ? {
          publicAssets: [{ dir: fileURLToPath(new URL('../results', import.meta.url)), baseURL: '/results-data', maxAge: 0 }],
          ignore: ['**/arrival_model.json']
        }
      : {})
  },
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      apiBase,
      authEnabled: clerkOn,
      // Static demo with no Clerk: anyone can make a local account for their hospital.
      demoAuth: !clerkOn && (pages || !!process.env.DEMO_AUTH)
    }
  },
  app: {
    baseURL: base,
    pageTransition: { name: 'page', mode: 'out-in' },
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
