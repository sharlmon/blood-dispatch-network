# Blood Dispatch Network

> Network Finder with honest arrival windows — built for the **Terumo BCT Africa Hackathon 2026**.

It's 1 a.m. A patient needs blood urgently and the hospital fridge doesn't have the right type. Today the lab worker phones the main blood centre and hopes; if it has none, they phone another and wait with no idea how long it will take. In the data, about **1 in 4** of these patients got no blood at all. Meanwhile a hospital 30 minutes away often has spare bags of exactly that type, but hospitals never share with each other.

## What it does

1. The lab worker enters what the patient needs, on a computer or by **SMS from a basic phone**.
2. The tool checks every nearby blood centre and hospital and lists those with **spare, compatible units**. A hospital only shares what it can spare, so it never leaves itself short.
3. Each option gets an **honest arrival window**, e.g. "most likely 2½ h, almost certainly 2–3½ h".
4. The lab worker picks one. The supplying site **confirms the units are on the shelf**, then dispatches.
5. If the wait is too long, the tool says so plainly so the clinician can act now (emergency group O, or transfer the patient).
6. **Evening pre-alert:** lists hospitals that have run out of the most common blood type so the centre can top them up before the 1 a.m. emergency.

## Safety principles

- A **person makes every decision**; the tool suggests, people approve.
- The tool never decides blood group. Unknown group → request group O only, per hospital protocol.
- A trained lab worker crossmatches and checks every unit before transfusion.
- Lending protects O-negative stock held for girls and women of childbearing age.
- If the tool fails, everyone **falls back to the existing phone process**.

## Why it matters (synthetic data, Nov 2025 – Oct 2026)

- Blood would have arrived ~**2 hours sooner** on average.
- ~**290** patients who got nothing could have had blood within 6 hours.
- Checking the six regional centres alone reaches 208 of 617 unmet requests within 6 h; hospital lending adds ~80.

**Limitations:** hospital lending is assumed (none observed in data); yesterday's stock may be gone by request time (confirmation timeout moves to next site); remote hospitals gain little; all figures are synthetic and exploratory.

## Architecture (planned)

```
SMS / Web UI ──► API + workflow ──► Ranking engine ──► Arrival-window model
                     │                    ▲
                     ├─ audit log         └─ stock (yesterday + today's releases)
                     └─ fallback mode          config (country settings)
```

| Path | Purpose |
|---|---|
| `engine/` | Ranking engine, arrival ranges, replay ladder, pre-alert test |
| `api/` | API, workflow logic, audit log, fallback |
| `sms/` | SMS parser |
| `web/` | Screens and results tab |
| `config/` | Settings file (country-portable: change config, not code) |
| `docs/` | Architecture diagram, standards table, video script |
| `results/` | Results JSON for the expert review |
| `data/` | Dataset (git-ignored) |
| `scripts/`, `tests/` | Tooling and tests |

## Roadmap

1. Prevent shortages before they happen (pre-alerts).
2. Live national blood picture for the health ministry.
3. New country = new settings file, no rewrite.

## Team & ownership

| Role | Owns |
|---|---|
| Data scientist 1 | Ranking engine (Tue 18:00). Stretch: estimate today's centre stock |
| Data scientist 2 | Arrival ranges, replay ladder, pre-alert test, results JSON (ready 15:00) |
| Full-stack 1 | API, workflow, audit log, fallback, deployment |
| Full-stack 2 | SMS parser, settings file, demo clock, architecture diagram, standards table |
| Frontend | Screens, results tab, video script and recording |

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow.

## License

MIT — see [LICENSE](LICENSE). Data is synthetic; nothing here describes real facilities.
