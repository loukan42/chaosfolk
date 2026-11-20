"""Entry point of the simulated users.

A user's sheet calls this module, never `chaosfolk`. It accepts only the actions of a user
(`chaosfolk.user --key KEY h01 click r12`) and the help: no leader command (serve, launch, replay,
integrations...). The operator can approve this one command for the whole session without approving, by the
same token, a command that starts a process (`serve --app-command`) or an external executable.

`--key` is the key of that user alone, written in its sheet. The engine refuses an action whose key does not
match the user it targets: a user cannot act in the browser of another one or end its session.
"""
import os
import re
import sys
from pathlib import Path

# A user id: h01, e0, t01, h00101... Never a command or an option.
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")
KEY = re.compile(r"[0-9a-f]{32}")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--state-dir"]:
        if len(args) < 3:
            print("Usage: chaosfolk.user [--state-dir DIRECTORY] [--key KEY] USER ACTION ...", file=sys.stderr)
            return 2
        os.environ["CHAOSFOLK_HOME"] = os.path.abspath(args[1])
        args = args[2:]
    if args[:1] == ["--key"]:
        if len(args) < 3 or not KEY.fullmatch(args[1]):
            print("Usage: chaosfolk.user [--state-dir DIRECTORY] --key KEY USER ACTION ...", file=sys.stderr)
            return 2
        os.environ["CHAOSFOLK_USER_KEY"] = args[1]
        args = args[2:]
    from . import engine
    from .cli import DIRECT_COMMANDS, EXTENSIONS
    engine.FICHIER_ACTIF = Path(os.environ.get("CHAOSFOLK_HOME", str(Path.home() / ".chaosfolk"))) / "active.json"
    if not args or args[0] in ("help", "-h", "--help"):
        return engine.principal(["help"])
    if args[0] in engine.COMMANDES_CHEF or args[0] in EXTENSIONS or args[0] in DIRECT_COMMANDS \
            or not IDENTIFIER.fullmatch(args[0]):
        print(f'chaosfolk.user: "{args[0]}" is not a user action. Leader commands go through `chaosfolk`.',
              file=sys.stderr)
        return 2
    try:
        return engine.principal(args)
    except (OSError, ValueError) as error:
        print(f"chaosfolk.user: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
