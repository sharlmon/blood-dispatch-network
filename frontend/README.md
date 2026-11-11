# frontend/ (Nuxt 4)

Owner: Frontend. UI direction: **Map Command** (map first, list second, honest arrival windows).

```bash
cd frontend
npm install
cp .env.example .env   # API base defaults to http://localhost:5001
npm run dev            # http://localhost:3000
```

Needs Node 22 or newer. The API runs on port **5001** (macOS reserves 5000 for AirPlay).

## Live data or demo data

- **Live** (normal builds): `NUXT_PUBLIC_API_BASE` is set, `http://localhost:5001` by default.
  Every screen reads the Flask API, and the API serves the ranking engine on the starter data.
  Live mode never falls back to demo data.
- **Static demo**: `NUXT_PUBLIC_API_BASE` is empty, which is the default for the GitHub Pages
  build (`GH_PAGES=1`). No API is called. Request, results and track run on fictional demo
  data in the engine's JSON shape (`app/utils/mock.ts`). Evidence and Pre-alerts read the
  committed `results/` files, which only this static build serves, at `<base>/results-data/`.
  Live builds get them from the API, so the pre-alert list stays behind its sign-in.
- **Example link** (`?demo=1`, from the landing page): runs on the fictional demo data in every
  build, so signed-out visitors see it; nothing is sent to the API or stored.

