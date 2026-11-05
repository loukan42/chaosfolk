"""Prepare the audit machine once and save it as a Vercel Sandbox snapshot.

Every audit then starts from this snapshot in a few seconds instead of installing Chromium again.
Run it from the web/ folder after `vercel link` and `vercel env pull` (or with VERCEL_TOKEN,
VERCEL_PROJECT_ID and VERCEL_TEAM_ID set):

    python sandbox/build_snapshot.py --ref main

It prints the snapshot id to put in the CHAOSFOLK_WEB_SNAPSHOT environment variable.
"""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
FILES = {
    "setup.sh": HERE / "setup.sh",
    "run-audit.sh": HERE / "run-audit.sh",
    "prompt.md": HERE / "prompt.md",
    "opencode.json": HERE / "opencode.json",
    "pack.py": HERE.parent / "chaosfolk_web" / "pack.py",
}


def load_env_file(path):
    """Read `vercel env pull` output without a dependency, keeping variables already set."""
    import os
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default="main", help="Chaosfolk git branch or tag to install (default: main)")
    parser.add_argument("--opencode", default="latest", help="opencode-ai npm version (pin it once a run is checked)")
    args = parser.parse_args(argv)
    load_env_file(HERE.parent / ".env.local")

    from vercel.sandbox import sync as sandbox
    from vercel.sandbox import SandboxResources

    box = sandbox.create_sandbox(execution_time_limit=2400, resources=SandboxResources(vcpus=2), persistent=False,
                                 tags={"app": "chaosfolk-web", "role": "snapshot-builder"})
    try:
        with box.fs.batch(cwd="/tmp/chaosfolk-setup") as batch:
            for name, path in FILES.items():
                batch.write_bytes(name, path.read_bytes(), mode=0o755 if name.endswith(".sh") else 0o644)
        result = box.run_command("sh", ["/tmp/chaosfolk-setup/setup.sh", args.ref, args.opencode])
        if result.returncode != 0:
            print(f"Setup failed with exit code {result.returncode}.", file=sys.stderr)
            return 1
        snapshot = box.snapshot(expiration=0)
        print(f"\nCHAOSFOLK_WEB_SNAPSHOT={snapshot.id}")
        return 0
    finally:
        # Keeps the snapshot: only orphan-snapshot deletion would remove it.
        box.destroy()


if __name__ == "__main__":
    sys.exit(main())
