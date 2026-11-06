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

# Cap the agent's model requests (one request per step) and keep it from starting subagents,
# which would each spend their own requests. Free OpenRouter models allow 50 requests a day.
python3 - "${CHAOSFOLK_AGENT_STEPS:-40}" <<'PY'
import json, os, sys
path = os.path.expanduser("~/.config/opencode/opencode.json")
config = json.load(open(path, encoding="utf-8"))
build = config.setdefault("agent", {}).setdefault("build", {})
build["steps"] = int(sys.argv[1])
build.setdefault("permission", {})["task"] = {"*": "deny"}
json.dump(config, open(path, "w", encoding="utf-8"), indent=2)
PY

# The limits are set here, before the agent starts: the engine enforces them whatever the model does.
chaosfolk audit-run init --folder "$run" --depth quick --max-seconds "$seconds" --max-actions "$actions"
chaosfolk audit-run start --folder "$run"

# Python fills the template: sed would treat "&" and "|" in a URL query as special characters.
prompt=$(P_URL="$url" P_LANG="$lang" P_USERS="$users" P_PROJECT="$project" P_RUN="$run" python3 -c '
import os
text = open("/opt/chaosfolk/prompt.md", encoding="utf-8").read()
os.environ["P_STEPS"] = os.environ.get("CHAOSFOLK_AGENT_STEPS", "40")
for key in ("URL", "LANG", "USERS", "PROJECT", "RUN", "STEPS"):
    text = text.replace("{" + key + "}", os.environ["P_" + key])
print(text)')

status=0
timeout --kill-after=30 "$((seconds + 300))" \
  opencode run --auto -m "$CHAOSFOLK_MODEL" "$prompt" >"$work/agent.log" 2>&1 || status=$?

echo "agent exit code $status" >>"$work/agent.log"

# Whatever the agent did, close the engine and try to leave a partial report behind.
# Each step has its own limit, so a stuck engine cannot keep the sandbox until it is killed.
timeout 60 chaosfolk audit-run stop --folder "$run" >/dev/null 2>&1 || true
timeout 60 chaosfolk stop >/dev/null 2>&1 || true
if [ ! -f "$run/rapport.html" ]; then
  timeout 180 chaosfolk report --folder "$run" --lang "$lang" >"$work/report.log" 2>&1 || true
fi

python3 "$root/pack.py" "$run" "$work/report.zip" "$archive" "$url" || {
  echo "no report, agent exit code $status" >&2
  exit 1
}
