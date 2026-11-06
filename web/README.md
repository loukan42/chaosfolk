# Hosted Quick audits

Visitors paste a URL on the landing page and get a Chaosfolk Quick audit report, with no
installation. Everything runs on free plans: GitHub Pages for the page, Vercel Hobby for the API,
the audits and the reports, and an OpenRouter free model. People who need more install Chaosfolk
or fork the repository.

```
GitHub Pages (site/)  --HTTPS-->  Vercel Function (FastAPI, web/index.py)
                                    |  queue and daily quota: Upstash Redis (free)
                                    |  reports: Vercel Blob, private store (free)
                                    '--> Vercel Sandbox microVM, restored from a prepared snapshot:
                                         Chaosfolk + Chromium + OpenCode on an OpenRouter model
```

There is no background worker. The function advances the queue when a visitor submits or polls an
audit (the landing page polls every few seconds), and a daily cron job cleans up expired reports.
One audit runs at a time.

## What protects the service

| Risk | Measure |
| --- | --- |
| Model and compute use | Global daily quota (1 by default), a cap on model requests per audit, one audit per IP per day, one audit at a time. On Hobby, Vercel pauses Sandbox and Blob when the monthly allowance is used instead of charging. |
| Robots | Cloudflare Turnstile on the form (optional) |
| A URL that reaches internal networks | http(s) on ports 80/443 only; local names refused; every resolved address must be public, checked at submission and again before the run; the sandbox firewall denies private, link-local and metadata ranges |
| The OpenRouter key | Never enters the sandbox: the sandbox firewall adds it to requests for `openrouter.ai` only |
| A hostile page or a confused agent | Each audit gets its own microVM, destroyed afterwards; the engine limits (Quick depth, time, actions) are set before the agent starts; the agent may run only `chaosfolk` and a few read commands and cannot fetch URLs itself |
| Private data in reports | The archive holds only the report, its `assets/`, `captures/`, `reproductions/` and `scenarios/`; browser state, the audit database and agent logs stay in the sandbox and disappear with it. Reports are deleted after 7 days and marked `noindex`. |
| Testing someone else's site | Consent checkbox, salted IP hash, small daily quota. Ownership is not verified. |

The report link is the only key to a report: anyone who has it can open it until it expires.

## Free plan budget

| Service | Free allowance (Hobby) | One Quick audit uses |
| --- | --- | --- |
| Vercel Sandbox | 5 h active CPU, 420 GB-h memory, 45 min per session | to be measured; CPU waiting for the model is not counted |
| Vercel Blob | 1 GB storage, 2,000 uploads, 10 GB transfer per month | one upload (the .zip) |
| Upstash Redis | free database | a few dozen commands |
| OpenRouter `:free` models | 20 requests/min; 50/day, or 1,000/day after buying 10 credits once | one request per agent step, capped by `CHAOSFOLK_WEB_AGENT_STEPS` (40) |

The OpenRouter daily limit is the first one you will hit. The first live audit (2026-11-05, three
users, no step cap) made about 60 requests in two minutes, 2.65 million prompt tokens, $0.00, and
then waited on the daily limit until the sandbox stopped. The defaults therefore fit one small audit
a day in the free 50 requests: `CHAOSFOLK_WEB_DAILY_QUOTA=1`, `CHAOSFOLK_WEB_USERS=1`,
`CHAOSFOLK_WEB_AGENT_STEPS=40`, no subagents. With 10 credits bought once on OpenRouter (free models
stay at $0), raise the steps to about 150, the users to 3 and the daily quota to what 1,000
requests allow.

## Download, share and replay

When an audit finishes, the page offers **Open the report**, **Download (.zip)**, **Copy the link**
and, on devices that support it, **Share**. The sandbox packs the report into one `.zip`
(`chaosfolk_web/pack.py`), stored as a single private blob. Report pages are served from that
archive by the function. Extracted, the folder opens offline (`rapport.html`) and keeps the session
replay screens. With Chaosfolk installed, `chaosfolk replay scenarios/NAME.json --times 3` replays a
recorded journey from that folder. The archive includes a README with these steps.

## Try it locally

No account is needed: local mode uses SQLite, files and the offline Chaosfolk demo, which ignores
the URL and always produces the demo report.

```bash
python -m venv .venv
.venv/bin/pip install -e . -r web/requirements.txt uvicorn
.venv/bin/python -m playwright install chromium
.venv/bin/python web/dev.py
```

