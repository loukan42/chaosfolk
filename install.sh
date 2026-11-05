#!/bin/sh
# Install Chaosfolk on macOS or Linux: the engine, its browser and the skill for your coding agents.
#   curl -LsSf https://raw.githubusercontent.com/loukan42/chaosfolk/v0.8.0/install.sh | sh
# Run it again to update. Read docs/security.md before using it in a managed environment.
#
# Environment variables:
#   CHAOSFOLK_VERSION          release to install (default: the version this script was published with)
#   CHAOSFOLK_SOURCE           archive URL or local file instead of the GitHub release archive (internal mirror)
#   CHAOSFOLK_SHA256           expected SHA-256 of the archive; the installation stops on a mismatch
#   CHAOSFOLK_REQUIRE_UV=1     never download uv; fail when it is not already installed
#   CHAOSFOLK_UV_VERSION       uv version downloaded when uv is missing (default below)
#   CHAOSFOLK_UV_SHA256        expected SHA-256 of that version's uv installer script (required with CHAOSFOLK_UV_VERSION)
#   CHAOSFOLK_NO_MODIFY_PATH=1 leave your shell profile unchanged
set -eu

VERSION="${CHAOSFOLK_VERSION:-0.8.0}"
SOURCE="${CHAOSFOLK_SOURCE:-https://github.com/loukan42/chaosfolk/archive/refs/tags/v$VERSION.zip}"
# The uv installer script is checked against this SHA-256 before it runs. It is the GitHub release asset
# uv-installer.sh of that version, which verifies the checksum of the uv binary it downloads.
DEFAULT_UV_VERSION="0.13.6"
DEFAULT_UV_SHA256="f7a56e7afaec49a3bcbc3ac3cdbe917e7c6ce30e0d815308a12e531aa5ef23b7"
UV_VERSION="${CHAOSFOLK_UV_VERSION:-$DEFAULT_UV_VERSION}"

fail() { echo "Chaosfolk installation stopped: $1" >&2; exit 1; }

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d ' ' -f 1
  else
    shasum -a 256 "$1" | cut -d ' ' -f 1
  fi
}

WORK="$(mktemp -d 2>/dev/null || mktemp -d -t chaosfolk)"
trap 'rm -rf "$WORK"' EXIT INT TERM

if ! command -v uv >/dev/null 2>&1; then
  [ -n "${CHAOSFOLK_REQUIRE_UV:-}" ] && fail "uv is not installed and CHAOSFOLK_REQUIRE_UV is set. Install uv or Python 3.12+ with your package manager first."
  if [ -n "${CHAOSFOLK_UV_SHA256:-}" ]; then
    UV_SHA256="$CHAOSFOLK_UV_SHA256"
  elif [ "$UV_VERSION" = "$DEFAULT_UV_VERSION" ]; then
    UV_SHA256="$DEFAULT_UV_SHA256"
  else
    fail "CHAOSFOLK_UV_VERSION=$UV_VERSION needs CHAOSFOLK_UV_SHA256, the SHA-256 of that version's uv-installer.sh."
  fi
  echo "Installing uv $UV_VERSION, which installs Python and Chaosfolk without touching your system Python..."
  UV_INSTALLER="$WORK/uv-installer.sh"
  curl -LsSf -o "$UV_INSTALLER" "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-installer.sh" || fail "uv download failed"
  UV_ACTUAL="$(sha256_of "$UV_INSTALLER")"
  [ "$UV_ACTUAL" = "$(printf '%s' "$UV_SHA256" | tr 'A-F' 'a-f')" ] || fail "uv installer checksum mismatch (expected $UV_SHA256, got $UV_ACTUAL)"
  if [ -n "${CHAOSFOLK_NO_MODIFY_PATH:-}" ]; then
    UV_NO_MODIFY_PATH=1 sh "$UV_INSTALLER" || fail "uv installation failed"
  else
    sh "$UV_INSTALLER" || fail "uv installation failed"
  fi
  PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  export PATH
fi

NAME="${SOURCE##*/}"
case "$NAME" in
  *.zip|*.tar.gz|*.tgz|*.whl) ;;
  *) NAME="chaosfolk.zip" ;;
esac
ARCHIVE="$WORK/$NAME"

case "$SOURCE" in
  http://*|https://*)
    echo "Downloading $SOURCE ..."
    curl -LsSf -o "$ARCHIVE" "$SOURCE" || fail "download failed"
    ;;
  *)
    [ -f "$SOURCE" ] || fail "$SOURCE is not a file"
    cp "$SOURCE" "$ARCHIVE"
    ;;
esac

if [ -n "${CHAOSFOLK_SHA256:-}" ]; then
  ACTUAL="$(sha256_of "$ARCHIVE")"
  [ "$ACTUAL" = "$(printf '%s' "$CHAOSFOLK_SHA256" | tr 'A-F' 'a-f')" ] || fail "archive checksum mismatch (expected $CHAOSFOLK_SHA256, got $ACTUAL)"
  echo "Archive checksum verified."
else
  echo "Note: CHAOSFOLK_SHA256 is not set; the archive is trusted from HTTPS alone. Release notes list the checksum." >&2
fi

echo "Installing the Chaosfolk engine..."
uv tool install --force --python ">=3.12" "chaosfolk @ file://$ARCHIVE"
if [ -z "${CHAOSFOLK_NO_MODIFY_PATH:-}" ]; then
  uv tool update-shell >/dev/null 2>&1 || true
fi

"$(uv tool dir --bin)/chaosfolk" setup "$@"
echo "Open a new terminal to use the chaosfolk command yourself."
