#!/bin/sh
# Runs one audit inside a sandbox restored from the prepared snapshot (see build_snapshot.py).
# Arguments: URL LANG MAX_SECONDS MAX_ACTIONS USERS PROJECT ARCHIVE_NAME
# Exit 0 only when /opt/chaosfolk/work/report.zip exists.
set -eu

url="$1"; lang="$2"; seconds="$3"; actions="$4"; users="$5"; project="$6"; archive="$7"
root=/opt/chaosfolk
work="$root/work"
run="$work/run"
rm -rf "$work"
mkdir -p "$work"
cd "$work"

chaosfolk check >"$work/check.log" 2>&1 || true

# The limits are set here, before the agent starts: the engine enforces them whatever the model does.
chaosfolk audit-run init --folder "$run" --depth quick --max-seconds "$seconds" --max-actions "$actions"
chaosfolk audit-run start --folder "$run"

# Python fills the template: sed would treat "&" and "|" in a URL query as special characters.
prompt=$(P_URL="$url" P_LANG="$lang" P_USERS="$users" P_PROJECT="$project" P_RUN="$run" python3 -c '
import os
text = open("/opt/chaosfolk/prompt.md", encoding="utf-8").read()
for key in ("URL", "LANG", "USERS", "PROJECT", "RUN"):
    text = text.replace("{" + key + "}", os.environ["P_" + key])
print(text)')

status=0
timeout --kill-after=30 "$((seconds + 300))" \
  opencode run --auto -m "$CHAOSFOLK_MODEL" "$prompt" >"$work/agent.log" 2>&1 || status=$?

# Whatever the agent did, close the engine and try to leave a report behind.
chaosfolk audit-run stop --folder "$run" >/dev/null 2>&1 || true
chaosfolk stop >/dev/null 2>&1 || true
if [ ! -f "$run/rapport.html" ]; then
  chaosfolk report --folder "$run" --lang "$lang" >"$work/report.log" 2>&1 || true
fi

python3 "$root/pack.py" "$run" "$work/report.zip" "$archive" "$url" || {
  echo "no report, agent exit code $status" >&2
  exit 1
}
