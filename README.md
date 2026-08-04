# AI/ML Remote Job Radar

Daily 07:00 IST email of **new** fully-remote AI/ML roles you can actually take
from India, each scored against your profile, with a tailored ATS-safe resume
attached for anything above your match threshold.

Runs on GitHub Actions. The LLM work runs on your existing Claude Pro/Max
subscription via an OAuth token — no API billing.

```
sources ──► pipeline.py ──► claude -p ──► render.py ──► notify.py ──► commit_state.py
 ATS +      keyword +        screen +      docx +        email        mark as seen
 boards     dedup            tailor        digest
```

---

## Setup

### 1. Repo

Create a **private** GitHub repo (your resume lives here) and push these files.

### 2. Claude auth — the free part

Locally, with Claude Code installed and logged into your Pro/Max account:

```bash
claude setup-token
```

Copy the printed `sk-ant-oat01-...` token into the repo:
**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | the token above |

> If you also have work Bedrock credentials configured, they don't interfere —
> the workflow runs in a clean container and only sees this token.

### 3. Email

Gmail needs an **App Password** (Google Account → Security → 2-Step
Verification → App passwords), not your normal password.

| Secret | Value |
|---|---|
| `SMTP_USER` | your.address@gmail.com |
| `SMTP_PASS` | 16-char app password |
| `MAIL_TO` | where the digest goes |

### 4. Validate the company list

The seed list in `config/companies.yml` is a starting point — board tokens go
stale when companies switch ATS. First run:

```bash
pip install -r requirements.txt
python scripts/validate_companies.py --prune
```

On my test run, 37 of 68 seed tokens were live across ~7,900 postings. **The
single biggest lever on this tool's usefulness is expanding this list.** Aim for
200+ companies. To add one, open its careers page and read the URL:

| URL pattern | ATS | Token |
|---|---|---|
| `job-boards.greenhouse.io/acme` | greenhouse | `acme` |
| `jobs.lever.co/acme` | lever | `acme` |
| `jobs.ashbyhq.com/acme` | ashby | `acme` |

### 5. Fill in your bullet bank

`profile/resume.yml` is the one file that determines output quality. Write
25–40 true, quantified bullets and tag them. The tailoring step may only
*select and rephrase* from this file — it is explicitly forbidden from
inventing experience, which is what keeps the output honest.

Also fill `never_claim` with things you've only lightly touched.

### 6. Test before trusting it

```bash
python src/pipeline.py       # check the filters locally
```

Then in GitHub: **Actions → Daily AI/ML job radar → Run workflow**, with
`dry_run` **checked**. That runs everything, skips the email, skips the state
commit, and uploads `out/digest.html` plus the resumes as a downloadable
artifact. Inspect them. When it looks right, uncheck dry_run.

---

## How the geography filter works, and why it matters

Most "remote" AI/ML jobs are remote-*within-a-country*. Without handling this,
the digest is 30 jobs you can't apply to. Two layers:

**Cheap layer (`pipeline.py`)** — regex on the location field. Rejects US state
abbreviations (`Remote - CA`), named regions (`Remote - United States`,
`Remote, EMEA`), and onsite markers, unless India/worldwide/APAC also appears.

**Expensive layer (`claude -p`)** — reads the actual description for work
authorization language, entity/payroll requirements, and timezone demands, and
classifies `global / india-ok / us-only / eu-only / unclear`. Only this layer
sees the fine print.

Things I found and fixed while testing, so you don't re-introduce them:

- **Ashby's `isRemote` flag lies.** It returns `true` for roles located "San
  Francisco". The flag is only trusted on board sources, which are remote-only
  by construction.
- **Don't keyword-match remote against job titles.** "Distributed Data Systems"
  is not a remote job.
- **Don't rescue HQ-located roles using phrases in the body.** Lyft's
  boilerplate says "work from anywhere" on San Francisco postings.

Net effect on my test run: 7,865 raw postings → 6 genuinely India-eligible
AI/ML remote roles. That ratio is normal and it is the point.

---

## Tuning

Everything lives in `config/filters.yml`.

| Symptom | Fix |
|---|---|
| Too few jobs | Add companies (biggest lever). Remove `principal`/`manager` from `title_blocklist`. Drop `match_threshold`. |
| Too many irrelevant | Raise `match_threshold`. Trim `title_keywords`. |
| Ineligible jobs slipping through | Add to `restricted_regions`; check the LLM screen isn't over-classifying `unclear`. |
| Burning quota | Lower `max_jobs_per_run` and `max_resumes_per_run`. |

`candidate_context` is passed straight to the screening prompt — keep it
accurate, it drives the eligibility call.

---

## Operational notes

- **Day one is a backlog dump.** The state file is empty, so the cap
  (`max_jobs_per_run: 30`) applies and the rest defer to tomorrow. From day two
  you'll see genuinely new postings only — usually a handful.
- **Cron drift.** GitHub's scheduler runs late under load, sometimes 20 minutes.
  Set for 01:10 UTC to land near 07:00 IST rather than after it.
- **State is committed only on success.** A crashed run doesn't silently
  swallow a day of postings. IDs expire after 120 days so `seen.json` can't
  grow forever.
- **Quota.** One `claude -p` invocation per day covering ≤30 job screens and
  ≤12 resumes. Well inside a Pro plan, but if you hit limits, lower
  `max_resumes_per_run` first — screening is cheap, tailoring isn't.

## Deliberately not included: LinkedIn scraping

LinkedIn has no public jobs API. The guest endpoint people scrape breaks
constantly, gets rate-limited, and is against their ToS. If you want that
coverage legitimately, add **Adzuna** (free tier, 250 calls/day) or **JSearch**
on RapidAPI — JSearch wraps Google Jobs, which indexes LinkedIn postings
anyway. Both drop cleanly into `src/sources.py` as another `BOARDS` entry.

## Before you send anything

Read every tailored resume. The prompt forbids invention and `never_claim`
guards the known traps, but you are the one signing your name to it.
