<script setup lang="ts">
useHead({ title: 'Blood Dispatch · Find spare blood nearby' })

const demo = mockRank({ id: '#demo', group: 'B+', units: 2, product: 'Red cells', limitH: 3, openedAt: '01:04' }).options
const selected = demo[0]!.id

const stats = [
  { c: { to: 28, suffix: '%' }, text: 'of emergencies hit a hospital fridge that fell short.' },
  { c: { to: 617 }, text: 'red cell emergencies got no blood at all.' },
  { c: { to: 2, prefix: '~', suffix: 'h' }, text: 'sooner on average when last year\'s requests are replayed with the tool.' }
]
const steps = [
  { icon: 'pen', title: 'Type what the patient needs', body: 'Blood group, units and the longest the patient can wait. On a computer, or by text message from a basic phone.' },
  { icon: 'bag', title: 'See who can spare it', body: 'Every nearby centre and hospital with compatible blood. A hospital only shares what it can spare, so it never leaves itself short.' },
  { icon: 'window', title: 'Read an honest arrival time', body: 'Not one number, a range: most likely 2½ h, almost certainly between 2 and 3½ h.' },
  { icon: 'confirm', title: 'Pick one, the shelf is checked', body: 'The supplier confirms the bags are really on the shelf, then sends them. No answer in 10 minutes, we move to the next source.' }
]
const roles = [
  { icon: 'pen', who: 'Lab worker', at: 'Requesting hospital', body: 'Types the need, reads the ranked sources and their windows, and picks one.' },
  { icon: 'confirm', who: 'Supplying site', at: 'Centre or hospital', body: 'Confirms the units are really on the shelf, then dispatches.' },
  { icon: 'ambulance', who: 'Clinician', at: 'At the bedside', body: 'Is told plainly if the wait is too long, and chooses emergency group O or a transfer.' },
  { icon: 'bell', who: 'Regional centre staff', at: 'Every evening', body: 'Gets the list of hospitals out of the most common blood type, to top up first.' }
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
      <div class="bgimg" aria-hidden="true"><Pic class="bgblur" name="hero" small /><Pic class="main" name="hero" sizes="100vw" eager /></div>
      <div class="copy">
        <h1 class="rise" style="--d: 80ms">Spare blood<br>is already<br><span>nearby.</span></h1>
        <p class="lead rise" style="--d: 160ms">At 1 a.m. the hospital fridge does not have the right type. See every centre and hospital that can spare it, and when it will really arrive.</p>
        <div class="chips chips-d rise" style="--d: 240ms">
          <NuxtLink to="/request" class="chip"><span class="chip-ico"><ServiceIcon name="find" :size="30" /></span>Find blood</NuxtLink>
          <NuxtLink to="/results?group=B%2B&units=2&limit=3&demo=1" class="chip"><span class="chip-ico"><ServiceIcon name="window" :size="30" /></span>See an example</NuxtLink>
          <a href="#phone" class="chip"><span class="chip-ico"><ServiceIcon name="sms" :size="30" /></span>Text a request</a>
        </div>
        <div class="cta-m rise" style="--d: 240ms">
          <NuxtLink to="/request" class="btn btn-primary">Find blood now</NuxtLink>
          <a href="#phone" class="chip"><span class="chip-ico"><ServiceIcon name="sms" :size="26" /></span>By SMS</a>
        </div>
      </div>

      <NetworkHorizon class="wall" />
    </section>

    <section v-inview id="data" class="band" aria-labelledby="why">
      <div class="inner">
        <h2 id="why">The gap, in the data</h2>
        <p class="sub">Last year's requests, from the synthetic hackathon dataset.</p>
        <ul class="stats">
          <li v-for="(st, i) in stats" :key="st.text" class="rise" :style="{ '--d': i * 70 + 'ms' }"><strong><CountUp v-bind="st.c" /></strong><span>{{ st.text }}</span></li>
        </ul>
      </div>
    </section>

    <section v-inview class="section" aria-labelledby="share">
      <div class="share">
        <div class="photo-card organic"><Pic name="blood-draw" sizes="(min-width: 900px) 520px, 92vw" alt="A health worker in a lab drawing blood from a patient" /><span class="pc-tag">Hospitals share. Nobody runs short.</span></div>
        <div class="share-copy">
          <h2 id="share">Hospitals have never shared. Now they can.</h2>
          <p>A hospital 30 minutes down the road often has spare bags of exactly the type you need. Nobody knows, because nobody can see.</p>
          <ul>
            <li><ServiceIcon name="bag" :size="26" /> Hospitals share only what they can spare.</li>
            <li><ServiceIcon name="confirm" :size="26" /> The supplier confirms the shelf before anything moves.</li>
            <li><ServiceIcon name="ambulance" :size="26" /> If the wait is too long, the doctor is told plainly.</li>
          </ul>
        </div>
      </div>
    </section>

    <section v-inview class="section" aria-labelledby="how">
      <h2 id="how">How it works</h2>
      <ol class="steps">
        <li v-for="(st, i) in steps" :key="st.title" class="organic rise" :style="{ '--d': i * 90 + 'ms' }">
          <IconBadge size="lg"><ServiceIcon :name="st.icon" :size="36" /></IconBadge>
          <span class="num">{{ i + 1 }}</span>
          <h3>{{ st.title }}</h3>
          <p>{{ st.body }}</p>
        </li>
      </ol>
    </section>

    <section v-inview class="section" aria-labelledby="example">
      <h2 id="example">One request, in a minute</h2>
      <ExampleStory :options="demo" :limit="3" group="B+" :units="2" product="Red cells" hospital="Hillside Hospital" />
    </section>

    <section v-inview id="phone" class="section" aria-labelledby="roles">
      <h2 id="roles">Who uses it</h2>
      <ul class="roles">
        <li v-for="(r, i) in roles" :key="r.who" class="organic rise" :style="{ '--d': i * 80 + 'ms' }">
          <IconBadge size="lg"><ServiceIcon :name="r.icon" :size="36" /></IconBadge>
          <h3>{{ r.who }}</h3>
          <small>{{ r.at }}</small>
          <p>{{ r.body }}</p>
        </li>
      </ul>
      <div class="gallery">
        <figure class="organic"><Pic name="blood-bags" sizes="(min-width: 900px) 380px, 31vw" alt="Three bags of donated blood, labelled A and B" /><figcaption>On the shelf</figcaption></figure>
        <figure class="organic"><Pic name="paramedics" sizes="(min-width: 900px) 380px, 31vw" alt="Paramedics caring for a patient inside an ambulance" /><figcaption>In transit</figcaption></figure>
        <figure class="organic"><Pic name="care-team" sizes="(min-width: 900px) 380px, 31vw" alt="Four nurses in blue uniforms and headscarves posing together" /><figcaption>At the bedside</figcaption></figure>
      </div>
      <div class="sms-card organic">
        <IconBadge size="lg"><ServiceIcon name="sms" :size="36" /></IconBadge>
        <div>
          <h3>Works on any phone</h3>
          <p>Requests and confirmations also work by text message. No smartphone and no data needed at the bench.</p>
        </div>
        <div class="bubbles" aria-hidden="true"><span class="out">B+ 2 RBC 3H</span><span class="in">3 sources. Fastest Lakeview 1.5h (1-2.25h). Reply 1 to request.</span></div>
      </div>
    </section>

    <section v-inview id="safe" class="section" aria-labelledby="safe-h">
      <h2 id="safe-h">Built to be safe</h2>
      <ul class="safety">
        <li v-for="t in safety" :key="t"><AppIcon name="check" :size="20" />{{ t }}</li>
      </ul>
    </section>

    <SiteFooter />
  </div>
</template>

<style scoped>
.hero { position: relative; overflow: hidden; padding: 14px 20px 120px; min-height: max(640px, calc(100svh - var(--header-h))); }
.bgimg { position: absolute; inset: 0; z-index: 0; }
.bgimg img { position: absolute; left: 0; width: 100%; object-fit: cover; }
/* Phone: a soft blurred copy fills the whole hero, the sharp photo sits lower so the faces clear the headline. */
.bgimg .bgblur { top: -30px; left: -30px; width: calc(100% + 60px); height: calc(100% + 60px); object-position: 60% 40%; filter: blur(28px) saturate(1.1); opacity: 0.75; }
.bgimg .main { top: 36%; height: 64%; object-position: 76% 30%; filter: saturate(1.05) contrast(1.02); -webkit-mask-image: linear-gradient(180deg, transparent 0%, #000 34%); mask-image: linear-gradient(180deg, transparent 0%, #000 34%); }
.bgimg::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(244, 248, 247, 0.94) 0%, rgba(244, 248, 247, 0.85) 36%, rgba(244, 248, 247, 0.3) 52%, rgba(244, 248, 247, 0) 66%, rgba(10, 107, 98, 0.16) 100%); }
.copy { position: relative; z-index: 4; max-width: 720px; }
.eyebrow { margin: 0; display: inline-block; padding: 7px 14px; border-radius: 99px; border: 1.5px solid var(--primary-500); background: #fff; font-size: 11px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--primary-700); }
h1 { margin: 16px 0 0; font-size: clamp(46px, 6.1vw, 88px); line-height: 0.94; letter-spacing: -0.035em; font-weight: 800; text-transform: uppercase; color: var(--ink-deep); }
h1 span { color: var(--primary-500); }
.lead { margin: 16px 0 0; font-size: clamp(15.5px, 1.35vw, 19px); line-height: 1.55; font-weight: 500; color: #44545f; max-width: 520px; }
.chips { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 26px; }
.chips-d { display: none; }
.cta-m { display: flex; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
.cta-m .btn { min-height: 54px; padding: 0 26px; font-size: 16px; }
.stage { position: relative; width: 214px; height: 330px; margin: 14px 0 0 auto; --iw: 187%; --il: -70%; --it: -65%; }
.arch { position: absolute; z-index: 3; inset: 0; border-radius: 107px 107px 28px 28px; overflow: hidden; background: linear-gradient(180deg, #eaf3f1, #cfe4e1); box-shadow: 0 20px 44px rgba(6, 74, 68, 0.22); }
.arch img { position: absolute; width: var(--iw); left: var(--il); top: var(--it); max-width: none; height: auto; filter: saturate(1.05) contrast(1.02); }
.tint { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(250, 205, 200, 0.6) 0%, rgba(207, 228, 225, 0.2) 55%, rgba(10, 107, 98, 0.22) 100%); }
.fcard { position: absolute; z-index: 6; left: -136px; top: 150px; width: 206px; padding: 12px 14px 14px; border-radius: 22px; background: rgba(255, 255, 255, 0.95); border: 1px solid #d8e4e2; box-shadow: 0 14px 30px rgba(6, 74, 68, 0.2); display: flex; flex-direction: column; gap: 3px; }
.fcard small { font-size: 9.5px; font-weight: 800; letter-spacing: 0.1em; color: var(--slate); white-space: nowrap; }
.fcard strong { font-size: 13.5px; color: #12202b; white-space: nowrap; }
.ft { display: flex; align-items: baseline; gap: 6px; margin: 2px 0 8px; }
.ft b { font-size: 30px; line-height: 1; color: var(--primary-500); white-space: nowrap; flex-shrink: 0; }
.ft > span { font-size: 11px; font-weight: 700; color: var(--slate); white-space: nowrap; }
.fchip, .fmini { display: none; }
.wall { position: absolute; left: 0; right: 0; bottom: 0; z-index: 5; }
.ln { width: 30px; height: 30px; border-radius: 99px; background: var(--slate); color: #fff; font-size: 13px; font-weight: 800; display: grid; place-items: center; flex-shrink: 0; }
.cap { margin: 0; text-align: center; font-weight: 800; font-size: 14px; color: var(--primary-700); }

.band { background: linear-gradient(180deg, var(--ink-deep), #071c22); color: #fff; padding: 44px 16px 40px; }
.inner { max-width: 1200px; margin: 0 auto; }
.band h2 { margin: 0; font-size: 30px; letter-spacing: -0.02em; font-weight: 800; text-transform: uppercase; color: #fff; }
.sub { margin: 8px 0 28px; font-size: 14px; font-weight: 600; color: #d9b3b0; }
.stats { list-style: none; margin: 0; padding: 0; display: grid; gap: 22px; }
.stats li > strong { display: block; font-size: 42px; line-height: 1; letter-spacing: -0.02em; font-weight: 800; color: #7fd6c9; }
.stats li > span { display: block; margin-top: 8px; font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #d4e8e5; max-width: 340px; }

.section { max-width: 1200px; margin: 0 auto; padding: 52px 16px 0; }
.section h2 { margin: 0 0 22px; font-size: 30px; letter-spacing: -0.02em; font-weight: 800; text-transform: uppercase; color: var(--ink-deep); }
h3 { margin: 0; font-size: 17px; font-weight: 800; }

.share { display: grid; gap: 24px; align-items: center; }
.photo-card { position: relative; overflow: hidden; aspect-ratio: 4 / 3; background: linear-gradient(180deg, #d6e8e5 0%, #8fc7bf 45%, #0a6b62 100%); }
.photo-card img { width: 100%; height: 100%; object-fit: cover; object-position: 50% 30%; filter: saturate(1.05) contrast(1.02); }
.pc-tag { position: absolute; left: 16px; bottom: 16px; padding: 9px 16px; border-radius: 99px; background: #e4f2f0; color: var(--primary-700); font-weight: 800; font-size: 14px; box-shadow: 0 10px 22px rgba(4, 40, 38, 0.3); }
.share-copy h2 { margin-bottom: 14px; }
.share-copy p { margin: 0 0 16px; font-size: 16px; line-height: 1.6; font-weight: 500; color: #44545f; }
.share-copy ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.share-copy li { display: flex; align-items: center; gap: 12px; font-size: 15px; font-weight: 700; }
.charts { display: grid; gap: 16px; }
.chart { padding: 24px; }
.chart h3 { margin-bottom: 18px; }
.bar-row { margin-bottom: 16px; }
.bl { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; font-weight: 700; margin-bottom: 6px; }
.bl b { font-size: 16px; }
.bt { height: 16px; border-radius: 99px; background: #e2ece9; overflow: hidden; }
.bt i, .stack i { display: block; height: 100%; border-radius: 99px; }
.stack { display: flex; height: 24px; border-radius: 99px; overflow: hidden; gap: 3px; background: transparent; }
.stack i { border-radius: 6px; }
.ink { background: var(--ink); } .blood { background: var(--primary-500); } .wine { background: var(--ink-deep); }
.teal { background: var(--teal-600); } .grey { background: #c9b8b5; }
.legend { list-style: none; margin: 16px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.legend li { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 600; }
.legend li span { flex: 1; }
.legend i { width: 12px; height: 12px; border-radius: 4px; flex-shrink: 0; }
.note { margin: 6px 0 0; font-size: 12.5px; line-height: 1.5; font-weight: 600; color: var(--slate); }

.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; }
.steps li { position: relative; padding: 22px; transition: transform 0.25s ease; }
.steps li:hover { transform: translateY(-4px) rotate(-0.4deg); }
.steps h3 { margin: 14px 0 6px; }
.steps p, .roles p, .sms-card p, .honest p, .road p, .pnote, .faq p { margin: 0; font-size: 14.5px; line-height: 1.55; font-weight: 500; color: #44545f; }
.big-ico { width: 52px; height: 52px; }
.num { position: absolute; top: 20px; right: 22px; font-size: 14px; font-weight: 800; color: var(--primary-500); }
.callout { display: flex; gap: 14px; align-items: flex-start; margin-top: 16px; padding: 18px 20px; background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: 26px; color: var(--amber-900); }
.callout svg { flex-shrink: 0; color: var(--amber-700); }
.callout p { margin: 0; font-size: 15px; line-height: 1.5; font-weight: 600; }

.timeline { list-style: none; margin: 0; padding: 0 0 0 4px; display: flex; flex-direction: column; gap: 16px; border-left: 2px solid var(--primary-500); margin-left: 6px; }
.timeline li { display: flex; flex-direction: column; gap: 2px; padding-left: 18px; position: relative; }
.timeline li::before { content: ''; position: absolute; left: -9px; top: 4px; width: 12px; height: 12px; border-radius: 99px; background: var(--primary-500); border: 3px solid #f3f8f7; }
.timeline b { font-size: 14px; color: var(--primary-700); }
.timeline span { font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #44545f; }

.roles { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; }
.roles li { padding: 22px; display: flex; flex-direction: column; gap: 4px; }
.roles h3 { margin-top: 12px; }
.roles small { font-size: 12px; font-weight: 700; color: var(--primary-700); margin-bottom: 6px; }
.sms-card { margin-top: 16px; padding: 22px; display: grid; gap: 16px; align-items: center; }
.sms-card h3 { margin-bottom: 4px; }
.bubbles { display: flex; flex-direction: column; gap: 8px; font-size: 13px; font-weight: 700; max-width: 320px; }
.bubbles span { padding: 10px 14px; border-radius: 18px; line-height: 1.4; }
.bubbles .out { align-self: flex-end; background: var(--azure-600); color: #fff; border-bottom-right-radius: 4px; }
.bubbles .in { align-self: flex-start; background: #fff; border: 1px solid var(--line); border-bottom-left-radius: 4px; }

.honest { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.honest li { display: flex; gap: 14px; padding: 20px; align-items: flex-start; }
.honest h3 { margin-bottom: 4px; }
.hi { width: 44px; height: 44px; border-radius: 14px; background: var(--amber-50); color: var(--amber-700); display: grid; place-items: center; flex-shrink: 0; }
.sens { margin-top: 16px; }

.pipe { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 10px 6px; align-items: center; }
.pipe li { display: flex; align-items: center; gap: 6px; }
.pipe span { padding: 10px 16px; border-radius: 99px; border: 1.5px solid var(--primary-500); background: #fff; font-weight: 800; font-size: 14px; color: var(--primary-700); }
.arrow { transform: rotate(180deg); color: var(--primary-500); }
.pnote { margin-top: 16px; max-width: 760px; }
.road { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.road li { padding: 22px; }
.road small { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--primary-500); }
.road h3 { margin: 6px 0; }

.safety { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.safety li { display: flex; gap: 12px; align-items: flex-start; font-size: 15.5px; line-height: 1.5; font-weight: 600; }
.safety li svg { color: var(--teal-600); flex-shrink: 0; margin-top: 2px; }
.faq { margin-top: 22px; display: grid; gap: 10px; max-width: 820px; }
.faq details { padding: 4px 18px; }
.faq summary { cursor: pointer; font-weight: 800; font-size: 15px; min-height: 48px; display: flex; align-items: center; }
.faq p { padding-bottom: 14px; }


@media (min-width: 900px) {
  .bgimg .bgblur { display: none; }
  .bgimg .main { top: 0; height: 100%; object-position: 100% 50%; -webkit-mask-image: none; mask-image: none; }
  .bgimg::after { background: linear-gradient(90deg, #f3f8f7 0%, rgba(244, 248, 247, 0.94) 30%, rgba(244, 248, 247, 0.5) 48%, rgba(244, 248, 247, 0) 68%), linear-gradient(180deg, rgba(244, 248, 247, 0.55) 0%, rgba(244, 248, 247, 0) 22%, rgba(244, 248, 247, 0) 70%, rgba(10, 107, 98, 0.18) 100%); }
  .hero { padding: 40px 64px clamp(110px, 9vw, 150px); min-height: clamp(740px, calc(100svh - var(--header-h)), 880px); }
  .chips-d { display: flex; }
  .cta-m { display: none; }
  /* The arch stands on the hills: its base sits in the empty sky of the horizon, so no hospital or label is covered. */
  .stage { position: absolute; right: 8%; bottom: calc(clamp(200px, 18vw, 270px) * 0.6); width: min(460px, 34vw); height: auto; aspect-ratio: 500 / 610; margin: 0; --iw: 172%; --il: -66%; --it: -77%; }
  .arch { border-radius: 50% 50% 40px 40px / 41% 41% 40px 40px; box-shadow: 0 30px 70px rgba(6, 74, 68, 0.22); }
  .fcard { right: auto; left: -96px; top: 34%; width: 280px; padding: 16px 18px; border-radius: 26px; gap: 4px; box-shadow: 0 22px 50px rgba(6, 74, 68, 0.2); }
  .fcard small { font-size: 11px; }
  .fcard strong { font-size: 17px; }
  .ft b { font-size: 40px; }
  .ft > span { font-size: 13px; }
  .fchip { display: block; position: absolute; z-index: 6; top: 40px; left: -40px; white-space: nowrap; padding: 11px 18px; border-radius: 99px; background: var(--primary-500); color: #fff; font-weight: 800; font-size: 14.5px; box-shadow: 0 14px 28px rgba(10, 107, 98, 0.38); }
  .fmini { display: flex; align-items: center; gap: 12px; position: absolute; z-index: 6; top: 56%; right: -56px; white-space: nowrap; padding: 12px 16px; border-radius: 20px; background: rgba(255, 255, 255, 0.95); border: 1px solid #d8e4e2; box-shadow: 0 16px 36px rgba(6, 74, 68, 0.18); }
  .fmini span:last-child { display: flex; flex-direction: column; }
  .fmini strong { font-size: 14px; color: #12202b; }
  .fmini small { font-size: 12px; font-weight: 700; color: var(--teal-600); }
  .stats { grid-template-columns: repeat(3, 1fr); gap: 36px 48px; }
  .share { grid-template-columns: 1fr 1fr; gap: 56px; }
  .charts { grid-template-columns: 1fr 1fr; }
  .steps { grid-template-columns: repeat(4, 1fr); }
  .example { grid-template-columns: 1.1fr 0.9fr; gap: 40px; }
  .roles { grid-template-columns: repeat(4, 1fr); }
  .sms-card { grid-template-columns: auto 1fr auto; gap: 24px; }
  .honest { grid-template-columns: 1fr 1fr; }
  .road { grid-template-columns: repeat(3, 1fr); }
  .section, .band { padding-left: 24px; padding-right: 24px; }
}

.ex-photo { margin: 0; position: relative; overflow: hidden; min-height: 280px; background: #cfe4e1; }
.ex-photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: 50% 30%; filter: saturate(1.05) contrast(1.02); }
.ex-photo figcaption, .gallery figcaption { position: absolute; left: 14px; bottom: 14px; right: 14px; padding: 9px 16px; border-radius: 99px; background: rgba(228, 242, 240, 0.96); color: var(--primary-700); font-weight: 800; font-size: 14px; box-shadow: 0 10px 22px rgba(4, 40, 38, 0.3); width: fit-content; max-width: calc(100% - 28px); }
.gallery { margin-top: 16px; display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.gallery figure { margin: 0; position: relative; overflow: hidden; aspect-ratio: 3 / 4; background: #cfe4e1; }
.gallery img { width: 100%; height: 100%; object-fit: cover; filter: saturate(1.05) contrast(1.02); transition: transform 0.8s cubic-bezier(0.2, 0.8, 0.2, 1); }
.gallery figure:hover img { transform: scale(1.06); }
.gallery figcaption { left: 10px; bottom: 10px; padding: 6px 12px; font-size: 12.5px; }
@media (max-width: 520px) { .gallery { gap: 8px; } .gallery figcaption { font-size: 11.5px; padding: 5px 10px; } }
@media (min-width: 900px) and (max-width: 1240px) { .fcard { left: -36px; width: 250px; } .fchip { left: -10px; } .fmini { right: -30px; top: 68%; } }
@keyframes bob { 50% { translate: 0 -8px; } }
</style>
