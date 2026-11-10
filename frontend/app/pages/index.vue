<script setup lang="ts">
useHead({ title: 'Blood Dispatch · Find spare blood nearby' })

const demo = mockRank({ id: '#demo', group: 'B+', units: 2, product: 'Red cells', limitH: 3, openedAt: '01:04' }).options
const selected = demo[0]!.id

const stats = [
  { big: '28%', text: 'of emergencies (2,456 of 8,768) hit a hospital fridge that fell short.' },
  { big: '617', text: 'red cell emergencies got no blood at all. About 1 in 4 of those short.' },
  { big: '0 of 5,330', text: 'emergency transfers came from another hospital. All came from regional centres.' },
  { big: '2.0 h', text: 'median wait from request to dispatch, about a third of the delivery time.' },
  { big: '~2 h', text: 'sooner on average when last year\'s requests are replayed with the tool.' },
  { big: '~290', text: 'patients who got nothing could have had blood within 6 hours.' }
]
const funnel = [
  { label: 'Emergency requests', n: '8,768', w: 100, tone: 'ink' },
  { label: 'Hospital fridge fell short', n: '2,456', w: 28, tone: 'blood' },
  { label: 'Red cell emergencies with no blood at all', n: '617', w: 7, tone: 'wine' }
]
const impact = [
  { label: 'Regional centre stock check alone', n: '208', w: 33.7, tone: 'teal' },
  { label: 'Plus hospital lending', n: '~80', w: 13, tone: 'blood' },
  { label: 'Still not reachable in 6 h', n: '~330', w: 53.3, tone: 'grey' }
]
const steps = [
  { icon: 'pen', title: 'Type what the patient needs', body: 'Blood group, units and the longest the patient can wait. On a computer, or by text message from a basic phone.' },
  { icon: 'bag', title: 'See who can spare it', body: 'Every nearby centre and hospital with compatible blood. A hospital only shares what it can spare, so it never leaves itself short.' },
  { icon: 'window', title: 'Read an honest arrival time', body: 'Not one number, a range: most likely 2½ h, almost certainly between 2 and 3½ h.' },
  { icon: 'confirm', title: 'Pick one, the shelf is checked', body: 'The supplier confirms the bags are really on the shelf, then sends them. No answer in 10 minutes, we move to the next source.' }
]
const honest = [
  { icon: 'warning', title: 'Lending is assumed, not observed', body: 'No hospital lent in the data. A lender 1 hour slower cuts rescues within 4 hours from 176 to 119.' },
  { icon: 'clock', title: 'Yesterday\'s stock can be gone', body: 'About 1 in 6 picks would lack units by end of day. The supplier confirms the shelf; no answer in 10 minutes moves to the next source.' },
  { icon: 'route', title: 'Remote hospitals gain little', body: 'The nearest other hospital to Garissa is 7.5 hours away, so the tool suggests referral or local emergency group O.' },
  { icon: 'drop', title: 'O negative is short everywhere', body: '57% of O negative shortfall emergencies went unmet. Lending protects stock held for girls and women of childbearing age.' }
]
const roles = [
  { icon: 'pen', who: 'Lab worker', at: 'Requesting hospital', body: 'Types the need, reads the ranked sources and their windows, and picks one.' },
  { icon: 'confirm', who: 'Supplying site', at: 'Centre or hospital', body: 'Confirms the units are really on the shelf, then dispatches.' },
  { icon: 'ambulance', who: 'Clinician', at: 'At the bedside', body: 'Is told plainly if the wait is too long, and chooses emergency group O or a transfer.' },
  { icon: 'bell', who: 'Regional centre staff', at: 'Every evening', body: 'Gets the list of hospitals out of the most common blood type, to top up first.' }
]
const pipeline = ['CSV data', 'SQLite', 'Ranking engine', 'Flask API', 'Web and SMS', 'Results tab']
const roadmap = [
  { n: 'Next', title: 'Prevent shortages', body: 'Move from an evening list to stock top-ups before the 1 a.m. emergency happens.' },
  { n: 'Then', title: 'A live national picture', body: 'Give the health ministry one live view of all the blood in the country.' },
  { n: 'After', title: 'Another country by settings', body: 'Set it up elsewhere by changing a settings file, not rewriting the code.' }
]
const faq = [
  { q: 'Does the tool decide who gets blood?', a: 'No. It suggests and people approve. A trained lab worker still checks every bag before it goes into a patient.' },
  { q: 'What if the blood group is unknown?', a: 'The tool never decides blood group. For an unknown group it requests group O only, per hospital protocol.' },
  { q: 'What if the stock count is out of date?', a: 'Stock is yesterday\'s closing count. The supplier confirms the shelf before anything moves, and a 10 minute timeout passes the request on.' },
  { q: 'What if the tool breaks?', a: 'Everyone falls back to the phone process they use today. The header shows when the tool cannot be reached.' }
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
          <NuxtLink to="/request" class="chip"><span class="chip-ico"><ServiceIcon name="find" :size="30" /></span>Find blood</NuxtLink>
          <NuxtLink to="/results?group=B%2B&units=2&limit=3&demo=1" class="chip"><span class="chip-ico"><ServiceIcon name="window" :size="30" /></span>See an example</NuxtLink>
          <a href="#phone" class="chip"><span class="chip-ico"><ServiceIcon name="sms" :size="30" /></span>Text a request</a>
        </div>
        <NuxtLink to="/request" class="btn btn-primary big rise" style="--d: 320ms"><AppIcon name="drop" :size="22" /> Find blood now</NuxtLink>
        <ul class="trust rise" style="--d: 400ms">
          <li><AppIcon name="check" :size="16" /> Works by text message</li>
          <li><AppIcon name="check" :size="16" /> A person approves every request</li>
          <li><AppIcon name="check" :size="16" /> Phone fallback if the tool is down</li>
        </ul>
      </div>

      <div class="visual rise" style="--d: 200ms">
        <div class="stage">
          <div class="live" aria-hidden="true">
            <div class="lh"><b>B+ · 2 units</b><small>Request 01:04</small></div>
            <div v-for="(o, i) in demo" :key="o.id" class="lr">
              <span class="ln" :class="o.kind">{{ i + 1 }}</span>
              <span class="lw">{{ o.name.split(' ').slice(0, 2).join(' ') }}</span>
              <span class="lt tnum">{{ fmtHours(o.p50) }}</span>
            </div>
          </div>
          <BloodMosaic />
        </div>
        <p class="cap">Hospitals share. Nobody runs short.</p>
      </div>
    </section>

    <section id="data" class="band" aria-labelledby="why">
      <div class="inner">
        <h2 id="why">The gap, in the data</h2>
        <p class="sub">Last year's requests, from the synthetic hackathon dataset (November 2025 to October 2026).</p>
        <ul class="stats">
          <li v-for="(st, i) in stats" :key="st.big" class="rise" :style="{ '--d': i * 70 + 'ms' }"><strong>{{ st.big }}</strong><span>{{ st.text }}</span></li>
        </ul>
      </div>
    </section>

    <section class="section" aria-labelledby="share">
      <div class="share">
        <div class="hands-card organic"><HandsPass /></div>
        <div class="share-copy">
          <h2 id="share">Hospitals have never shared. Now they can.</h2>
          <p>In the data, not one of 5,330 emergency transfers came from another hospital. Yet a hospital 30 minutes down the road often has spare bags of exactly that type. Nobody knows, because nobody can see.</p>
          <ul>
            <li><ServiceIcon name="bag" :size="26" /> Hospitals share only what they can spare.</li>
            <li><ServiceIcon name="confirm" :size="26" /> The supplier confirms the shelf before anything moves.</li>
            <li><ServiceIcon name="ambulance" :size="26" /> If the wait is too long, the doctor is told plainly.</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="section" aria-labelledby="funnel">
      <h2 id="funnel">Where the blood goes missing</h2>
      <div class="charts">
        <Reveal class="chart organic">
          <h3>From every emergency to the ones with no blood</h3>
          <div v-for="f in funnel" :key="f.label" class="bar-row">
            <div class="bl"><span>{{ f.label }}</span><b class="tnum">{{ f.n }}</b></div>
            <div class="bt"><i class="grow" :class="f.tone" :style="{ width: f.w + '%' }" /></div>
          </div>
          <p class="note">Bars are to scale. 617 of the 2,456 short emergencies, about 1 in 4, were red cell requests that got no blood.</p>
        </Reveal>

        <Reveal class="chart organic">
          <h3>What the tool could reach within 6 hours</h3>
          <div class="stack" role="img" aria-label="Of 617 unmet requests, 208 reachable from centre stock, about 80 more with hospital lending, about 330 not reachable">
            <i v-for="p in impact" :key="p.label" class="grow" :class="p.tone" :style="{ width: p.w + '%' }" />
          </div>
          <ul class="legend">
            <li v-for="p in impact" :key="p.label"><i :class="p.tone" /><span>{{ p.label }}</span><b class="tnum">{{ p.n }}</b></li>
          </ul>
          <p class="note">Of the 617 who got nothing. Checking the six regional centres alone reaches 208; hospital lending adds about 80. Counts are approximate and exploratory.</p>
        </Reveal>
      </div>
    </section>

    <section class="section" aria-labelledby="how">
      <h2 id="how">How it works</h2>
      <ol class="steps">
        <li v-for="(st, i) in steps" :key="st.title" class="organic rise" :style="{ '--d': i * 90 + 'ms' }">
          <span class="chip-ico big-ico"><ServiceIcon :name="st.icon" :size="38" /></span>
          <span class="num">{{ i + 1 }}</span>
          <h3>{{ st.title }}</h3>
          <p>{{ st.body }}</p>
        </li>
      </ol>
      <div class="callout rise">
        <AppIcon name="warning" :size="26" />
        <p><strong>If the wait is too long, it says so plainly.</strong> The doctor can act now: give emergency group O, or move the patient.</p>
      </div>
    </section>

    <section class="section" aria-labelledby="example">
      <h2 id="example">One request, end to end</h2>
      <div class="example">
        <div class="ex-card organic">
          <p class="kick">Example · 01:04</p>
          <div class="ex-req"><span class="grp">B+</span><span><b>2 units · red cells</b><small>Hillside Hospital · limit 3 h</small></span></div>
          <ul class="ex-list">
            <li v-for="(o, i) in demo" :key="o.id">
              <div class="ex-top">
                <span class="ln" :class="[o.kind, { first: i === 0 }]">{{ i + 1 }}</span>
                <span class="ex-name"><b>{{ o.name }}</b><small>{{ o.kind === 'hospital' ? 'Hospital' : 'Centre' }} · {{ o.spare }} · {{ o.km }} km</small></span>
                <span class="ex-when"><b class="tnum">{{ fmtHours(o.p50) }}</b><small>{{ fmtRange(o.p10, o.p90) }}</small></span>
              </div>
              <WindowBar :p10="o.p10" :p50="o.p50" :p90="o.p90" :limit="3" :max="4" />
            </li>
          </ul>
          <NuxtLink to="/results?group=B%2B&units=2&limit=3&demo=1" class="btn btn-primary">Open this example on the map</NuxtLink>
        </div>
        <ol class="timeline">
          <li><b>01:04</b><span>Lab worker enters B+, 2 units, limit 3 h.</span></li>
          <li><b>01:05</b><span>Tool ranks three sources and draws their windows.</span></li>
          <li><b>01:06</b><span>Lab worker picks Lakeview. Request sent, logged.</span></li>
          <li><b>Shelf check</b><span>Lakeview confirms the units are on the shelf, within 10 minutes or the next source is asked.</span></li>
          <li><b>Dispatch</b><span>Bags leave. The window tightens.</span></li>
          <li><b>Arrival</b><span>Lab worker checks every bag before use. Every step is in the audit log.</span></li>
        </ol>
      </div>
    </section>

    <section id="phone" class="section" aria-labelledby="roles">
      <h2 id="roles">Who uses it</h2>
      <ul class="roles">
        <li v-for="(r, i) in roles" :key="r.who" class="organic rise" :style="{ '--d': i * 80 + 'ms' }">
          <span class="chip-ico big-ico"><ServiceIcon :name="r.icon" :size="36" /></span>
          <h3>{{ r.who }}</h3>
          <small>{{ r.at }}</small>
          <p>{{ r.body }}</p>
        </li>
      </ul>
      <div class="sms-card organic">
        <span class="chip-ico big-ico"><ServiceIcon name="sms" :size="36" /></span>
        <div>
          <h3>Works on any phone</h3>
          <p>Requests and confirmations also work by text message. No smartphone and no data needed at the bench.</p>
        </div>
        <div class="bubbles" aria-hidden="true"><span class="out">B+ 2 RBC 3H</span><span class="in">3 sources. Fastest Lakeview 1.5h (1-2.25h). Reply 1 to request.</span></div>
      </div>
    </section>

    <section class="section" aria-labelledby="honest">
      <h2 id="honest">What we are honest about</h2>
      <ul class="honest">
        <li v-for="h in honest" :key="h.title" class="card rise">
          <span class="hi"><AppIcon :name="h.icon" :size="22" /></span>
          <div><h3>{{ h.title }}</h3><p>{{ h.body }}</p></div>
        </li>
      </ul>
      <Reveal class="chart organic sens">
        <h3>If lenders are slower, fewer rescues</h3>
        <div class="bar-row"><div class="bl"><span>Hospitals lend at the assumed speed</span><b class="tnum">176</b></div><div class="bt"><i class="grow teal" style="width: 100%" /></div></div>
        <div class="bar-row"><div class="bl"><span>Lender is 1 hour slower</span><b class="tnum">119</b></div><div class="bt"><i class="grow blood" style="width: 67.6%" /></div></div>
        <p class="note">Patients with no blood who could be rescued within 4 hours.</p>
      </Reveal>
    </section>

    <section class="section" aria-labelledby="built">
      <h2 id="built">How it is built</h2>
      <ol class="pipe">
        <li v-for="(n, i) in pipeline" :key="n"><span>{{ n }}</span><AppIcon v-if="i < pipeline.length - 1" name="back" :size="18" class="arrow" /></li>
      </ol>
      <p class="pnote">Settings live in one file per country: lending rules, safety stock, arrival parameters. A new country is a new settings file, not a code change. The ranking engine uses fixed lookups and a seeded simulation; no AI model writes the numbers.</p>
    </section>

    <section class="section" aria-labelledby="road">
      <h2 id="road">Where it goes next</h2>
      <ol class="road">
        <li v-for="r in roadmap" :key="r.title" class="card"><small>{{ r.n }}</small><h3>{{ r.title }}</h3><p>{{ r.body }}</p></li>
      </ol>
    </section>

    <section class="section" aria-labelledby="safe">
      <h2 id="safe">Built to be safe</h2>
      <ul class="safety">
        <li v-for="t in safety" :key="t"><AppIcon name="check" :size="20" />{{ t }}</li>
      </ul>
      <div class="faq">
        <details v-for="f in faq" :key="f.q" class="card">
          <summary>{{ f.q }}</summary>
          <p>{{ f.a }}</p>
        </details>
      </div>
    </section>

    <section class="final">
      <BrandLogo layout="stacked" :size="64" reverse />
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
.trust { list-style: none; margin: 18px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 13px; font-weight: 700; color: #5a3c3f; }
.trust li { display: flex; align-items: center; gap: 6px; }
.trust svg { color: var(--teal-600); }
.visual { display: flex; flex-direction: column; gap: 12px; }
.stage { position: relative; border-radius: 44px 44px 36px 36px; padding: 150px 0 0; overflow: hidden; background: linear-gradient(180deg, #fff 0%, #fbe6e3 55%, #f3c6c0 100%); border: 1px solid var(--line); box-shadow: 0 24px 60px rgba(126, 16, 21, 0.18); }
.live { position: absolute; top: 18px; left: 18px; right: 18px; background: rgba(255, 255, 255, 0.92); border: 1px solid var(--line); border-radius: 18px; padding: 10px 14px; display: flex; flex-direction: column; gap: 4px; z-index: 2; }
.lh { display: flex; justify-content: space-between; align-items: baseline; font-size: 13px; }
.lh small { font-size: 11px; font-weight: 700; color: var(--slate); }
.lr { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 700; }
.lw { flex: 1; }
.lt { font-weight: 800; color: var(--teal-600); }
.ln { width: 22px; height: 22px; border-radius: 99px; background: var(--slate); color: #fff; font-size: 11px; font-weight: 800; display: grid; place-items: center; flex-shrink: 0; }
.ln.centre { border-radius: 6px; }
.ln.first { background: var(--blood-500); }
.cap { margin: 0; text-align: center; font-weight: 800; font-size: 14px; color: var(--blood-700); }

.band { background: linear-gradient(180deg, var(--wine), #2a0709); color: #fff; padding: 44px 16px 40px; }
.inner { max-width: 1200px; margin: 0 auto; }
.band h2 { margin: 0; font-size: 30px; letter-spacing: -0.02em; font-weight: 800; text-transform: uppercase; color: #fff; }
.sub { margin: 8px 0 28px; font-size: 14px; font-weight: 600; color: #d9b3b0; }
.stats { list-style: none; margin: 0; padding: 0; display: grid; gap: 22px; }
.stats strong { display: block; font-size: 42px; line-height: 1; letter-spacing: -0.02em; font-weight: 800; color: #ff9a92; }
.stats span { display: block; margin-top: 8px; font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #f2d5d2; max-width: 340px; }

.section { max-width: 1200px; margin: 0 auto; padding: 52px 16px 0; }
.section h2 { margin: 0 0 22px; font-size: 30px; letter-spacing: -0.02em; font-weight: 800; text-transform: uppercase; color: var(--blood-600); }
h3 { margin: 0; font-size: 17px; font-weight: 800; }

.share { display: grid; gap: 24px; align-items: center; }
.hands-card { padding: 28px 20px 20px; background: linear-gradient(180deg, #fff, #fbe6e3); overflow: hidden; }
.share-copy h2 { margin-bottom: 14px; }
.share-copy p { margin: 0 0 16px; font-size: 16px; line-height: 1.6; font-weight: 500; color: #5a3c3f; }
.share-copy ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.share-copy li { display: flex; align-items: center; gap: 12px; font-size: 15px; font-weight: 700; }
.charts { display: grid; gap: 16px; }
.chart { padding: 24px; }
.chart h3 { margin-bottom: 18px; }
.bar-row { margin-bottom: 16px; }
.bl { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; font-weight: 700; margin-bottom: 6px; }
.bl b { font-size: 16px; }
.bt { height: 16px; border-radius: 99px; background: #f0e1de; overflow: hidden; }
.bt i, .stack i { display: block; height: 100%; border-radius: 99px; }
.stack { display: flex; height: 24px; border-radius: 99px; overflow: hidden; gap: 3px; background: transparent; }
.stack i { border-radius: 6px; }
.ink { background: var(--ink); } .blood { background: var(--blood-500); } .wine { background: var(--wine); }
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
.steps p, .roles p, .sms-card p, .honest p, .road p, .pnote, .faq p { margin: 0; font-size: 14.5px; line-height: 1.55; font-weight: 500; color: #5a3c3f; }
.big-ico { width: 52px; height: 52px; }
.num { position: absolute; top: 20px; right: 22px; font-size: 14px; font-weight: 800; color: var(--blood-500); }
.callout { display: flex; gap: 14px; align-items: flex-start; margin-top: 16px; padding: 18px 20px; background: var(--amber-50); border: 2px solid var(--amber-500); border-radius: 26px; color: var(--amber-900); }
.callout svg { flex-shrink: 0; color: var(--amber-700); }
.callout p { margin: 0; font-size: 15px; line-height: 1.5; font-weight: 600; }

.example { display: grid; gap: 20px; align-items: start; }
.ex-card { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
.kick { margin: 0; font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--blood-700); }
.ex-req { display: flex; align-items: center; gap: 14px; }
.grp { font-size: 34px; font-weight: 800; color: var(--blood-500); line-height: 1; }
.ex-req span:last-child { display: flex; flex-direction: column; }
.ex-req small, .ex-name small, .ex-when small { font-size: 12px; font-weight: 600; color: var(--slate); }
.ex-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.ex-top { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.ex-name { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.ex-when { text-align: right; display: flex; flex-direction: column; }
.ex-when b { font-size: 20px; line-height: 1; }
.timeline { list-style: none; margin: 0; padding: 0 0 0 4px; display: flex; flex-direction: column; gap: 16px; border-left: 2px solid var(--blood-500); margin-left: 6px; }
.timeline li { display: flex; flex-direction: column; gap: 2px; padding-left: 18px; position: relative; }
.timeline li::before { content: ''; position: absolute; left: -9px; top: 4px; width: 12px; height: 12px; border-radius: 99px; background: var(--blood-500); border: 3px solid #fdf3f1; }
.timeline b { font-size: 14px; color: var(--blood-700); }
.timeline span { font-size: 14.5px; line-height: 1.5; font-weight: 500; color: #5a3c3f; }

.roles { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; }
.roles li { padding: 22px; display: flex; flex-direction: column; gap: 4px; }
.roles h3 { margin-top: 12px; }
.roles small { font-size: 12px; font-weight: 700; color: var(--blood-700); margin-bottom: 6px; }
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
.pipe span { padding: 10px 16px; border-radius: 99px; border: 1.5px solid var(--blood-500); background: #fff; font-weight: 800; font-size: 14px; color: var(--blood-700); }
.arrow { transform: rotate(180deg); color: var(--blood-500); }
.pnote { margin-top: 16px; max-width: 760px; }
.road { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.road li { padding: 22px; }
.road small { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--blood-500); }
.road h3 { margin: 6px 0; }

.safety { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.safety li { display: flex; gap: 12px; align-items: flex-start; font-size: 15.5px; line-height: 1.5; font-weight: 600; }
.safety li svg { color: var(--teal-600); flex-shrink: 0; margin-top: 2px; }
.faq { margin-top: 22px; display: grid; gap: 10px; max-width: 820px; }
.faq details { padding: 4px 18px; }
.faq summary { cursor: pointer; font-weight: 800; font-size: 15px; min-height: 48px; display: flex; align-items: center; }
.faq p { padding-bottom: 14px; }

.final { margin-top: 56px; padding: 56px 16px; background: radial-gradient(600px 240px at 50% 0%, #cf2a30, var(--blood-600)); color: #fff; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 22px; }
.final h2 { margin: 0; font-size: clamp(26px, 4.5vw, 40px); letter-spacing: -0.02em; text-transform: uppercase; }
.final .btn { background: #fff; color: var(--blood-700); border-color: #fff; margin-top: 0; }
.foot { padding: 20px 16px 28px; text-align: center; font-size: 12px; font-weight: 600; color: var(--slate); }

@media (min-width: 900px) {
  .hero { grid-template-columns: 1.1fr 0.9fr; gap: 64px; padding: 64px 24px 80px; }
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
</style>
