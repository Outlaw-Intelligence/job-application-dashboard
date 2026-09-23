# Job Application Dashboard

A local-first command center for running a serious job search. It tracks every application through an approval-gated pipeline, indexes your materials, automates the repetitive parts, and keeps the final submit behind an explicit human decision.

Built because applying to dozens of roles with tailored materials is a pipeline problem — and pipelines deserve tooling.

## What it does

- **Approval-gated pipeline.** Every application moves through `draft → review → approved → submit_authorized → submitted`, with `needs_changes` and `submission_blocked` states when something needs intervention. Nothing gets submitted until you explicitly authorize it.
- **Submission guardrails.** Blockers are surfaced, not silent: missing required fields, missing resume/cover letter, broken apply links, login/CAPTCHA walls, closed postings. Two failed attempts auto-blocks a packet for manual review.
- **Evidence-gated submissions.** A packet can only be marked `submitted` with employer confirmation evidence (receipt, confirmation URL). The summary counts evidenced submissions separately from unverified ones.
- **Material index.** Indexes resumes, cover letters, and application packets across your local directories so everything is searchable in one place. Stale entries (deleted files) are pruned on refresh.
- **Command center.** Live metrics — packages in flight, approved, submitted, blocked — plus per-application review panels with a markdown-rendered packet overview.
- **Greenhouse automation.** `greenhouse_applicant.py` automates Greenhouse application forms via Playwright, with `--dry-run` validation before anything is submitted.
- **Manifest export.** `/api/export` produces a JSON manifest of your pipeline state.

## Quickstart

```bash
./launch_dashboard.sh
```

Then open http://127.0.0.1:8765 in your browser. (Override with `HOST` / `PORT` env vars.)

No dependencies to install for the dashboard itself — `app.py` is stdlib-only Python.

## How it works

`app.py` is a single-file application: a threaded HTTP server (`ThreadingHTTPServer`) serving the dashboard UI, backed by SQLite (`dashboard.sqlite3`). Job lead sources are configured in `job-search-sources.json`. Everything runs locally on `127.0.0.1`; your data never leaves your machine.

Machine-specific paths (`/Users/...`) can be overridden with env vars: `JOB_DASHBOARD_HOME` and `JOBOPS_ROOT`.

## Project structure

| File | What it is |
|---|---|
| `app.py` | Dashboard server, API, and UI — threaded HTTP server + SQLite, stdlib only |
| `greenhouse_applicant.py` | Greenhouse form automation via Playwright (`--dry-run` / `--submit`) |
| `test_dashboard.py` | Test suite — board cards, summary payload, and the submission guardrail state machine |
| `job-search-sources.json` | Configured job lead sources |
| `launch_dashboard.sh` | One-command launcher |
| `.env.example` | Environment template for the Greenhouse automation script — copy to `.env` |

## The approval gate

The core design decision: automation prepares, humans submit. The dashboard indexes materials, tracks state, fills what it can, and flags blockers — but the `submit_authorized` state requires explicit approval per application, and `submitted` requires confirmation evidence. That discipline is what makes high-volume applying safe instead of reckless.

## Greenhouse automation setup

```bash
pip install playwright
playwright install chromium
cp .env.example .env   # fill in your details
python greenhouse_applicant.py --job-id <id> --role "<title>" --dry-run
python greenhouse_applicant.py --job-id <id> --role "<title>" --submit
```

## Testing

```bash
python -m unittest test_dashboard -v
```

14 tests covering the board-card logic, the summary payload, the blocker taxonomy, index pruning, and the full submission guardrail flow (authorization → blocking → evidence → submitted) through the real HTTP handler.

## Requirements

- Python 3 (stdlib only for the dashboard)
- Playwright + Chromium only for `greenhouse_applicant.py`

## License

MIT — see [LICENSE](LICENSE).
