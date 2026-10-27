"""Bundle the agent skill (SKILL.md and its guides) inside the package for `chaosfolk setup`."""
import shutil
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from chaosfolk.install import SKILL_FILES  # noqa: E402  MANIFEST.in lists the same files for the sdist


class BuildWithSkill(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / "chaosfolk" / "skill"
        for name in SKILL_FILES:
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)


setup(cmdclass={"build_py": BuildWithSkill})
