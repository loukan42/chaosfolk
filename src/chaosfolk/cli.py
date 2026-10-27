"""Public command line entry point; browser imports stay lazy."""
import os
import sys

from . import __version__


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
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
    if args and args[0] == "install-browser":
        # Use the engine's own interpreter so pipx, uv tool and venv installs all get the matching browser.
        import subprocess
        return subprocess.call([sys.executable, "-m", "playwright", "install", "chromium", *args[1:]])
    # Select a state directory before importing the engine. Each separate agent
    # session must inherit the same CHAOSFOLK_HOME when running concurrently.
    if args and args[0] == "--state-dir":
        if len(args) < 3:
            print("Usage: chaosfolk --state-dir DIRECTORY COMMAND", file=sys.stderr)
            return 2
        os.environ["CHAOSFOLK_HOME"] = os.path.abspath(args[1])
        args = args[2:]
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
