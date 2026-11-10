export default defineNuxtConfig({
  compatibilityDate: '2026-11-10',
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:5001'
    }
  },
  app: {
    head: {
      htmlAttrs: { lang: 'en' },
      title: 'Blood Dispatch',
      meta: [{ name: 'theme-color', content: '#b3171e' }, { name: 'description', content: 'Find spare compatible blood nearby with honest arrival windows.' }],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&display=swap' }
      ]
    }
  }
})
