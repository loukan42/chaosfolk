#!/bin/sh
# Installs Chaosfolk, Chromium and OpenCode under /opt/chaosfolk in a fresh Vercel Sandbox
# (Ubuntu with sudo). build_snapshot.py runs it once, then saves the result as a snapshot.
# Arguments: CHAOSFOLK_REF OPENCODE_VERSION
set -eu

ref="${1:-main}"
opencode_version="${2:-latest}"
root=/opt/chaosfolk
files=/tmp/chaosfolk-setup

sudo mkdir -p "$root"
sudo chown "$(id -u):$(id -g)" "$root"
cp "$files/run-audit.sh" "$files/prompt.md" "$files/opencode.json" "$files/pack.py" "$root/"
chmod 0755 "$root/run-audit.sh"

python3 -m venv "$root/venv"
"$root/venv/bin/pip" install --quiet --upgrade pip
"$root/venv/bin/pip" install --quiet "chaosfolk @ git+https://github.com/loukan42/chaosfolk.git@$ref"

export PLAYWRIGHT_BROWSERS_PATH="$root/browsers"
# Playwright's dependency list may lag behind the newest Ubuntu; fall back to the usual Chromium libraries.
sudo env PLAYWRIGHT_BROWSERS_PATH="$root/browsers" "$root/venv/bin/python" -m playwright install-deps chromium || {
  sudo apt-get update -q
  sudo apt-get install -y -q libnss3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libasound2t64 fonts-liberation
}
"$root/venv/bin/python" -m playwright install chromium

npm install --global --prefix "$root/npm" --silent "opencode-ai@$opencode_version"
mkdir -p "$HOME/.config/opencode"
cp "$root/opencode.json" "$HOME/.config/opencode/opencode.json"

export PATH="$root/venv/bin:$root/npm/bin:$PATH"
chaosfolk setup --agent opencode --skip-browser
chaosfolk --version
opencode --version
chaosfolk check || true
echo "Sandbox ready."