Open http://127.0.0.1:8080/. Data goes to `.horde/web-dev/`. Tests:

```bash
.venv/bin/pip install pytest httpx
cd web && ../.venv/bin/python -m pytest
```

## Deploy

### 1. Accounts

- **Vercel** (Hobby, free): sign up with GitHub.
- **OpenRouter**: create an API key with a credit limit. Choose a free model that supports tool
  calls, for example `nvidia/nemotron-3-ultra-550b-a55b:free`; in OpenCode it is written
  `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`. Some free providers keep prompts, and the
  agent sends them the visited pages.
- **Cloudflare Turnstile** (optional): a widget for `loukan42.github.io`.

### 2. Vercel project

The current deployment is the `chaosfolk-web` project of the `chaosfolk` team, at
https://chaosfolk-web.vercel.app. It was set up from `web/` with the Vercel CLI:

```bash
vercel login
vercel link --yes --project chaosfolk-web --scope chaosfolk
vercel blob create-store chaosfolk-reports --access private --yes
vercel integration add upstash/upstash-kv --name chaosfolk-queue
```

The Upstash step asks once to accept its terms in the browser. The Blob store and Redis database
add `BLOB_READ_WRITE_TOKEN`, `KV_REST_API_URL` and `KV_REST_API_TOKEN` to the project. The
project is not connected to GitHub, so deploy from `web/` with `vercel deploy --prod`. To deploy
on every push instead, add a GitHub login connection to the Vercel account, connect the
repository and set **Root Directory** to `web`.

Environment variables (`vercel env add NAME production`, or the project settings):

   | Variable | Value |
   | --- | --- |
   | `OPENROUTER_API_KEY` | your OpenRouter key |
   | `CHAOSFOLK_WEB_MODEL` | `openrouter/<vendor>/<model>:free` |
   | `CHAOSFOLK_WEB_SNAPSHOT` | from step 3 |
   | `CHAOSFOLK_WEB_ALLOWED_ORIGINS` | `https://loukan42.github.io` |
   | `CRON_SECRET` | optional: a long random string; Vercel then authenticates the daily cron |
   | `CHAOSFOLK_WEB_TURNSTILE_SECRET` | optional |

   Optional: `CHAOSFOLK_WEB_DAILY_QUOTA` (1), `CHAOSFOLK_WEB_PER_IP_DAILY` (1),
   `CHAOSFOLK_WEB_AUDIT_MINUTES` (10), `CHAOSFOLK_WEB_MAX_ACTIONS` (80), `CHAOSFOLK_WEB_USERS` (1), `CHAOSFOLK_WEB_AGENT_STEPS` (40),
   `CHAOSFOLK_WEB_REPORT_DAYS` (7), `CHAOSFOLK_WEB_PUBLIC_URL` (defaults to the production domain).

### 3. Audit snapshot

From `web/`, with the Vercel CLI linked to the project:

```bash
vercel link
vercel env pull
python -m pip install "vercel>=0.12,<0.13"
python sandbox/build_snapshot.py --ref main
```

The script installs Chaosfolk, Chromium and OpenCode in a sandbox (`sandbox/setup.sh`), saves a
snapshot that never expires, and prints `CHAOSFOLK_WEB_SNAPSHOT=snap_...`. Add that value to the
project and redeploy. Run it again after updating Chaosfolk or the files in `sandbox/`.

### 4. Landing page on GitHub Pages

Pages is enabled with **GitHub Actions** as the source. `site/config.js` points `apiBase` to
`https://chaosfolk-web.vercel.app`; set `turnstileSiteKey` to enable Turnstile. An empty `apiBase`
closes the form and points visitors to the installation instructions. Each push to `main` that
touches `site/` publishes it to `https://loukan42.github.io/chaosfolk/`.

### 5. First audits

Run two or three audits on your own sites. Check in OpenRouter's activity page how many requests
one audit used, and in Vercel's usage page the Sandbox CPU. Then set `CHAOSFOLK_WEB_DAILY_QUOTA`.

## Operate

- Logs: the function's Runtime Logs in Vercel. Agent logs stay inside the sandbox and are lost with
  it; to debug a run, create a sandbox from the snapshot with the Vercel CLI and run
  `/opt/chaosfolk/run-audit.sh` by hand.
- Abuse report: hash the IP with the `cf:salt` value to find its audits.
- An audit stuck without a sandbox is failed after 3 minutes; a running one after its time limit
  plus 15 minutes.
