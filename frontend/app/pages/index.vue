<script setup lang="ts">
useHead({ title: 'Blood Dispatch · Find spare blood nearby' })

const demo = mockRank({ id: '#demo', group: 'B+', units: 2, product: 'Red cells', limitH: 3, openedAt: '01:04' }).options
const selected = demo[0]!.id

const steps = [
  { icon: 'edit', title: 'Type what the patient needs', body: 'Blood group, units and the longest the patient can wait. On a computer, or by text message from a basic phone.' },
  { icon: 'units', title: 'See who can spare it', body: 'Every nearby centre and hospital with compatible blood. A hospital only shares what it can spare, so it never leaves itself short.' },
  { icon: 'window', title: 'Read an honest arrival time', body: 'Not one number, a range: most likely 2½ h, almost certainly between 2 and 3½ h.' },
  { icon: 'confirmed', title: 'Pick one, the shelf is checked', body: 'The supplier confirms the bags are really on the shelf, then sends them. No answer in 10 minutes, we move to the next source.' }
]
const stats = [
  { big: '1 in 4', text: 'emergency patients whose hospital fridge fell short got no blood at all.' },
  { big: '0 of 5,330', text: 'emergency transfers came from another hospital. Hospitals never share today.' },
  { big: '~2 h', text: 'sooner on average, replaying last year\'s requests with the tool.' }
]
const safety = [
  'A person makes every decision. The tool suggests, people approve.',
  'The tool never decides blood group. Unknown group means group O only.',
  'A trained lab worker crossmatches and checks every bag before use.',
  'If the tool breaks, everyone falls back to the phone process.'
]
</script>

<template>
  <div class="landing">
    <section class="hero">
      <div class="copy">
        <p class="eyebrow">Terumo BCT Africa Hackathon 2026</p>
        <h1>Find spare blood nearby, with an honest arrival time.</h1>
        <p class="lead">
          It is 1 a.m. and the hospital fridge does not have the right type. Type what the patient needs and see every centre and hospital that can spare compatible blood, and how long each will really take.
        </p>
        <div class="cta">
          <NuxtLink to="/request" class="btn btn-primary"><AppIcon name="search" /> Find blood now</NuxtLink>
          <NuxtLink to="/results?group=B%2B&units=2&limit=3" class="btn">See an example</NuxtLink>
        </div>
        <p class="sms"><AppIcon name="sms" :size="20" /> No data? Text <b>B+ 2 RBC 3H</b> to [SHORTCODE].</p>
      </div>

      <div class="visual" aria-hidden="true">
        <SourceMap :options="demo" :selected-id="selected" :pad-top="90" :pad-bottom="130" :pad-x="40" :max-zoom="1.6" />
        <div class="float">
          <small>Fastest option</small>
          <strong>Lakeview District Hospital</strong>
          <span class="tnum">1½ h · almost certainly 1 to 2¼ h</span>
        </div>
      </div>
    </section>

    <section class="band" aria-label="Why it matters">
      <ul class="stats">
        <li v-for="s in stats" :key="s.big"><strong>{{ s.big }}</strong><span>{{ s.text }}</span></li>
      </ul>
      <p class="fine">Synthetic hackathon dataset, November 2025 to October 2026. Figures replay last year's requests and are exploratory.</p>
    </section>

    <section class="section" aria-labelledby="how">
      <h2 id="how">How it works</h2>
      <ol class="steps">
        <li v-for="(s, i) in steps" :key="s.title">
          <span class="ico"><AppIcon :name="s.icon" :size="26" /></span>
          <span class="num">{{ i + 1 }}</span>
          <h3>{{ s.title }}</h3>
          <p>{{ s.body }}</p>
        </li>
      </ol>
      <div class="callout">
        <AppIcon name="warning" :size="26" />
        <p><strong>If the wait is too long, it says so plainly.</strong> The doctor can act now: give emergency group O, or move the patient.</p>
      </div>
    </section>

    <section class="section split" aria-labelledby="before">
      <div class="card pad">
        <span class="ico"><AppIcon name="bell" :size="26" /></span>
        <h2 id="before">Before the emergency</h2>
        <p>Every evening the tool lists hospitals that have run out of the most common blood type, so the blood centre can top them up before the 1 a.m. call.</p>
      </div>
      <div class="card pad">
        <span class="ico"><AppIcon name="sms" :size="26" /></span>
        <h2>Works on any phone</h2>
        <p>Requests and confirmations also work by text message. No smartphone and no data needed at the bench.</p>
      </div>
    </section>

    <section class="section safety" aria-labelledby="safe">
      <h2 id="safe">Built to be safe</h2>
      <ul>
        <li v-for="t in safety" :key="t"><AppIcon name="check" :size="20" />{{ t }}</li>
      </ul>
    </section>

    <section class="final">
      <h2>Ready when the next request comes in.</h2>
      <NuxtLink to="/request" class="btn btn-primary"><AppIcon name="search" /> Find blood now</NuxtLink>
    </section>

    <footer class="foot">Blood Dispatch Network · Hackathon prototype · All data is synthetic and does not describe real facilities.</footer>
  </div>
