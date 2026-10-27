import json
from pathlib import Path
import subprocess

import pytest

from chaosfolk import planning


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Synthetic Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "src" / "orders").mkdir(parents=True)
    (root / "src" / "orders" / "save.js").write_text("original", encoding="utf-8")
    (root / "src" / "shared.js").write_text("original", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "Fixture")
    return root


def test_change_plan_keeps_ambiguous_shared_and_untracked_changes(repo):
    before = git(repo, "rev-parse", "HEAD")
    (repo / "src" / "orders" / "save.js").write_text("changed", encoding="utf-8")
    (repo / "src" / "shared.js").write_text("changed", encoding="utf-8")
    (repo / "src" / "new.js").write_text("new", encoding="utf-8")
    data = {"routes": {"/orders/:id": {}, "/settings": {}}, "discovered": ["/help"]}
    plan = planning.plan_changes(repo, "HEAD", data)
    assert plan["base"] == before
    assert plan["routes"][0]["route"] == "/orders/:id"
    assert plan["routes"][0]["reasons"][0]["confidence"] == "low"
    assert len(plan["unmapped_changes"]) == 3
    assert plan["full_scope_recommended"] and plan["requires_review"]
    assert any(c["status"] == "?" for c in plan["changes"])
    assert git(repo, "rev-parse", "HEAD") == before
    assert (repo / "src" / "shared.js").read_text() == "changed"


def test_change_plan_matches_old_and_new_names_without_losing_renames(repo):
    git(repo, "mv", "src/orders/save.js", "src/orders/write.js")
    data = {"routes": {"/settings": {}}, "discovered": []}
    rules = {"mappings": [{"paths": ["src/orders/save.js"], "routes": ["/orders/:id/edit"],
                           "reason": "Orders mutation handler"}]}
    plan = planning.plan_changes(repo, "HEAD", data, rules, all_routes=True)
    assert plan["changes"][0]["paths"] == ["src/orders/save.js", "src/orders/write.js"]
    assert not plan["unmapped_changes"]
    assert {item["route"] for item in plan["routes"]} == {"/orders/:id/edit", "/settings"}
    assert plan["routes"][0]["reasons"][0]["confidence"] == "explicit"
    assert plan["scope"] == "all-known-routes"


def test_change_plan_handles_spaces_and_rejects_option_like_base(repo):
    path = repo / "new file with spaces.txt"
    path.write_text("test", encoding="utf-8")
    _, changes = planning.changed_files(repo, "HEAD")
    assert changes == [{"status": "?", "paths": [path.name]}]
    with pytest.raises(ValueError):
        planning.changed_files(repo, "--help")


def test_no_changes_is_not_a_passed_coverage_claim(repo):
    plan = planning.plan_changes(repo, "HEAD", {"routes": {"/": {}}})
    assert plan["routes"] == [] and plan["changes"] == []
    assert plan["requires_review"]
    assert "not coverage" in plan["note"]


def test_mappings_require_repository_patterns():
    with pytest.raises(ValueError, match="relative"):
        planning.mappings({"mappings": [{"paths": ["../outside"], "routes": ["/"]}]})
    with pytest.raises(ValueError, match="routes"):
        planning.mappings([{"paths": ["src/*"], "routes": []}])


def check(key, **values):
    return {"id": key, "expectation": "Saved project survives reload", "theme": "functional",
            "route": "/projects", "role": "editor", "state": "signed-in", **values}


def result(key, status, **values):
    return {"id": key, "status": status, "evidence": ["captures/observed.png"], **values}


def test_coverage_preserves_skips_attempts_mixed_runs_and_unplanned_results():
    plan = {"checks": [check(key) for key in ("pass", "fail", "mixed", "skip", "missing", "pending")]}
    results = {"results": [result("pass", "passed"), result("fail", "failed"), result("mixed", "failed"),
        result("mixed", "passed"), result("skip", "skipped", reason="No authorized test account"),
        result("pending", "attempted"), result("outside", "passed")]}
    data = planning.coverage(plan, results)
    assert data["summary"] == {"expected": 6, "not-tested": 2, "attempted": 1,
                               "passed": 1, "failed": 1, "inconclusive": 1}
    assert data["groups"]["role"]["editor"] == data["summary"]
    assert data["groups"]["state"]["signed-in"]["not-tested"] == 2
    assert data["checks"][3]["results"][0]["reason"] == "No authorized test account"
    assert data["unplanned_results"] == [result("outside", "passed")]
    assert results["results"][0]["status"] == "passed"


