"""Public command line entry point; browser imports stay lazy."""
import os
import sys

from . import __version__

EXTENSIONS = {"regression": "regression", "planning": "planning", "integrations": "integrations",
              "mcp": "mcp_server", "visual": "visual", "privacy": "privacy", "usage": "usage",
              "benchmark": "benchmark", "chaos": "chaos", "audit-run": "audit_session"}
# Other commands answered here, before the engine. With EXTENSIONS they are the commands a simulated user
# can never run: user.py refuses them, and a test checks that this list stays complete.
DIRECT_COMMANDS = {"demo", "plan", "probe", "themes", "checks", "setup", "install-browser", "campaign", "map"}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--state-dir":
        if len(args) < 3:
            print("Usage: chaosfolk --state-dir DIRECTORY COMMAND", file=sys.stderr)
            return 2
        os.environ["CHAOSFOLK_HOME"] = os.path.abspath(args[1])
        args = args[2:]
    extensions = EXTENSIONS
    if args and args[0] in extensions:
        import importlib
        try:
            module = importlib.import_module(f".{extensions[args[0]]}", __package__)
            return module.main(args[1:])
        except (OSError, ValueError, RuntimeError) as error:
            print(f"chaosfolk {args[0]}: {error}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            return 130
    if args == ["--version"]:
        print(f"chaosfolk {__version__}")
        return 0
    if args and args[0] == "demo":
        from .demo_runner import main as demo
        return demo(args[1:])
    if args and args[0] == "plan":
        from .budgets import main as show_plan
        return show_plan(args[1:])
    if args and args[0] == "probe":
        from .probe import main as probe
        return probe(args[1:])
    if args and args[0] == "themes":
        from .themes import main as list_themes
        return list_themes(args[1:])
    if args and args[0] == "checks":
        from .checks import main as list_checks
        return list_checks(args[1:])
    if args and args[0] == "setup":
        from .install import main as setup
        return setup(args[1:])
    if args and args[0] == "install-browser":
        # Use the engine's own interpreter so pipx, uv tool and venv installs all get the matching browser.
        allowed = {"--with-deps", "--force", "--dry-run"}
        unknown = [flag for flag in args[1:] if flag not in allowed]
        if unknown:
            print(f"chaosfolk install-browser accepts only {', '.join(sorted(allowed))}", file=sys.stderr)
            return 2
        import subprocess
        # -P: without it, "-m" looks for playwright in the current folder first, that is in the tested project.
        return subprocess.call([sys.executable, "-P", "-m", "playwright", "install", "chromium", *args[1:]])  # nosec B603 # fixed Playwright command; extra flags are an allowlist checked above
    from . import engine
    from pathlib import Path
    engine.FICHIER_ACTIF = Path(os.environ.get("CHAOSFOLK_HOME", str(Path.home() / ".chaosfolk"))) / "active.json"
    if args and args[0] == "campaign":
        from .campaigns import main as campaign
        return campaign(args[1:])
    if args and args[0] == "map":
        import argparse
        from .campaigns import command_map
        parser = argparse.ArgumentParser(prog="chaosfolk map", description="Routes and transitions seen in a session.")
        parser.add_argument("--folder", dest="dossier", required=True)
        parser.add_argument("--project", help="merge into this project's memory and show every campaign")
        return command_map(parser.parse_args(args[1:]))
    try:
        return engine.principal(args)
    except (OSError, ValueError) as error:
        print(f"chaosfolk: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Use chaosfolk stop to close an active session.", file=sys.stderr)
        return 130