</template>

<style scoped>
.landing { background: var(--paper); }
.hero { display: grid; gap: 28px; padding: 28px 16px 36px; max-width: 1200px; margin: 0 auto; align-items: center; }
.eyebrow { margin: 0 0 10px; font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--blood-700); }
h1 { margin: 0; font-size: clamp(32px, 6vw, 52px); line-height: 1.05; letter-spacing: -0.025em; font-weight: 800; }
.lead { margin: 16px 0 0; font-size: 17px; line-height: 1.55; font-weight: 500; color: var(--slate); max-width: 560px; }
.cta { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.cta .btn { min-height: 54px; font-size: 16px; }
.sms { display: flex; align-items: center; gap: 10px; margin: 18px 0 0; font-size: 14px; font-weight: 600; color: var(--azure-600); }
.sms b { color: var(--ink); }
.visual { position: relative; height: 340px; border-radius: 24px; overflow: hidden; border: 1px solid var(--line); box-shadow: 0 18px 50px rgba(18, 32, 43, 0.14); }
.float { position: absolute; left: 14px; right: 14px; bottom: 14px; background: var(--white); border-radius: 16px; padding: 12px 16px; display: flex; flex-direction: column; gap: 2px; box-shadow: var(--shadow-float); }
.float small { font-size: 11px; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; color: var(--slate); }
.float strong { font-size: 16px; }
.float span { font-size: 13px; font-weight: 700; color: var(--teal-600); }

.band { background: var(--ink); color: #fff; padding: 36px 16px 28px; }
.stats { list-style: none; margin: 0 auto; padding: 0; max-width: 1200px; display: grid; gap: 24px; }
.stats strong { display: block; font-size: 40px; line-height: 1; letter-spacing: -0.02em; font-weight: 800; }
.stats span { display: block; margin-top: 8px; font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #c9d3da; max-width: 340px; }
.fine { max-width: 1200px; margin: 24px auto 0; font-size: 12px; font-weight: 600; color: #9fb0bd; }

.section { max-width: 1200px; margin: 0 auto; padding: 44px 16px 0; }
.section h2 { margin: 0 0 20px; font-size: 28px; letter-spacing: -0.015em; font-weight: 800; }
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.steps li { position: relative; background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg); padding: 20px; }
.steps h3 { margin: 14px 0 6px; font-size: 17px; font-weight: 800; }
.steps p, .pad p { margin: 0; font-size: 14.5px; line-height: 1.55; font-weight: 500; color: var(--slate); }
.ico { width: 48px; height: 48px; border-radius: 14px; background: var(--blood-50); color: var(--blood-700); display: grid; place-items: center; }
.num { position: absolute; top: 20px; right: 20px; font-size: 13px; font-weight: 800; color: var(--slate); }
.callout { display: flex; gap: 14px; align-items: flex-start; margin-top: 14px; padding: 18px 20px; background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: var(--radius-lg); color: var(--amber-900); }
.callout svg { flex-shrink: 0; color: var(--amber-700); }
.callout p { margin: 0; font-size: 15px; line-height: 1.5; font-weight: 600; }
.split { display: grid; gap: 14px; }
.pad { padding: 22px; }
.pad h2 { margin: 14px 0 8px; font-size: 22px; }
.safety ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.safety li { display: flex; gap: 12px; align-items: flex-start; font-size: 15.5px; line-height: 1.5; font-weight: 600; }
.safety li svg { color: var(--teal-600); flex-shrink: 0; margin-top: 2px; }
.final { margin-top: 48px; padding: 48px 16px; background: var(--blood-500); color: #fff; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 20px; }
.final h2 { margin: 0; font-size: clamp(24px, 4vw, 34px); letter-spacing: -0.015em; }
.final .btn { background: #fff; color: var(--blood-700); border-color: #fff; min-height: 54px; font-size: 16px; }
.foot { padding: 20px 16px; text-align: center; font-size: 12px; font-weight: 600; color: var(--slate); }

@media (min-width: 900px) {
  .hero { grid-template-columns: 1.05fr 1fr; gap: 56px; padding: 64px 24px 72px; }
  .visual { height: 460px; }
  .stats { grid-template-columns: repeat(3, 1fr); gap: 48px; }
  .steps { grid-template-columns: repeat(4, 1fr); }
  .split { grid-template-columns: 1fr 1fr; }
  .section, .band { padding-left: 24px; padding-right: 24px; }
}
</style>