def test_coverage_does_not_let_a_pass_erase_an_incomplete_attempt():
    data = planning.coverage([check("a")], [result("a", "attempted"), result("a", "passed")])
    assert data["checks"][0]["status"] == "attempted"


@pytest.mark.parametrize("bad", [[], None, "screenshot.png", [" "]])
def test_pass_and_failure_require_explicit_evidence(bad):
    with pytest.raises(ValueError, match="evidence"):
        planning.coverage([check("a")], [result("a", "passed", evidence=bad)])


def test_coverage_rejects_invalid_status_missing_expectations_and_duplicate_ids():
    with pytest.raises(ValueError, match="Unknown result status"):
        planning.coverage([check("a")], [result("a", "success")])
    with pytest.raises(ValueError, match="unique"):
        planning.coverage([check("a"), check("a")], [])
    with pytest.raises(ValueError, match="expectation"):
        planning.coverage([{"id": "a"}], [])


def finding(key, **values):
    return {"id": key, "titre": "[double-submit] Order saved twice", "route": "/orders/42",
            "condition": "Expected exactly one record after retry", "statut": "observed",
            "preuves": {"avant": f"reproductions/{key}.json"}, **values}


def test_triage_groups_only_matching_context_preserves_status_and_every_evidence():
    first = finding("a")
    second = finding("b", route="/orders/7", statut="reproduit")
    third = finding("c", role="reader")
    data = planning.triage({"constats": [first, second, third]})
    assert len(data["groups"]) == 2
    group = data["groups"][0]
    assert group["occurrence_count"] == 2 and group["requires_review"]
    assert group["statuses"] == {"observed": 1, "reproduit": 1}
    assert [entry["finding"] for entry in group["members"]] == [first, second]
    assert data["finding_count"] == 3


def test_triage_does_not_merge_titles_without_evidence_or_distinct_error_punctuation():
    rows = [finding("a", condition=None), finding("b", condition=None),
            finding("c", condition="count == 1"), finding("d", condition="count != 1")]
    assert len(planning.triage(rows)["groups"]) == 4
    rows = [finding("a", route="https://first.test/orders/42"),
            finding("b", route="https://second.test/orders/42")]
    assert len(planning.triage(rows)["groups"]) == 2


def test_triage_allows_manual_group_and_split_without_promoting_findings():
    rows = [finding(key) for key in ("a", "b", "c")]
    rows[2]["titre"] = "A different title"
    data = planning.triage(rows, {"split": ["a"], "groups": [{"id": "same-cause", "members": ["b", "c"]}]})
    assert len(data["groups"]) == 2
    assert data["groups"][0]["grouping"] == "separate"
    assert data["groups"][1]["grouping"] == "manual"
    assert data["groups"][1]["statuses"] == {"observed": 2}
    with pytest.raises(ValueError, match="split"):
        planning.triage(rows, {"split": ["a"], "groups": [{"id": "x", "members": ["a", "b"]}]})


def test_cli_writes_json_and_protects_source_files(tmp_path, capsys):
    source = tmp_path / "findings.json"
    original = json.dumps({"constats": [finding("a"), finding("b")]})
    source.write_text(original, encoding="utf-8")
    output = tmp_path / "groups.json"
    assert planning.main(["triage", "--findings", str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["finding_count"] == 2
    assert planning.main(["triage", "--findings", str(source), "--output", str(source)]) == 2
    assert "must differ" in capsys.readouterr().err
    assert source.read_text() == original


def test_cli_change_plan_reads_real_git_state(repo, tmp_path):
    (repo / "src" / "shared.js").write_text("changed", encoding="utf-8")
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({"routes": {"/": {}}, "mappings": [
        {"paths": ["src/shared.js"], "routes": ["/"]}]}), encoding="utf-8")
    output = tmp_path / "plan.json"
    assert planning.main(["changes", "--repo", str(repo), "--base", "HEAD", "--map", str(map_file),
                          "--output", str(output)]) == 0
    assert json.loads(output.read_text())["routes"][0]["route"] == "/"
