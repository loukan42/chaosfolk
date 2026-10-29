"""Fault indexing preserves the former window rules and reads sources once."""
from collections.abc import Mapping
import random
import sqlite3

import pytest

from chaosfolk.scoring import fault_pillar
from test_reporting_efficiency import legacy_fault_pillar


def fixture(seed, count=80, faults=25):
    rng = random.Random(seed)
    users = {f"h{n}": sorted([
        {"t": rng.randrange(0, 90000), "action": rng.choice(["click", "done", "look", "flag", "giveup"]),
         "resultat": rng.choice(["ok", "echec"]), "gravite": rng.choice(["blocking", "minor", "bloquant"])}
        for _ in range(rng.randrange(count))], key=lambda event: event["t"]) for n in range(5)}
    events = []
    for number in range(faults):
        stamp = rng.randrange(-2000, 100000)
        events.append({"type": "panne-debut", "id": number, "h": rng.choice([None, *users, "absent"]),
                       "t": stamp, "erreur": rng.choice([None, None, None, "failed"])})
        duration = rng.choice([None, 0, 999, 1000, 30000, 50000])
        if duration is not None:
            events.append({"type": "panne-fin", "id": number, "t": stamp + duration})
    return sorted(events, key=lambda event: event["t"]), users


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("storage", ["memory", "disk"])
def test_index_matches_original_fault_windows(seed, storage):
    events, users = fixture(seed)
    assert fault_pillar(events, users, storage=storage) == legacy_fault_pillar(events, users)


@pytest.mark.parametrize("storage", ["memory", "disk"])
def test_each_affected_journey_is_read_once(storage):
    events, users = fixture(4)

    class Once(Mapping):
        def __init__(self):
            self.read = set()

        def __iter__(self):
            return iter(users)

        def __len__(self):
            return len(users)

        def __getitem__(self, key):
            if key not in users:
                raise KeyError(key)
            assert key not in self.read
            self.read.add(key)
            return iter(users[key])

    assert fault_pillar(events, Once(), storage=storage) == legacy_fault_pillar(events, users)


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_disk_index_closes_on_input_failure(monkeypatch, failure):
    opened = []
    original = sqlite3.connect

    def connect(*args, **kwargs):
        db = original(*args, **kwargs)
        opened.append(db)
        return db

    def actions():
        yield {"t": 0, "action": "click", "resultat": "ok"}
        raise failure("interrupted")

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(failure):
        fault_pillar([{"type": "panne-debut", "id": "p1", "t": 0}], {"h1": actions()}, storage="disk")
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_failed_injections_do_not_open_an_index(monkeypatch):
    monkeypatch.setattr(sqlite3, "connect", lambda *_: pytest.fail("Unneeded database"))
    assert fault_pillar([{"type": "panne-debut", "id": "p1", "erreur": "failed"}], {}, storage="disk") is None


def test_memory_index_preserves_large_integer_boundaries():
    start = 2**54 + 1
    actions = [{"t": start - 1, "action": "flag", "gravite": "blocking"},
               {"t": start, "action": "click", "resultat": "ok"}]
    events = [{"type": "panne-debut", "id": "p1", "t": start}]
    assert fault_pillar(events, {"h1": actions}) == legacy_fault_pillar(events, {"h1": actions})
