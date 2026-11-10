// v-inview: fades and lifts an element in the first time it scrolls into view.
// Content stays visible without JS or with reduced motion (the hidden state is only added here).
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.directive('inview', {
    mounted(el: HTMLElement, binding) {
      if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return
      el.style.setProperty('--iv-d', `${Number(binding.value) || 0}ms`)
      el.classList.add('iv')
      const io = new IntersectionObserver(([e]) => {
        if (e?.isIntersecting) { el.classList.add('iv-in'); io.disconnect() }
      }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' })
      io.observe(el)
    },
    getSSRProps() { return {} }
  })
})
