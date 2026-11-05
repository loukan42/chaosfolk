"""Pack a finished Chaosfolk session into the report archive that visitors download.

Standard library only: the same file runs on the server and inside the audit sandbox.

    python3 pack.py RUN_DIR OUT_ZIP FOLDER_NAME URL
"""
from pathlib import Path
import sys
import zipfile

# Only the report and the folders it reads are published. The session also holds browser state,
# the audit database and agent logs, which never leave the sandbox.
PUBLIC_FILES = ("rapport.html", "report-en.html", "rapport-fr.html", "logo.png")
# scenarios/ holds the recorded journeys: `chaosfolk replay scenarios/NAME.json` replays them on the
# visitor's machine, and the engine finds the session folder from the scenario's location.
PUBLIC_DIRS = ("assets", "captures", "reproductions", "scenarios")

README = """Chaosfolk report for {url}

Open rapport.html in a browser. Keep the other folders next to it: they hold the screenshots
and the session replay.

To replay a recorded journey on your machine, install Chaosfolk
(https://github.com/loukan42/chaosfolk#install), then from this folder:

    chaosfolk replay scenarios/NAME.json --times 3

Read a scenario before replaying it: it drives a real browser on the site it names.
The report may contain text and screenshots from the audited site. Share it accordingly.
"""


class NoReport(Exception):
    pass


def public_files(run_dir):
    run_dir = Path(run_dir).resolve()
    if not (run_dir / "rapport.html").is_file():
        raise NoReport("The audit ended without a report.")

    def inside(path):
        # A symlink planted by a page or the agent must not pull other files into the archive.
        return not path.is_symlink() and path.resolve().is_relative_to(run_dir)

    for name in PUBLIC_FILES:
        path = run_dir / name
        if path.is_file() and inside(path):
            yield path, name
    for name in PUBLIC_DIRS:
        folder = run_dir / name
        if not folder.is_dir() or not inside(folder):
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and inside(path):
                yield path, path.relative_to(run_dir).as_posix()


def build(run_dir, zip_path, folder, url):
    zip_path = Path(zip_path)
    partial = zip_path.with_name(zip_path.name + ".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{folder}/README.txt", README.format(url=url))
        for path, name in public_files(run_dir):
            bundle.write(path, f"{folder}/{name}")
    partial.replace(zip_path)
    return zip_path


def archive_name(host, created_at):
    safe = "".join(c if c.isalnum() or c in ".-" else "-" for c in host)[:80]
    return f"chaosfolk-{safe}-{created_at[:10]}"


def main(argv=None):
    run_dir, out, folder, url = (argv or sys.argv[1:])[:4]
    build(run_dir, out, folder, url)


if __name__ == "__main__":
    try:
        main()
    except NoReport as error:
        print(error, file=sys.stderr)
        sys.exit(2)
