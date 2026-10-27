#!/bin/sh
# Install Chaosfolk on macOS or Linux: the engine, its browser and the skill for your coding agents.
#   curl -LsSf https://raw.githubusercontent.com/loukan42/chaosfolk/main/install.sh | sh
# Run it again to update. CHAOSFOLK_SOURCE installs another version, for example a release archive;
# CHAOSFOLK_NO_MODIFY_PATH=1 leaves your shell profile unchanged.
set -eu

SOURCE="${CHAOSFOLK_SOURCE:-https://github.com/loukan42/chaosfolk/archive/refs/heads/main.zip}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv, which installs Python and Chaosfolk without touching your system Python..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  export PATH
fi

echo "Installing the Chaosfolk engine..."
uv tool install --force --python ">=3.12" "chaosfolk @ $SOURCE"
if [ -z "${CHAOSFOLK_NO_MODIFY_PATH:-}" ]; then
  uv tool update-shell >/dev/null 2>&1 || true
fi

"$(uv tool dir --bin)/chaosfolk" setup "$@"
echo "Open a new terminal to use the chaosfolk command yourself."
