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
    try:
        return engine.principal(args)
    except (OSError, ValueError) as error:
        print(f"chaosfolk: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Use chaosfolk stop to close an active session.", file=sys.stderr)
        return 130
