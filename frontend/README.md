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
| `/` | New request: blood group, product, units, longest wait, SMS format hint |
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

## Known gaps (next)

- Data is mocked; the map is a schematic SVG, not real geography.
- No dark mode, SMS view, evening top-up list, audit page or results tab yet.
- No automated tests yet.
