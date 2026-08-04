"""Job source fetchers.

Tier 1: ATS public APIs (Greenhouse / Lever / Ashby) -> links land on the
        company's own careers page.
Tier 2: aggregate remote job boards -> coverage for companies not on your list.

Every fetcher is wrapped so a single dead endpoint never kills the run.
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; job-radar/1.0)"}
TIMEOUT = 25
MAX_DESC = 7000  # chars; keeps token spend sane downstream


def _get(url: str, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()[:MAX_DESC]


def job(source, company, title, url, location, description="", posted=None, raw_remote=None):
    return {
        "source": source,
        "company": (company or "").strip(),
        "title": (title or "").strip(),
        "url": url,
        "location": (location or "").strip(),
        "description": clean(description),
        "posted": posted,
        "raw_remote": raw_remote,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- ATS Tier 1

def greenhouse(token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    data = _get(url).json()
    out = []
    for j in data.get("jobs", []):
        out.append(job(
            "greenhouse", token, j.get("title"), j.get("absolute_url"),
            (j.get("location") or {}).get("name", ""),
            j.get("content", ""), j.get("updated_at"),
        ))
    return out


def lever(token: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    data = _get(url).json()
    out = []
    for j in data:
        cats = j.get("categories") or {}
        desc = j.get("descriptionPlain") or j.get("description") or ""
        lists = " ".join(
            f"{s.get('text','')}: {s.get('content','')}" for s in (j.get("lists") or [])
        )
        out.append(job(
            "lever", token, j.get("text"), j.get("hostedUrl"),
            cats.get("location", ""), f"{desc}\n{lists}",
            j.get("createdAt"), cats.get("commitment"),
        ))
    return out


def ashby(token: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    data = _get(url).json()
    out = []
    for j in data.get("jobs", []):
        out.append(job(
            "ashby", token, j.get("title"), j.get("jobUrl"),
            j.get("location", ""),
            j.get("descriptionPlain") or j.get("descriptionHtml", ""),
            j.get("publishedAt"), j.get("isRemote"),
        ))
    return out


ATS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


# ------------------------------------------------------------- Boards Tier 2

def remotive() -> list[dict]:
    out = []
    for cat in ("software-dev", "data"):
        try:
            data = _get(f"https://remotive.com/api/remote-jobs?category={cat}&limit=200").json()
        except Exception:
            continue
        for j in data.get("jobs", []):
            out.append(job(
                "remotive", j.get("company_name"), j.get("title"), j.get("url"),
                j.get("candidate_required_location", ""), j.get("description", ""),
                j.get("publication_date"), True,
            ))
        time.sleep(1)
    return out


def remoteok() -> list[dict]:
    data = _get("https://remoteok.com/api").json()
    out = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # first element is a legal notice
        out.append(job(
            "remoteok", j.get("company"), j.get("position"), j.get("url"),
            j.get("location", "") or "Remote", j.get("description", ""),
            j.get("date"), True,
        ))
    return out


def arbeitnow() -> list[dict]:
    out = []
    for page in (1, 2):
        try:
            data = _get(f"https://www.arbeitnow.com/api/job-board-api?page={page}").json()
        except Exception:
            break
        for j in data.get("data", []):
            if not j.get("remote"):
                continue
            out.append(job(
                "arbeitnow", j.get("company_name"), j.get("title"), j.get("url"),
                j.get("location", ""), j.get("description", ""),
                j.get("created_at"), True,
            ))
        time.sleep(1)
    return out


def himalayas() -> list[dict]:
    data = _get("https://himalayas.app/jobs/api?limit=200").json()
    out = []
    for j in data.get("jobs", []):
        loc = j.get("locationRestrictions") or j.get("countries") or []
        if isinstance(loc, list):
            loc = ", ".join(str(x) for x in loc) or "Worldwide"
        out.append(job(
            "himalayas", j.get("companyName"), j.get("title"),
            j.get("applicationLink") or j.get("guid"),
            loc, j.get("description", ""), j.get("pubDate"), True,
        ))
    return out


BOARDS = {
    "remotive": remotive,
    "remoteok": remoteok,
    "arbeitnow": arbeitnow,
    "himalayas": himalayas,
}
