import re
from pathlib import Path

from chaosfolk import install

ROOT = Path(__file__).resolve().parents[1]


def run(tmp_path, *args):
    return install.main(["--skip-browser", "--home", str(tmp_path), *args])


def test_skill_files_cover_every_guide_the_skill_links():
    seen, todo = set(), ["SKILL.md"]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        base = Path(name).parent
        for link in re.findall(r"\]\(([^)#:]+\.md)", (ROOT / name).read_text(encoding="utf-8")):
            target = (base / link).as_posix()
            if (ROOT / target).is_file() and not target.startswith(".."):
                todo.append(target)
    assert seen <= set(install.SKILL_FILES)
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8").split()
    assert all(name in manifest for name in install.SKILL_FILES)


def test_setup_installs_for_detected_agents_only(tmp_path, capsys):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()
    assert run(tmp_path) == 0
    for folder in (".claude/skills/chaosfolk", ".agents/skills/chaosfolk"):
        assert (tmp_path / folder / "SKILL.md").is_file()
        assert (tmp_path / folder / "docs" / "checks.md").is_file()
    assert not (tmp_path / ".cursor").exists()
    agent = tmp_path / ".claude" / "agents" / "chaosfolk-user.md"
    assert agent.read_text(encoding="utf-8").startswith("---\nname: chaosfolk-user")
    assert "Restart your coding agent" in capsys.readouterr().out


def test_setup_without_agents_uses_the_shared_folder(tmp_path):
    assert run(tmp_path) == 0
    assert (tmp_path / ".agents" / "skills" / "chaosfolk" / "SKILL.md").is_file()


def test_setup_refreshes_its_skill_and_keeps_edited_agent(tmp_path, capsys):
    target = tmp_path / ".claude" / "skills" / "chaosfolk"
    assert run(tmp_path, "--agent", "claude-code") == 0
    (target / "docs" / "old.md").write_text("stale", encoding="utf-8")
    agent = tmp_path / ".claude" / "agents" / "chaosfolk-user.md"
    agent.write_text(agent.read_text(encoding="utf-8").replace("model: sonnet", "model: haiku"), encoding="utf-8")
    assert run(tmp_path, "--agent", "claude-code") == 0
    assert not (target / "docs" / "old.md").exists()
    assert "model: haiku" in agent.read_text(encoding="utf-8")
    assert "kept your edited copy" in capsys.readouterr().out


def test_setup_never_replaces_another_skill(tmp_path):
    other = tmp_path / ".cursor" / "skills" / "chaosfolk"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: something-else\n---\n", encoding="utf-8")
    assert run(tmp_path, "--agent", "cursor") == 1
    assert "something-else" in (other / "SKILL.md").read_text(encoding="utf-8")
