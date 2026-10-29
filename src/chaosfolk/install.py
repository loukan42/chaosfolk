"""`chaosfolk setup`: browser, agent skill and Claude Code user definition in one idempotent step."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_NAME = "chaosfolk"
USER_AGENT = "chaosfolk-user"
# The skill's files, relative to the repository root; setup.py bundles them in the wheel as chaosfolk/skill/.
SKILL_FILES = ["SKILL.md", "LICENSE", "docs/audit-runs.md", "docs/agents.md", "docs/benchmark.md", "docs/campaigns.md", "docs/checks.md",
               "docs/faults.md", "docs/chaos.md", "docs/integrations.md", "docs/planning.md", "docs/regression.md",
               "docs/replay.md", "docs/scoring.md", "docs/workflow.md"]

# Agent id: (name, folder whose presence means the agent is installed, global skill folder), relative to home.
# Global folders follow the Skills CLI table: https://github.com/vercel-labs/skills/blob/main/docs/agents.md
AGENTS = {
    "claude-code": ("Claude Code", ".claude", ".claude/skills"),
    "codex": ("Codex", ".codex", ".agents/skills"),
    "cursor": ("Cursor", ".cursor", ".cursor/skills"),
    "github-copilot": ("GitHub Copilot", ".copilot", ".copilot/skills"),
    "gemini-cli": ("Gemini CLI", ".gemini", ".gemini/skills"),
    "opencode": ("OpenCode", ".config/opencode", ".config/opencode/skills"),
    "windsurf": ("Windsurf", ".codeium/windsurf", ".codeium/windsurf/skills"),
}
# Read by Codex, Cline, Warp, Zed and other agents that follow the shared `.agents` convention.
UNIVERSAL = ".agents/skills"


def skill_source():
    """The bundled skill in an installed wheel, or the repository root in a development checkout."""
    bundled = HERE / "skill"
    if (bundled / "SKILL.md").exists():
        return bundled
    root = HERE.parents[1]
    return root if all((root / name).is_file() for name in SKILL_FILES) else None


def detected(home):
    return [agent for agent, (_, marker, _) in AGENTS.items() if (home / marker).is_dir()]


def is_chaosfolk(folder):
    skill = folder / "SKILL.md"
    if not skill.is_file():
        return False
    with skill.open(encoding="utf-8-sig", errors="replace") as stream:
        head = stream.read(4096)
    # A mention in the body or another skill's name must never authorize deletion.
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---(?:\s|$)", head, re.S)
    if frontmatter is None:
        return False
    names = re.findall(r"^name:\s*([^\r\n]+)", frontmatter.group(1), re.M)
    return len(names) == 1 and names[0].strip() in {SKILL_NAME, f'"{SKILL_NAME}"', f"'{SKILL_NAME}'"}


def copy_skill(source, target):
    """Stage a complete skill before replacement, restoring the old copy if publishing fails."""
    source, target = Path(source), Path(target)
    linked = target.is_symlink() or target.is_junction()
    if target.exists() and not linked and not is_chaosfolk(target):
        return f"skipped: {target.as_posix()} holds another skill"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Siblings stay on the same filesystem, where directory rename is atomic.
    staging = Path(tempfile.mkdtemp(prefix=".chaosfolk-setup-", dir=target.parent)).resolve()
    fresh, previous = staging / "new", staging / "previous"
    try:
        for name in SKILL_FILES:
            destination = fresh / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)
        if linked or target.exists():
            target.replace(previous)
        try:
            fresh.replace(target)
        except BaseException:
            if previous.exists() or previous.is_symlink() or previous.is_junction():
                try:
                    previous.replace(target)
                except OSError as error:
                    raise OSError(f"Could not restore the previous skill; backup kept at {previous}") from error
            raise
        # Only delete the saved entry after the new skill is in place. Links are
        # removed themselves; their external targets must remain untouched.
        if previous.is_symlink():
            previous.unlink()
        elif previous.is_junction():
            os.rmdir(previous)
        elif previous.exists():
            shutil.rmtree(previous)
    finally:
        # Preserve the backup if rollback or cleanup failed, including broken links.
        if not (previous.exists() or previous.is_symlink() or previous.is_junction()):
            shutil.rmtree(staging)
    return f"installed in {target.as_posix()}"


def install_user_agent(home):
    """Claude Code's simulated user definition; a customized copy is kept."""
    source = HERE / "templates" / "agent.md"
    target = home / ".claude" / "agents" / f"{USER_AGENT}.md"
    if target.exists():
        if target.read_bytes() == source.read_bytes():
            return "up to date"
        return f"kept your edited copy ({target.as_posix()}); `chaosfolk install-agent --force` replaces it"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return f"installed in {target.as_posix()}"


def browser_ready():
    import asyncio
    from .engine import tester_navigateur
    try:
        channel, version = asyncio.run(tester_navigateur())
    except Exception:
        return None
    return f"{channel} {version}" if channel else None


def ensure_browser():
    found = browser_ready()
    if found:
        return f"ready ({found})"
    print("Downloading Chromium for Chaosfolk, about 150 MB...", flush=True)
    code = subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])
    found = browser_ready() if code == 0 else None
    if found:
        return f"ready ({found})"
    hint = " On Linux, run `chaosfolk install-browser --with-deps` for the system libraries." \
        if sys.platform.startswith("linux") else ""
    return "missing: run `chaosfolk install-browser`." + hint


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="chaosfolk setup",
        description="Install the browser and add the Chaosfolk skill to your coding agents. Safe to run again "
                    "after an update.")
    parser.add_argument("--agent", action="append", choices=[*AGENTS, "universal"],
                        help="install for this agent only (repeatable); default: every agent found")
    parser.add_argument("--skip-browser", action="store_true", help="do not check or download the browser")
    parser.add_argument("--home", type=Path, default=None, help=argparse.SUPPRESS)  # tests and CI
    opts = parser.parse_args(argv)
    home = (opts.home or Path.home()).resolve()

    problems = 0
    if not opts.skip_browser:
        status = ensure_browser()
        problems += status.startswith("missing")
        print(f"Browser: {status}")

    source = skill_source()
    if source is None:
        print("Skill: files missing from this installation. Reinstall Chaosfolk.")
        return 1
    agents = opts.agent or detected(home)
    if not agents:
        print("No coding agent found in your home folder; installing the skill in the shared ~/.agents/skills.")
        print("Use --agent to choose one, for example: chaosfolk setup --agent claude-code")
        agents = ["universal"]
    done = set()
    for agent in agents:
        name, _, folder = AGENTS.get(agent, ("Shared agents folder", None, UNIVERSAL))
        target = home / folder / SKILL_NAME
        if target in done:
            print(f"{name}: skill shared with an agent above")
            continue
        done.add(target)
        status = copy_skill(source, target)
        problems += status.startswith("skipped")
        print(f"{name}: skill {status}")
        if agent == "claude-code":
            print(f"Claude Code: simulated user {install_user_agent(home)}")

    print("\nRestart your coding agent, then ask it: Run chaosfolk check and tell me if anything is missing."
          if not problems else "\nSome steps need your attention; see the lines above.")
    return 1 if problems else 0
