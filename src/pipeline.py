"""Stage 1: fetch every source, keyword-filter, drop already-seen jobs.

Writes work/new_jobs.json for the Claude screening stage.
Deliberately dumb: no LLM here, so the expensive stage only ever sees
a small, deduplicated batch.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import sources  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
STATE = ROOT / "state" / "seen.json"


def load_cfg():
    with open(ROOT / "config" / "filters.yml") as f:
        filters = yaml.safe_load(f)
    with open(ROOT / "config" / "companies.yml") as f:
        companies = yaml.safe_load(f)
    return filters, companies


def fingerprint(j: dict) -> str:
    key = f"{j['company'].lower()}|{re.sub(r'[^a-z0-9]', '', j['title'].lower())}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def load_seen() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def matches_role(j: dict, f: dict) -> bool:
    title = j["title"].lower()
    if any(re.search(rf"\b{re.escape(b)}\b", title) for b in f["title_blocklist"]):
        return False
    return any(re.search(rf"\b{re.escape(k)}\b", title) for k in f["title_keywords"])


def looks_remote(j: dict, f: dict) -> bool:
    """ATS `isRemote` flags are unreliable — Ashby returns True for roles
    whose location is plainly 'San Francisco'. So we only trust the flag on
    board sources, which are remote-only by construction.

    Matching is against the LOCATION field only. Matching titles too was worse:
    'Distributed Data Systems' is not a remote job. And rescuing HQ-located
    roles via body phrases was worse still — Lyft's boilerplate says 'work from
    anywhere' on San Francisco roles."""
    loc = j["location"].lower()
    if any(w in loc for w in f["onsite_markers"]):
        return False
    if j["source"] not in sources.ATS:
        return True
    return any(w in loc for w in f["remote_markers"])


def hard_geo_reject(j: dict, f: dict) -> bool:
    """Cheap pre-filter for obviously ineligible geographies.
    The nuanced call still happens in the LLM screen — this only kills
    the blatant ones so we don't pay tokens on them."""
    hay = j["location"].lower()
    if any(re.search(p, hay) for p in f["geo_hard_reject"]):
        return True
    # 'Remote - United States' / 'Remote, EMEA': a named region in the location
    # scopes the role to it, unless India or a global marker is also present.
    if re.search(f["us_state_pattern"], hay):
        return True
    if any(re.search(rf"\b{r}\b", hay) for r in f["restricted_regions"]):
        return not any(g in hay for g in f["ok_regions"])
    return False


def fetch_all(companies: dict) -> list[dict]:
    tasks = []
    for ats, tokens in (companies.get("ats") or {}).items():
        fn = sources.ATS.get(ats)
        if not fn:
            continue
        for token in tokens or []:
            tasks.append((f"{ats}:{token}", fn, token))
    for name in companies.get("boards") or []:
        fn = sources.BOARDS.get(name)
        if fn:
            tasks.append((f"board:{name}", fn, None))

    jobs, failures = [], []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {
            ex.submit(fn, tok) if tok else ex.submit(fn): label
            for label, fn, tok in tasks
        }
        for fut in cf.as_completed(futs):
            label = futs[fut]
            try:
                got = fut.result()
                jobs.extend(got)
                print(f"  ok   {label:38s} {len(got):4d}")
            except Exception as e:
                failures.append(label)
                print(f"  FAIL {label:38s} {type(e).__name__}: {e}")
    if failures:
        print(f"\n{len(failures)} source(s) failed: {', '.join(failures[:15])}")
    return jobs


def main():
    filters, companies = load_cfg()
    WORK.mkdir(exist_ok=True)

    print("Fetching sources...")
    raw = fetch_all(companies)
    print(f"\nRaw postings: {len(raw)}")

    seen = load_seen()
    kept, stats = [], {"role": 0, "remote": 0, "geo": 0, "seen": 0}

    for j in raw:
        if not j.get("url") or not j.get("title"):
            continue
        if not matches_role(j, filters):
            stats["role"] += 1
            continue
        if not looks_remote(j, filters):
            stats["remote"] += 1
            continue
        if hard_geo_reject(j, filters):
            stats["geo"] += 1
            continue
        fp = fingerprint(j)
        if fp in seen:
            stats["seen"] += 1
            continue
        j["id"] = fp
        kept.append(j)

    # newest-looking first, then cap so one bad day can't burn the quota
    kept.sort(key=lambda x: (x["source"] not in sources.ATS, str(x.get("posted") or "")), reverse=False)
    cap = filters.get("max_jobs_per_run", 30)
    overflow = max(0, len(kept) - cap)
    kept = kept[:cap]

    print(f"Filtered out -> role:{stats['role']} not-remote:{stats['remote']} "
          f"geo:{stats['geo']} already-seen:{stats['seen']}")
    print(f"New jobs to screen: {len(kept)}" + (f" (capped, {overflow} deferred)" if overflow else ""))

    (WORK / "new_jobs.json").write_text(json.dumps(kept, indent=2))
    # NOTE: state is only committed at the very end of the workflow, so a
    # mid-run crash doesn't silently swallow a day of postings.
    (WORK / "pending_ids.json").write_text(json.dumps([j["id"] for j in kept]))


if __name__ == "__main__":
    main()
