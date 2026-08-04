"""Ping every ATS token in config/companies.yml and report which are live.

    python scripts/validate_companies.py            # report
    python scripts/validate_companies.py --prune    # rewrite config, dropping dead tokens

Run this before your first real run, and again any time the digest goes quiet.
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import sources  # noqa: E402

CFG = ROOT / "config" / "companies.yml"


def check(ats: str, token: str):
    try:
        jobs = sources.ATS[ats](token)
        return ats, token, "live" if jobs else "empty", len(jobs)
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", type(e).__name__)
        return ats, token, f"dead({code})", 0


def main():
    cfg = yaml.safe_load(CFG.read_text())
    tasks = [(a, t) for a, toks in (cfg.get("ats") or {}).items() for t in toks or []]

    results = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(lambda p: check(*p), tasks):
            results.append(r)
            flag = "OK " if r[2] == "live" else "-- "
            print(f"{flag}{r[0]:12s} {r[1]:22s} {r[2]:12s} {r[3]:4d} jobs")

    live = [r for r in results if r[2] == "live"]
    print(f"\n{len(live)}/{len(results)} live, "
          f"{sum(r[3] for r in live)} total postings across all boards")

    if "--prune" in sys.argv:
        keep = {}
        for ats, token, status, _ in results:
            if status == "live":
                keep.setdefault(ats, []).append(token)
        cfg["ats"] = keep
        CFG.write_text(yaml.safe_dump(cfg, sort_keys=False))
        print(f"Pruned config/companies.yml -> {sum(len(v) for v in keep.values())} tokens kept")


if __name__ == "__main__":
    main()
