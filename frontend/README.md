# frontend/ (Nuxt 4)

Owner: Frontend. UI direction: **Map Command** (map first, list second, honest arrival windows).

```bash
cd frontend
npm install
cp .env.example .env   # API base defaults to http://localhost:5001
npm run dev            # http://localhost:3000
```

Needs Node 22 or newer. The API runs on port **5001** (macOS reserves 5000 for AirPlay).
When the API is unreachable the header shows **Offline** and a banner tells the lab worker to use the phone process.

## Screens

| Route | What it is |
|---|---|
| `/` | Landing page: the 1 a.m. problem, key numbers, how it works, safety principles |
| `/sign-in`, `/sign-up`, `/onboarding` | Clerk login in the splash style, then hospital setup |
| `/request` | New request: blood group, product, units, longest wait, SMS format hint |
| `/results` | Map plus ranked sources with arrival-window bars, "why this source", and the **wait too long** state with emergency group O / transfer actions |
| `/track` | Arrival window, shelf-confirmation timeline, audit log. "Demo: simulate next step" advances the stages |

`/results` and `/track` also open from a link, for demos and screenshots:
`/results?group=B%2B&units=2&limit=3` (rare groups such as `AB%E2%88%92` trigger the too-long state) and `/track?group=B%2B&stage=1`.

## Structure

| Path | Purpose |
|---|---|
| `app/assets/css/main.css` | Triage palette tokens and shared styles |
| `app/components/` | `SourceMap`, `SourceCard`, `WindowBar`, `BloodGroupPicker`, `AppIcon`, `SafetyNote` |
| `app/composables/useDispatch.ts` | Request, options, selection, stage and audit state |
| `app/utils/mock.ts` | **Mock** ranking data. Replace with `POST /api/requests` when the engine is ready |
| `app/utils/icons.ts` | The icon set (24px grid, 1.75 stroke) |
| `app/layouts/default.vue` | Header, live status, phone-process fallback banner |

## Authentication (Clerk)

`@clerk/nuxt`. Public routes: `/`, `/sign-in`, `/sign-up` and demo links (`?demo=1`). Everything else needs a signed-in user who belongs to a **hospital**, which is a Clerk Organization: `/onboarding` lets them join or create one. The header shows the hospital switcher and user menu.

In development Clerk runs *keyless* on temporary keys (you will see a "Configure your application" panel). For a real setup create an app at dashboard.clerk.com, enable Organizations, and set `NUXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `NUXT_CLERK_SECRET_KEY` (see `.env.example`). Set the same two variables on Vercel. The Flask API does not verify sessions yet.

## Brand

Logo: **Convergence** (four drops closing in on one point; three red sources, one dark drop for your hospital). Components `BrandMark` and `BrandLogo` (`inline` and `stacked`, with `reverse` for dark and red backgrounds). SVGs live in `frontend/public/` and `docs/brand/convergence/` (colour, black, reverse, lockup); `favicon.svg` is the app icon.

## Look and motion

Blush gradient with floating blood cells, brick-red palette, uppercase headlines, outlined pill chips, organic cards and a floating red nav pill on mobile. Motion: staggered rise-in, tile mosaic where a spare bag lands in a gap, pins dropping onto the map, flowing route line, pulsing location dot, growing arrival-window bars. All motion is off under `prefers-reduced-motion`.

## Known gaps (next)

- Data is mocked; the map is a schematic SVG, not real geography.
- No dark mode, SMS view, evening top-up list, audit page or results tab yet.
- No automated tests yet.
