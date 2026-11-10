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
        <p class="eyebrow rise">Terumo BCT Africa Hackathon 2026</p>
        <h1 class="rise" style="--d: 80ms">Spare blood is already <span>nearby.</span></h1>
        <p class="lead rise" style="--d: 160ms">
          At 1 a.m. the hospital fridge does not have the right type. Type what the patient needs and see every centre and hospital that can spare it, with an honest arrival time.
        </p>
        <div class="chips rise" style="--d: 240ms">
          <NuxtLink to="/request" class="chip"><span class="chip-ico"><AppIcon name="search" :size="20" /></span>Find blood</NuxtLink>
          <NuxtLink to="/results?group=B%2B&units=2&limit=3" class="chip"><span class="chip-ico"><AppIcon name="window" :size="20" /></span>See an example</NuxtLink>
          <a href="#phone" class="chip"><span class="chip-ico"><AppIcon name="sms" :size="20" /></span>Text a request</a>
        </div>
        <NuxtLink to="/request" class="btn btn-primary big rise" style="--d: 320ms"><AppIcon name="drop" :size="22" /> Find blood now</NuxtLink>
      </div>

      <div class="visual rise" style="--d: 200ms">
        <div class="stage"><BloodMosaic /></div>
        <p class="cap">Hospitals share. Nobody runs short.</p>
      </div>
    </section>

    <section class="band" aria-label="Why it matters">
      <ul class="stats">
        <li v-for="s in stats" :key="s.big" class="rise"><strong>{{ s.big }}</strong><span>{{ s.text }}</span></li>
      </ul>
      <p class="fine">Synthetic hackathon dataset, November 2025 to October 2026. Figures replay last year's requests and are exploratory.</p>
    </section>

    <section class="section" aria-labelledby="how">
      <h2 id="how">How it works</h2>
      <ol class="steps">
        <li v-for="(s, i) in steps" :key="s.title" class="organic rise" :style="{ '--d': i * 90 + 'ms' }">
          <span class="chip-ico big-ico"><AppIcon :name="s.icon" :size="26" /></span>
          <span class="num">{{ i + 1 }}</span>
          <h3>{{ s.title }}</h3>
          <p>{{ s.body }}</p>
        </li>
      </ol>
      <div class="callout rise">
        <AppIcon name="warning" :size="26" />
        <p><strong>If the wait is too long, it says so plainly.</strong> The doctor can act now: give emergency group O, or move the patient.</p>
      </div>
    </section>

    <section id="phone" class="section split" aria-labelledby="before">
      <div class="organic pad rise">
        <span class="chip-ico big-ico"><AppIcon name="bell" :size="26" /></span>
        <h2 id="before">Before the emergency</h2>
        <p>Every evening the tool lists hospitals that have run out of the most common blood type, so the blood centre can top them up before the 1 a.m. call.</p>
      </div>
      <div class="organic pad rise" style="--d: 90ms">
        <span class="chip-ico big-ico"><AppIcon name="sms" :size="26" /></span>
        <h2>Works on any phone</h2>
        <p>Requests and confirmations also work by text message. No smartphone and no data needed at the bench. Try: <b>B+ 2 RBC 3H</b></p>
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
      <NuxtLink to="/request" class="btn big"><AppIcon name="drop" :size="22" /> Find blood now</NuxtLink>
    </section>

    <footer class="foot">Blood Dispatch Network · Hackathon prototype · All data is synthetic and does not describe real facilities.</footer>
  </div>
</template>