To run against the API, start it with the engine data built and `DATA_DIR` set (see the
[root README](../README.md#quick-start) and [backend/README.md](../backend/README.md)), then
pick a sign-in:

- **Local demo:** run the API with `AUTH_DISABLED=1` and the frontend with `DEMO_AUTH=1 npm run dev`.
  Demo accounts live only in this browser (localStorage), with no password.
- **Clerk:** set `NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `NUXT_CLERK_SECRET_KEY` here, and
  `CLERK_PUBLISHABLE_KEY` (or `CLERK_ISSUER`) on the API.

The API's `CORS_ORIGINS` must include this app's origin (`http://localhost:3000` by default).
Every API call runs in the browser, never during server rendering.

When the API is unreachable, `/api/health` reports the engine in error, or a call answers
`503 engine_unavailable`, a banner tells the lab worker to use the phone process: "Ranking
engine not available: <reason>. Use the phone process: call the blood centre directly." (or
"Tool not reachable. ..."). The header chip shows **Offline**, **Engine down**, **Not verified**
or **Loading data**. Other errors show as toasts with the API's message.

## Screens

| Route | What it is |
|---|---|
| `/` | Landing page: the 1 a.m. problem, key numbers, how it works, safety principles. Its example runs on the fictional demo data |
| `/sign-in`, `/sign-up`, `/onboarding` | Clerk login in the splash style, then hospital setup. With `DEMO_AUTH=1`, or in the static demo without a Clerk key: a local demo account |
| `/request` | New request: patient group (none preselected; or Unknown: group O only), red cells, units (1-10), longest wait (1-12 h, default 6 h), requesting hospital (live: a dropdown of the dataset's hospitals, from your saved choice or your organisation, never guessed). "Nearby sources" preview with 8-in-10 ranges, your organisation's recent requests (each names its hospital), SMS format hint |
| `/results` | Map plus ranked sources: most likely time and the 8-in-10 range, today's way (one quote, no range) and how much sooner, the **wait too long** state with emergency group O / transfer (both audited), "no single site has all N units", the stock date, "Rough estimate" when no arrival model is loaded, and "Why this source" |
| `/track` | Arrival window and clock, steps (request sent, shelf check, shelf confirmed, dispatched, arrived), a 10-minute shelf-check countdown, Try next source, Call site, Cancel request, and the audit log in East Africa Time. "Demo: record next step" stands in for the supplying site |
| `/prealerts` | Evening pre-alerts for regional centre staff: hospitals with a known zero in the last closing count, hospitals with no count, the assumptions, and the rule's held-out precision |
| `/evidence` | Results tab for expert reviewers: arrival validation, the replay ladder per scenario, the evening alert evaluation, assumptions and provenance |

Stock is the closing count of the day before the request, unconfirmed until the site confirms.
The results and detail screens date the count, and say how old it is when it is older than the
day before the request (for example after the synthetic data ends on 31 Oct 2026, without a
demo clock). The engine's reason sentences and `stock_note` are shown verbatim (spec section 9).

## Links

| Link | Opens |
|---|---|
| `/results?id=BDN-XXXXXXXX`, `/track?id=BDN-XXXXXXXX` | A saved request of your hospital |
| `/results?group=B%2B&units=2&limit=6&facility=HSP-004&at=2026-10-31T00:58` | A preview from `POST /api/rank`. Nothing is saved until someone picks a source; then the request is saved and the link becomes `?id=` |
| `/request?sos=1` | A new request with the group set to Unknown (group O only) |
| `/evidence?scenario=hospital-reserve-5#replay` | Evidence with that replay scenario |
| `/results?group=…&units=…&limit=…&pick=<id>`, `/track?group=…&pick=<id>&stage=1` | Static demo only. Stage 1 shelf check, 2 shelf confirmed, 3 dispatched, 4 arrived |

`group` takes `A−`, `A-` or `Unknown` (write `+` as `%2B`). `facility` and `at` are optional:
the defaults are your default hospital and the API's clock. In links, units run 1-50 and the
limit up to 72 h. `demo=1` lets a link skip the sign-in screen (the API still checks the
caller); the app keeps it on the links it builds.

## Structure

| Path | Purpose |
|---|---|
| `app/utils/engine.ts` | The API contract (types for every request and response, exact field names) and the adapter from an engine option to the screens' `Option`. Also group converters, flag and status labels, workflow rules, audit sentences, map positions. No framework code, so it also runs in plain Node |
| `app/utils/mock.ts` | Fictional demo data in the same `RankResult` shape, following the engine's rules. Only for the static demo and the landing-page example |
| `app/utils/format.ts` | Hours, ranges, East Africa Time |
| `app/composables/useApi.ts` | API calls with the Clerk token; turns errors into `{status, code, message}`, toasts and the phone-process flags |
| `app/composables/useEngineStatus.ts` | `/api/health`, polled while the engine loads; the banner text |
| `app/composables/useFacilities.ts` | `/api/facilities`, loaded once; the chosen hospital (localStorage `bdn-facility`) |
| `app/composables/useDispatch.ts` | The request on screen: search, preview, restore from a link, pick, site steps, next source, decisions, cancel. The server's status and audit replace local state |
| `app/composables/useResults.ts` | Results files and the pre-alert list, from the API or `<base>/results-data/` |
| `app/components/` | `SourceMap`, `SourceCard`, `SourceDetail`, `WindowBar`, `BloodGroupPicker`, `Evidence*`, `PrealertFacility`, `AppIcon`, `SafetyNote`, ... |
| `app/middleware/auth.global.ts` | Which routes need sign-in |
| `app/layouts/default.vue` | Header, navigation, status chip, phone-process banner |
| `app/assets/css/main.css` | Palette tokens and shared styles |
| `app/utils/icons.ts` | The icon set (24px grid, 1.75 stroke) |

The API endpoints the screens call are listed in [backend/README.md](../backend/README.md#endpoints).

## Deploy to GitHub Pages

`scripts/deploy-pages.sh` builds a static SPA (`GH_PAGES=1`, base path `/<repo>/`) and pushes it to the `gh-pages` branch. Pages is static, so there is no Flask API and no server-side Clerk: the build runs on the fictional demo data, and the results screen says **Demo data: fictional sites**. If `NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is set at build time, Clerk login is included (client-side only; add the Pages URL to the Clerk allowed origins); otherwise people make a local demo account. To point it at a hosted API, pass it in the shell: `NUXT_PUBLIC_API_BASE=https://api.example.org scripts/deploy-pages.sh`. The script ignores `frontend/.env`'s development value, so visitors' browsers never call localhost.

## Authentication (Clerk)

`@clerk/nuxt`. Public routes: `/`, `/sign-in`, `/sign-up`, `/evidence` and demo links (`?demo=1`). Everything else needs a signed-in user who belongs to a **hospital**, which is a Clerk Organization: `/onboarding` lets them join or create one. The header shows the hospital switcher and user menu.

In development Clerk runs *keyless* on temporary keys (you will see a "Configure your application" panel), but the API cannot verify those sessions. For a real setup create an app at dashboard.clerk.com, enable Organizations, and set `NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `NUXT_CLERK_SECRET_KEY` (see `.env.example`). Set the same two variables on Vercel. The Flask API verifies every session token itself (`backend/app/clerk_auth.py`).

`DEMO_AUTH=1` turns Clerk off and uses local demo accounts instead (name, email, hospital and role, kept in this browser only). Pair it with `AUTH_DISABLED=1` on the API.

## Brand

Logo: **Convergence** (four drops closing in on one point; three red sources, one dark drop for your hospital). Components `BrandMark` and `BrandLogo` (`inline` and `stacked`, with `reverse` for dark and red backgrounds). SVGs live in `frontend/public/` and `docs/brand/convergence/` (colour, black, reverse, lockup); `favicon.svg` is the app icon.

## Photos

`public/images/hand-vial.jpg` and `hand-tube.jpg` are free-to-use photos from [Pexels](https://www.pexels.com) (Pexels License: free to use and modify). Any grading is a CSS filter, not an edited file.

## Look and motion

Calm palette: teal is the interface colour; red is kept for blood, urgency and the logo. Grain and floating blood cells, uppercase headlines, outlined pill chips with illustrated icons, organic outlined cards, a floating pill header and a teal nav pill on mobile. Landing and login use real photography over a block wall of blood groups with handwritten letters. Motion: staggered rise-in, a block bobbing over its gap, pins dropping onto the map, flowing route line, pulsing location dot, growing arrival-window bars. All motion is off under `prefers-reduced-motion`.

## Known gaps (next)

- The map is schematic: true bearing from the requesting hospital, distances scaled to fit. It is not real geography.
- No supplying-site view: the site's steps are recorded from the requesting hospital's track page.
- No site phone register yet: "Contact site" and "Call site" show no number; call the site the usual way.
- No SMS view; the SMS hint shows the shortcode 38421 (set in `app/utils/sms.ts`).
- No dark mode.
- The landing page's "28%" and "617" figures match the starter data (2,456 of 8,768 emergency requests had local stock below the units asked for; 617 red cell emergencies were issued no units; checked 2026-11-10) but no committed results file records them yet.
- No automated tests yet.
