import json

import pytest

from chaosfolk import benchmark


def series(failures, times=3):
    return {"demandes": times, "fois": times, "casses": failures}


@pytest.mark.parametrize("seeded,fixed,control,verdict", [
    (series(3), series(0), series(0), "detected"),
    (series(0), series(0), None, "missed"),
    (series(3), series(3), None, "false-alarm"),
    (series(2), series(0), None, "flaky"),
    (series(3), series(0), series(3), "invalid"),
    ({"demandes": 3, "fois": 2, "casses": 2}, series(0), None, "invalid"),
    (None, series(0), None, "invalid"),
])
def test_classify(seeded, fixed, control, verdict):
    assert benchmark.classify(seeded, fixed, control, 3) == verdict


def test_cases_are_valid_replay_scenarios():
    from chaosfolk.schema import normalize_scenario
    cases = benchmark.load_cases()
    assert len({case["id"] for case in cases}) == len(cases) >= 4
    for case in cases:
        assert (benchmark.APPS / case["id"] / "index.html").is_file()
        assert normalize_scenario(dict(case["scenario"], url="http://127.0.0.1/"))["attendu"]
    with pytest.raises(ValueError, match="Unknown benchmark case"):
        benchmark.load_cases(["nope"])


def write_findings(tmp_path, findings):
    (tmp_path / "constats.json").write_text(json.dumps({"constats": findings}), encoding="utf-8")
    return tmp_path


def test_score_separates_matches_duplicates_and_unreviewed(tmp_path):
    folder = write_findings(tmp_path, [
        {"id": "F1", "titre": "Draft lost when storage is full"},
        {"id": "F2", "titre": "Another draft vanished"},
        {"id": "F3", "titre": "Logo is blurry"},
    ])
    result = benchmark.score(folder, benchmark.load_cases())
    assert result["found"] == 1 and result["missed"] == ["double-submit-duplicate", "offline-false-success", "reload-loses-data"]
    assert [r["status"] for r in result["rows"]] == ["true-positive", "duplicate", "unreviewed"]
    # Precision stays unknown while a finding is unreviewed.
    assert result["precision"] is None
    assert result["precision_bounds"] == [round(2 / 3, 4), 1.0]
    reviewed = benchmark.score(folder, benchmark.load_cases(), {"F3": None})
    assert reviewed["precision"] == round(2 / 3, 4)


def test_score_routes_ambiguity_to_review_and_reports_usage(tmp_path):
    folder = write_findings(tmp_path, [{"id": "F1", "titre": "Duplicate item after reload"}])
    events = [{"id": "r1", "source": "host", "input_tokens": 10, "output_tokens": 5, "cost": None}]
    result = benchmark.score(folder, benchmark.load_cases(), usage_events=events)
    assert result["rows"][0]["status"] == "unreviewed"
    assert set(result["rows"][0]["candidates"]) == {"double-submit-duplicate", "reload-loses-data"}
    assert result["usage"]["tokens"] == 15 and result["usage"]["cost"] is None
    with pytest.raises(ValueError, match="unknown case"):
        benchmark.score(folder, benchmark.load_cases(), {"F1": "typo"})


def test_cli_list_and_errors(capsys, tmp_path):
    assert benchmark.main(["list"]) == 0
    assert "reload-loses-data" in capsys.readouterr().out
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "old.json").write_text("{}", encoding="utf-8")
    assert benchmark.main(["run", "--output", str(tmp_path / "out")]) == 2
    assert "not empty" in capsys.readouterr().err


@pytest.mark.browser
def test_run_detects_seeded_defects_without_false_alarms(tmp_path):
    summary, code = benchmark.run(tmp_path / "bench", times=1)
    assert code == 0, summary
    assert summary["detected"] == summary["cases"]
    assert json.loads((tmp_path / "bench" / "benchmark.json").read_text(encoding="utf-8"))["recall"] == 1
