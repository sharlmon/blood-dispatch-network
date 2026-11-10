"""How much does the hospital-lending result depend on how fast hospitals dispatch?

The dataset has no hospital-to-hospital lending, so hospital arrival times reuse
regional-centre dispatch waits. This script re-ranks one request with hospitals
0, 1, 2 and 3 hours slower to dispatch, and with sharing switched off (today's
network), and prints a Markdown table.

Usage (from backend/, after build_db.py and fit_eta.py):
    export DATA_DIR=data
    python scripts/sensitivity.py --request-id REQ-020421
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `engine` importable

from engine import config, eta, rank  # noqa: E402
from engine.load import load_frames  # noqa: E402

EXTRA_HOURS = (0.0, 1.0, 2.0, 3.0)


def scenarios(request_id: str, frames, model, base_cfg: dict) -> list[dict]:
    """One row per scenario: label, top option, its range, baseline quote, advice."""
    req = rank.request_from_dataset(frames, request_id)
    runs = [("Sharing off (today's network)", {**base_cfg, "sharing_allowed": False})]
    runs += [
        (f"Sharing on, hospitals +{x:.0f} h to dispatch", {**base_cfg, "hospital_extra_dispatch_h": x})
        for x in EXTRA_HOURS
    ]
    rows = []
    for label, cfg in runs:
        out = rank.rank_sources(req, config=cfg, frames=frames, eta_model=model)
        top = out["options"][0] if out["options"] else None
        rows.append({
            "scenario": label,
            "top": top["name"] if top else None,
            "facility_id": top["facility_id"] if top else None,
            "p10": top["eta"]["p10"] if top else None,
            "p50": top["eta"]["p50"] if top else None,
            "p90": top["eta"]["p90"] if top else None,
            "quote": out["baseline"]["quote_hours"],
            "advice": out["advice"],
        })
    return rows


def markdown(rows: list[dict]) -> str:
    lines = [
        "| Scenario | Top option | Most likely (p50) | 8 in 10 within | Today's quote | Advice |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["top"] is None:
            lines.append(f"| {r['scenario']} | none | | | {r['quote']} h | {r['advice']} |")
            continue
        lines.append(
            f"| {r['scenario']} | {r['top']} | {r['p50']:.1f} h | {r['p10']:.1f}-{r['p90']:.1f} h "
            f"| {r['quote']:.1f} h | {r['advice'] or 'none'} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request-id", default="REQ-020421")
    args = parser.parse_args(argv)
    frames = load_frames(config.db_path())
    model = eta.load_model(config.eta_model_path())
    print(markdown(scenarios(args.request_id, frames, model, config.load_config())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
