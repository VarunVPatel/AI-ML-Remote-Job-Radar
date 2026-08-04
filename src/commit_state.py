"""Stage 5: mark this run's jobs as seen. Runs only after a successful send,
so a crashed run doesn't silently swallow a day of postings.

Also expires entries older than RETAIN_DAYS to stop seen.json growing forever.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state" / "seen.json"
PENDING = ROOT / "work" / "pending_ids.json"
RETAIN_DAYS = 120


def main():
    seen = json.loads(STATE.read_text()) if STATE.exists() else {}
    pending = json.loads(PENDING.read_text()) if PENDING.exists() else []

    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    for jid in pending:
        seen[jid] = stamp

    cutoff = now - timedelta(days=RETAIN_DAYS)
    before = len(seen)
    seen = {
        k: v for k, v in seen.items()
        if datetime.fromisoformat(v) > cutoff
    }

    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(seen, indent=0, sort_keys=True))
    print(f"State: +{len(pending)} new, -{before + len(pending) - len(seen)} expired, "
          f"{len(seen)} tracked")


if __name__ == "__main__":
    main()
