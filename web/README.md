# Hosted Quick audits

Visitors paste a URL on the landing page and get a Chaosfolk Quick audit report, with no
installation. A daily quota bounds model usage. People who need more install Chaosfolk or fork
the repository.

```
GitHub Pages (site/)  --HTTPS-->  Caddy  -->  API (FastAPI, SQLite)
                                               |
                                            worker  --docker run-->  runner container
                                                                     (Chaosfolk, Chromium, OpenCode
                                                                      on an OpenRouter model)
```

- `site/` is the static landing page, deployed by `.github/workflows/pages.yml`.
- `web/chaosfolk_web/` holds the API (`app.py`), the queue ledger (`store.py`), URL checks
  (`urls.py`), Turnstile (`turnstile.py`) and the worker (`worker.py`, `runner.py`).
- `web/runner/` builds the disposable audit container. The engine limits (Quick depth, time and
  actions) are set before the agent starts, so they hold whatever the model does.
- `web/deploy/` has the systemd units, the Caddyfile and the egress firewall script.

## What protects the service

| Risk | Measure |
| --- | --- |
| Model cost | Global daily quota, one audit per IP per day, one audit at a time, credit limit on the OpenRouter key |
| Robots | Cloudflare Turnstile on the form |
| A URL that reaches the server's network | http(s) on ports 80/443 only; local names refused; every resolved address must be public, checked at submission and again before the run; the audit network blocks private ranges, metadata and the host |
| A hostile page | One container per audit, no capabilities, memory/CPU/process limits, removed after the run; the agent may run only `chaosfolk` and a few read commands and cannot fetch URLs itself |
| Private data in reports | Only the report and its `assets/`, `captures/`, `reproductions/` are published; browser state, the audit database and logs stay on the server; reports are deleted after 7 days and marked `noindex` |
| Testing someone else's site | Consent checkbox, salted IP hash kept with each audit, small daily quota. Ownership is not verified. |

The report link is the only key to a report: anyone who has it can open it until it expires.

## Try it locally

No model, Docker or Turnstile needed: the `demo` runner ignores the URL and builds the bundled
demo report, which exercises the whole queue.

```bash
python -m venv .venv
.venv/bin/pip install -e . -r web/requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python web/dev.py
```

Open http://127.0.0.1:8080/. Data goes to `.horde/web-dev/`.

Tests:

```bash
.venv/bin/pip install pytest httpx
cd web && ../.venv/bin/python -m pytest
```

## Deploy

### 1. Landing page on GitHub Pages

1. In the repository settings, open **Pages** and choose **GitHub Actions** as the source.
2. Edit `site/config.js`: `apiBase` is the server address (for example `https://audit.example.com`),
   `turnstileSiteKey` the Turnstile site key. While `apiBase` is empty the form stays closed and
   the page points to the installation instructions.
3. Merge to `main`. The workflow publishes `site/` to `https://loukan42.github.io/chaosfolk/`.

### 2. Accounts

- **OpenRouter**: create an API key, set a credit limit on it, and choose a model that supports
  tool calls. Free models have low daily request limits and some providers keep prompts; the page
  sends them the visited pages. Check OpenRouter's current limits and the provider's data policy.
- **Cloudflare Turnstile**: create a widget for `loukan42.github.io`. The site key goes in
  `site/config.js`, the secret in the server environment.

### 3. Server

A small Linux VPS with Docker (Debian or Ubuntu), 2 vCPU and 4 GB of memory for one audit at a
time. Point a DNS name such as `audit.example.com` to it.

```bash
sudo apt install -y docker.io caddy python3-venv git
sudo git clone https://github.com/loukan42/chaosfolk.git /opt/chaosfolk
cd /opt/chaosfolk
sudo docker build -f web/runner/Dockerfile -t chaosfolk-runner .

sudo useradd --system --home /var/lib/chaosfolk-web --create-home chaosfolk-web
sudo python3 -m venv web/.venv
sudo web/.venv/bin/pip install -r web/requirements.txt

sudo install -m 0600 web/deploy/env.example /etc/chaosfolk-web.env
sudo nano /etc/chaosfolk-web.env          # key, model, public URL, Turnstile secret

sudo chmod 0755 web/deploy/egress-firewall.sh
sudo cp web/deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chaosfolk-egress chaosfolk-web-api chaosfolk-web-worker

sudo cp web/deploy/Caddyfile /etc/caddy/Caddyfile   # replace audit.example.com
sudo systemctl reload caddy
```

Open only ports 22, 80 and 443 on the server firewall. The API listens on 127.0.0.1.

Check that a container cannot reach private addresses:

```bash
sudo docker run --rm --network chaosfolk-audits --entrypoint python3 chaosfolk-runner \
  -c "import urllib.request; urllib.request.urlopen('http://169.254.169.254', timeout=3)"
```

The command must fail with a connection error.

### 4. Set the quota

The right `CHAOSFOLK_WEB_DAILY_QUOTA` is the model budget divided by what one audit uses, which is
not known yet. Run two or three audits on your own sites with a quota of 5, read the requests and
cost in the OpenRouter activity page, then adjust the value and restart the API. The counter resets
at midnight UTC.

## Operate

- Logs: `journalctl -u chaosfolk-web-worker -f`. Each audit keeps `runner.log`, `work/agent.log` and
  `work/check.log` in `/var/lib/chaosfolk-web/jobs/<id>/` until it expires.
- Abuse report: hash the IP with the salt in the `meta` table to find its audits.
- Update: `git pull`, rebuild the runner image, restart both services. A restart marks a running
  audit as failed.
