#!/bin/sh
# Entry point of the disposable audit container.
# Arguments: URL LANG MAX_SECONDS MAX_ACTIONS USERS PROJECT
set -eu

url="$1"; lang="$2"; seconds="$3"; actions="$4"; users="$5"; project="$6"
run=/work/run
cd /work
# Files belong to the container user; let the worker on the host copy and later delete them.
trap 'chmod -R a+rwX /work 2>/dev/null || true' EXIT

chaosfolk check >/work/check.log 2>&1 || true

# The limits are set here, before the agent starts: the engine enforces them whatever the model does.
chaosfolk audit-run init --folder "$run" --depth quick --max-seconds "$seconds" --max-actions "$actions"
chaosfolk audit-run start --folder "$run"

# Python fills the template: sed would treat "&" and "|" in a URL query as special characters.
prompt=$(P_URL="$url" P_LANG="$lang" P_USERS="$users" P_PROJECT="$project" python3 -c '
import os
text = open("/opt/chaosfolk/prompt.md", encoding="utf-8").read()
for key in ("URL", "LANG", "USERS", "PROJECT"):
    text = text.replace("{" + key + "}", os.environ["P_" + key])
print(text)')

status=0
timeout --kill-after=30 "$((seconds + 240))" \
  opencode run --auto -m "$CHAOSFOLK_MODEL" "$prompt" >/work/agent.log 2>&1 || status=$?

# Whatever the agent did, close the engine and try to leave a report behind.
chaosfolk audit-run stop --folder "$run" >/dev/null 2>&1 || true
chaosfolk stop >/dev/null 2>&1 || true
if [ ! -f "$run/rapport.html" ]; then
  chaosfolk report --folder "$run" --lang "$lang" >/work/report.log 2>&1 || true
fi

[ -f "$run/rapport.html" ] || { echo "no report, agent exit code $status" >&2; exit 1; }
