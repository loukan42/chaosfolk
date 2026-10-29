"""Exact time-window lookups for repeated fault judgments over sorted actions."""
from array import array
from bisect import bisect_left
import sqlite3


class _Journey:
    def __init__(self):
        self.first = self.last = self.recovery = None
        self.done = False

    def observe(self, action):
        stamp = action["t"]
        if self.first is None:
            self.first = stamp
        self.last = stamp
        self.done = action.get("action") == "done"
        if action.get("resultat") == "ok" and action.get("action") not in ("flag", "giveup", "think", "look"):
            self.recovery = stamp

    def outcome(self, start, end):
        if self.last is None or self.last < start or end is not None and self.first > end:
            return None
        instant = end is not None and end - start < 1000
        recovered = (instant or end is None or self.recovery is not None and self.recovery > end
                     or self.done and self.last > end)
        return not self.bad_window(start, end, instant) and recovered


class _MemoryJourney(_Journey):
    def __init__(self, actions, is_blocking):
        super().__init__()
        self.times, self.bad = array("d"), array("Q")
        for action in actions:
            self.observe(action)
            stamp = action["t"]
            # JSON integers outside binary64's exact range keep their ordering.
            if isinstance(self.times, array) and isinstance(stamp, int):
                try:
                    exact = float(stamp) == stamp
                except OverflowError:
                    exact = False
                if not exact:
                    self.times = list(self.times)
            if action.get("action") == "giveup" or action.get("action") == "flag" and is_blocking(action.get("gravite")):
                self.bad.append(len(self.times))
            self.times.append(stamp)

    def bad_window(self, start, end, instant):
        first = bisect_left(self.times, start)
        bad = bisect_left(self.bad, first)
        if bad == len(self.bad):
            return False
        position = self.bad[bad]
        return position < first + 10 if instant else end is None or self.times[position] <= end + 30000


class _DiskJourney(_Journey):
    def __init__(self, connection, identifier, actions, is_blocking):
        super().__init__()
        self.db, self.identifier = connection, identifier

        def rows():
            for action in actions:
                self.observe(action)
                bad = action.get("action") == "giveup" or action.get("action") == "flag" and is_blocking(action.get("gravite"))
                stamp = action["t"]
                if isinstance(stamp, int) and not -2**63 <= stamp < 2**63:
                    stamp = float(stamp)  # beyond SQLite integers: keep ordering instead of failing
                yield identifier, stamp, bad

        self.db.executemany("INSERT INTO actions(person,stamp,bad) VALUES (?,?,?)", rows())

    def bad_window(self, start, end, instant):
        if instant:
            row = self.db.execute("""SELECT MAX(bad) FROM
                (SELECT bad FROM actions WHERE person=? AND stamp>=? ORDER BY stamp,seq LIMIT 10)""",
                                  (self.identifier, start)).fetchone()
        else:
            sql = "SELECT 1 FROM actions WHERE person=? AND bad=1 AND stamp>=?"
            values = [self.identifier, start]
            if end is not None:
                sql += " AND stamp<=?"
                values.append(end + 30000)
            row = self.db.execute(sql + " LIMIT 1", values).fetchone()
        return bool(row and row[0])


class FaultIndex:
    """Read each affected journey once; use disk for streaming report inputs."""
    def __init__(self, storage, is_blocking):
        if storage not in ("memory", "disk"):
            raise ValueError("Fault index storage must be memory or disk")
        self.storage, self.is_blocking = storage, is_blocking
        self.journeys, self.db = {}, None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.db is not None:
            self.db.close()

    def outcome(self, user, by_user, start, end):
        if user not in self.journeys:
            actions = by_user.get(user, ())
            if self.storage == "disk":
                if self.db is None:
                    self.db = sqlite3.connect("")
                    self.db.execute("PRAGMA cache_size=-1024")
                    self.db.execute("PRAGMA journal_mode=OFF")
                    self.db.execute("PRAGMA synchronous=OFF")
                    self.db.execute("CREATE TABLE actions (seq INTEGER PRIMARY KEY, person INTEGER, stamp NUMERIC, bad INTEGER)")
                    self.db.execute("CREATE INDEX actions_time ON actions(person,stamp,seq)")
                    self.db.execute("CREATE INDEX actions_bad ON actions(person,bad,stamp)")
                journey = _DiskJourney(self.db, len(self.journeys), actions, self.is_blocking)
            else:
                journey = _MemoryJourney(actions, self.is_blocking)
            self.journeys[user] = journey
        return self.journeys[user].outcome(start, end)
