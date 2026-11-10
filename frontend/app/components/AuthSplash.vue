<script setup lang="ts">
withDefaults(defineProps<{ title: string; sub: string; cta?: string }>(), { cta: 'Login' })
const img = useImg()
</script>

<template>
  <div class="wrap">
    <section class="art">
      <NuxtLink to="/" class="brand" aria-label="Blood Dispatch home"><BrandLogo :size="34" /></NuxtLink>
      <div class="txt">
        <h1>{{ title }}</h1>
        <p class="sub">{{ sub }}</p>
        <span class="dots" aria-hidden="true"><i /></span>
      </div>
      <div class="stage">
        <div class="photo"><img :src="img('hand-tube.jpg')" alt="A gloved hand holding a tube of blood"></div>
        <BlockWall class="wall" :max="10" :mobile-gap="1" :desktop-gap="3" />
      </div>
      <a href="#form" class="pill">{{ cta }}</a>
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
.art { position: relative; min-height: min(100dvh, 620px); display: flex; flex-direction: column; overflow: hidden; background: linear-gradient(180deg, #fff 0%, #fdf1ef 45%, #f6d3ce 100%); }
.brand { text-decoration: none; display: inline-flex; margin: 24px 24px 0; align-self: flex-start; position: relative; z-index: 6; }
.txt { position: relative; z-index: 6; padding: 22px 24px 0; }
h1 { margin: 0; font-size: 10vw; line-height: 1; letter-spacing: -0.03em; font-weight: 800; text-transform: uppercase; color: #a3151b; white-space: pre-line; }
.sub { margin: 14px 0 0; font-size: 17px; font-weight: 500; color: #1b1b1f; }
.dots { display: block; width: 40px; height: 11px; border: 2px solid var(--blood-500); border-radius: 99px; margin-top: 18px; position: relative; box-sizing: border-box; }
.dots i { position: absolute; left: 2px; top: 2px; width: 22px; height: 4px; border-radius: 99px; background: var(--blood-500); animation: slide 2.4s ease-in-out infinite alternate; }
@keyframes slide { to { transform: translateX(8px); } }
.stage { position: relative; flex: 1; min-height: 340px; margin-top: 8px; }
.photo { position: absolute; left: 0; right: 0; bottom: 0; height: 600px; max-height: 100%; overflow: hidden; z-index: 2; background: linear-gradient(180deg, #f9d5d0 0%, #e58d86 45%, #b3171e 100%); -webkit-mask-image: linear-gradient(180deg, transparent 0%, #000 22%, #000 78%, transparent 100%); mask-image: linear-gradient(180deg, transparent 0%, #000 22%, #000 78%, transparent 100%); }
.photo img { position: absolute; width: 164%; left: -28%; top: -15%; max-width: none; height: auto; filter: grayscale(1) contrast(1.3) brightness(1.18); mix-blend-mode: multiply; }
.wall { position: absolute; left: 0; right: 0; bottom: 0; z-index: 4; }
.pill { position: absolute; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 7; min-width: 220px; text-align: center; padding: 17px 28px; border-radius: 99px; background: #fdecea; color: var(--blood-700); font-weight: 800; font-size: 18px; text-decoration: none; box-shadow: 0 14px 28px rgba(60, 5, 10, 0.4); }
.panel { padding: 28px 16px 40px; display: flex; justify-content: center; position: relative; z-index: 1; }
.card-in { width: 100%; max-width: 440px; background: linear-gradient(180deg, #fff 0%, #fdf0ee 100%); border: 1.5px solid var(--blood-500); border-radius: 40px 50px 42px 52px / 48px 40px 52px 42px; padding: 30px 24px 22px; box-shadow: 0 30px 70px rgba(126, 16, 21, 0.18); }
.safe { margin: 16px 0 0; text-align: center; font-size: 12px; font-weight: 600; color: var(--slate); }
@media (min-width: 900px) {
  .wrap { grid-template-columns: 1.1fr 1fr; }
  h1 { font-size: clamp(44px, 5.4vw, 78px); }
  .brand { margin: 40px 0 0 64px; }
  .txt { padding: 56px 64px 0; }
  .sub { font-size: 22px; margin-top: 22px; }
  .art { min-height: 100dvh; }
  .stage { min-height: 520px; }
  .photo { height: 520px; }
  .photo img { width: 97.5%; left: 18.75%; top: -21%; }
  .pill { display: none; }
  .panel { align-items: center; padding: 40px; }
  .card-in { padding: 40px 38px 30px; }
}
</style>
