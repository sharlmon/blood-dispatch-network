<script setup lang="ts">
defineProps<{ title: string; sub: string }>()
</script>

<template>
  <div class="wrap">
    <section class="art">
      <NuxtLink to="/" class="brand" aria-label="Blood Dispatch home"><BrandLogo :size="34" /></NuxtLink>
      <h1>{{ title }}</h1>
      <p class="sub">{{ sub }}</p>
      <span class="dots" aria-hidden="true"><i /></span>
      <div class="hands"><SplashHands /></div>
      <a href="#form" class="pill">Login</a>
    </section>

    <section id="form" class="panel">
      <div class="card-in">
        <slot />
        <p class="safe">Every action is recorded in the audit log. A person approves every request.</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.wrap { min-height: 100dvh; display: grid; }
.art { position: relative; padding: 22px 20px 0; display: flex; flex-direction: column; background: linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(251, 230, 227, 0.4) 100%); }
.brand { text-decoration: none; display: inline-flex; margin-bottom: 26px; }
h1 { margin: 0; font-size: clamp(34px, 8vw, 56px); line-height: 1; letter-spacing: -0.02em; font-weight: 800; text-transform: uppercase; color: var(--blood-600); max-width: 560px; }
.sub { margin: 12px 0 0; font-size: 18px; font-weight: 500; color: #3b0a0e; }
.dots { display: block; width: 38px; height: 10px; border: 2px solid var(--blood-500); border-radius: 99px; margin: 18px 0 8px; position: relative; }
.dots i { position: absolute; left: 2px; top: 1px; width: 22px; height: 4px; border-radius: 99px; background: var(--blood-500); animation: slide 2.4s ease-in-out infinite alternate; }
@keyframes slide { to { transform: translateX(8px); } }
.hands { margin: 8px -20px 0; }
.pill { position: absolute; left: 50%; bottom: 22px; transform: translateX(-50%); min-width: 220px; text-align: center; padding: 16px 28px; border-radius: 99px; background: #fdecea; color: var(--blood-700); font-weight: 800; font-size: 17px; text-decoration: none; box-shadow: 0 10px 24px rgba(126, 16, 21, 0.3); }
.panel { padding: 28px 16px 40px; display: flex; justify-content: center; }
.card-in { width: 100%; max-width: 440px; background: rgba(255, 255, 255, 0.9); border: 1.5px solid var(--blood-500); border-radius: 30px 38px 32px 40px / 36px 30px 40px 32px; padding: 28px 22px 22px; backdrop-filter: blur(6px); box-shadow: 0 24px 60px rgba(126, 16, 21, 0.14); }
.safe { margin: 16px 0 0; text-align: center; font-size: 12px; font-weight: 600; color: var(--slate); }
@media (min-width: 900px) {
  .wrap { grid-template-columns: 1.1fr 1fr; }
  .art { padding: 32px 48px 0; min-height: 100dvh; }
  .pill { display: none; }
  .panel { align-items: center; padding: 40px; }
  .hands { margin: auto -48px 0; }
}
</style>