<style scoped>
.hero { display: grid; gap: 28px; padding: 28px 16px 40px; max-width: 1200px; margin: 0 auto; align-items: center; }
.eyebrow { margin: 0 0 12px; display: inline-block; padding: 6px 14px; border-radius: 99px; border: 1.5px solid var(--blood-500); background: #fff; font-size: 11.5px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--blood-700); }
h1 { margin: 0; font-size: clamp(36px, 7vw, 66px); line-height: 0.98; letter-spacing: -0.03em; font-weight: 800; text-transform: uppercase; color: var(--blood-600); }
h1 span { color: var(--wine); }
.lead { margin: 18px 0 0; font-size: 17px; line-height: 1.55; font-weight: 500; color: #5a3c3f; max-width: 540px; }
.chips { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }
.big { min-height: 58px; padding: 0 28px; font-size: 17px; margin-top: 22px; }
.visual { display: flex; flex-direction: column; gap: 12px; }
.stage { position: relative; border-radius: 44px 44px 36px 36px; padding: 36px 0 0; overflow: hidden; background: linear-gradient(180deg, #fff 0%, #fbe6e3 55%, #f3c6c0 100%); border: 1px solid var(--line); box-shadow: 0 24px 60px rgba(126, 16, 21, 0.18); }
.cap { margin: 0; text-align: center; font-weight: 800; font-size: 14px; color: var(--blood-700); }

.band { background: linear-gradient(180deg, var(--wine), #2a0709); color: #fff; padding: 40px 16px 28px; }
.stats { list-style: none; margin: 0 auto; padding: 0; max-width: 1200px; display: grid; gap: 26px; }
.stats strong { display: block; font-size: 44px; line-height: 1; letter-spacing: -0.02em; font-weight: 800; color: #ff9a92; }
.stats span { display: block; margin-top: 8px; font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #f2d5d2; max-width: 340px; }
.fine { max-width: 1200px; margin: 24px auto 0; font-size: 12px; font-weight: 600; color: #c9a2a0; }

.section { max-width: 1200px; margin: 0 auto; padding: 48px 16px 0; }
.section h2 { margin: 0 0 20px; font-size: 30px; letter-spacing: -0.02em; font-weight: 800; text-transform: uppercase; color: var(--blood-600); }
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; }
.steps li { position: relative; padding: 22px; transition: transform 0.25s ease; }
.steps li:hover { transform: translateY(-4px) rotate(-0.4deg); }
.steps h3 { margin: 14px 0 6px; font-size: 17px; font-weight: 800; }
.steps p, .pad p { margin: 0; font-size: 14.5px; line-height: 1.55; font-weight: 500; color: #5a3c3f; }
.big-ico { width: 52px; height: 52px; }
.num { position: absolute; top: 20px; right: 22px; font-size: 14px; font-weight: 800; color: var(--blood-500); }
.callout { display: flex; gap: 14px; align-items: flex-start; margin-top: 16px; padding: 18px 20px; background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: 26px; color: var(--amber-900); }
.callout svg { flex-shrink: 0; color: var(--amber-700); }
.callout p { margin: 0; font-size: 15px; line-height: 1.5; font-weight: 600; }
.split { display: grid; gap: 16px; }
.pad { padding: 24px; }
.pad h2 { margin: 14px 0 8px; font-size: 24px; }
.safety ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.safety li { display: flex; gap: 12px; align-items: flex-start; font-size: 15.5px; line-height: 1.5; font-weight: 600; }
.safety li svg { color: var(--teal-600); flex-shrink: 0; margin-top: 2px; }
.final { margin-top: 52px; padding: 56px 16px; background: radial-gradient(600px 240px at 50% 0%, #cf2a30, var(--blood-600)); color: #fff; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 22px; }
.final h2 { margin: 0; font-size: clamp(26px, 4.5vw, 40px); letter-spacing: -0.02em; text-transform: uppercase; }
.final .btn { background: #fff; color: var(--blood-700); border-color: #fff; margin-top: 0; }
.foot { padding: 20px 16px 28px; text-align: center; font-size: 12px; font-weight: 600; color: var(--slate); }

@media (min-width: 900px) {
  .hero { grid-template-columns: 1.1fr 0.9fr; gap: 64px; padding: 64px 24px 80px; }
  .stats { grid-template-columns: repeat(3, 1fr); gap: 48px; }
  .steps { grid-template-columns: repeat(4, 1fr); }
  .split { grid-template-columns: 1fr 1fr; }
  .section, .band { padding-left: 24px; padding-right: 24px; }
}
</style>
