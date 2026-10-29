"""Exact live evidence collections that spill to a private SQLite file.

Small sessions stay in memory. Spilling changes storage, never record counts,
ordering or values. Transactions are committed every 256 writes, at command
boundaries and when the browser closes. The session journal remains the source
for timestamped browser anomalies.
"""
from collections.abc import Mapping, MutableMapping, Sequence
from contextlib import suppress
from itertools import islice
import os
from pathlib import Path
import re
import sqlite3
import tempfile


class EvidenceStore:
    def __init__(self, folder=None, label="world", on_spill=None, limit=512, byte_limit=256 * 1024):
        self.folder = Path(folder) if folder is not None else None
        self.label = re.sub(r"[^A-Za-z0-9_-]", "_", label)[:48] or "world"
        self.on_spill = on_spill
        self.limit = limit
        self.byte_limit = byte_limit
        self.path = None
        self.connection = None
        self.pending = 0
        self.failure = None
        self._temporary = None
        self.errors = EvidenceSequence(self, "errors")
        self.messages = EvidenceSequence(self, "messages")
        self.requests = EvidenceCounter(self)

    def database(self):
        if self.connection is None:
            if self.path is None:
                if self.folder is None:
                    self._temporary = tempfile.TemporaryDirectory(prefix="chaosfolk-evidence-")
                    self.folder = Path(self._temporary.name)
                self.folder.mkdir(parents=True, exist_ok=True)
                descriptor, path = tempfile.mkstemp(prefix=f"{self.label}-", suffix=".sqlite", dir=self.folder)
                os.close(descriptor)
                self.path = Path(path)
            connection = sqlite3.connect(self.path)
            try:
                connection.execute("PRAGMA cache_size=-512")
                connection.execute("PRAGMA mmap_size=0")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=NORMAL")
                connection.executescript(
                    "CREATE TABLE IF NOT EXISTS errors (position INTEGER PRIMARY KEY, value TEXT NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS messages (position INTEGER PRIMARY KEY, value TEXT NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, value INTEGER NOT NULL, position INTEGER NOT NULL);"
                    "CREATE INDEX IF NOT EXISTS request_order ON requests(position);"
                )
            except BaseException:
                connection.close()
                raise
            self.connection = connection
        return self.connection

    def written(self):
        self.pending += 1
        if self.pending >= 256:
            self.flush()

    def flush(self):
        if self.connection is not None:
            try:
                self.connection.commit()
                self.pending = 0
            except Exception as error:
                self.failure = error
                raise

    def spilled(self, collection):
        self.flush()
        if self.on_spill is not None:
            self.on_spill({"collection": collection, "path": str(self.path), "records_preserved": True})

    def check(self):
        if self.failure is not None:
            raise RuntimeError(f"Live evidence storage failed; stop this session: {self.failure}") from self.failure

    def close(self):
        if self.connection is not None:
            try:
                self.flush()
            finally:
                self.connection.close()
                self.connection = None

    def __del__(self):
        with suppress(Exception):
            self.close()


class EvidenceSequence(Sequence):
    """Append-only string sequence with list-compatible indexing and slicing."""
    def __init__(self, store, table):
        if table not in {"errors", "messages"}:
            raise ValueError("Unknown evidence sequence")
        self.store, self.table = store, table
        self.memory = []
        self.memory_bytes = 0
        self.disk = False
        self.length = 0

    def __len__(self):
        return self.length

    def append(self, value):
        if not isinstance(value, str):
            raise TypeError("Evidence sequence values must be strings")
        self.store.check()
        if not self.disk:
            self.memory.append(value)
            self.length += 1
            self.memory_bytes += len(value) * 4 + 64
            if self.length > self.store.limit or self.memory_bytes > self.store.byte_limit:
                try:
                    database = self.store.database()
                    self.store.flush()
                    with database:
                        database.executemany(f"INSERT INTO {self.table} VALUES (?, ?)", enumerate(self.memory))
                    self.disk = True
                    self.memory.clear()
                    self.memory_bytes = 0
                    self.store.spilled(self.table)
                except Exception as error:
                    self.store.failure = error
                    raise
        else:
            try:
                self.store.database().execute(f"INSERT INTO {self.table} VALUES (?, ?)", (self.length, value))
                self.store.written()
                self.length += 1
            except Exception as error:
                self.store.failure = error
                raise

    def __iter__(self):
        if not self.disk:
            yield from self.memory
        else:
            cursor = self.store.database().execute(f"SELECT value FROM {self.table} ORDER BY position")
            try:
                for row in cursor:
                    yield row[0]
            finally:
                cursor.close()

    def __getitem__(self, index):
        if not self.disk:
            return self.memory[index]
        if isinstance(index, slice):
            indices = range(*index.indices(self.length))
            if not indices:
                return []
            lower, upper = min(indices[0], indices[-1]), max(indices[0], indices[-1])
            direction = "ASC" if indices.step > 0 else "DESC"
            cursor = self.store.database().execute(
                f"SELECT value FROM {self.table} WHERE position BETWEEN ? AND ? ORDER BY position {direction}",
                (lower, upper))
            try:
                return [row[0] for row in islice(cursor, 0, None, abs(indices.step))]
            finally:
                cursor.close()
        if not isinstance(index, int):
            raise TypeError("Sequence indices must be integers or slices")
        position = index if index >= 0 else self.length + index
        if not 0 <= position < self.length:
            raise IndexError("Evidence index out of range")
        row = self.store.database().execute(f"SELECT value FROM {self.table} WHERE position = ?", (position,)).fetchone()
        return row[0]

    def clear(self):
        if self.disk:
            try:
                self.store.database().execute(f"DELETE FROM {self.table}")
                self.store.written()
            except Exception as error:
                self.store.failure = error
                raise
        else:
            self.memory.clear()
        self.length = self.memory_bytes = 0

    def __eq__(self, other):
        return isinstance(other, Sequence) and len(self) == len(other) and all(a == b for a, b in zip(self, other))


class EvidenceCounter(MutableMapping):
    """Request counters keep exact keys, insertion order and integer values."""
    def __init__(self, store):
        self.store = store
        self.memory = {}
        self.memory_bytes = 0
        self.disk = False
        self.position = 0

    def __len__(self):
        if not self.disk:
            return len(self.memory)
        return self.store.database().execute("SELECT COUNT(*) FROM requests").fetchone()[0]

    def __iter__(self):
        if not self.disk:
            yield from self.memory
        else:
            cursor = self.store.database().execute("SELECT key FROM requests ORDER BY position")
            try:
                for row in cursor:
                    yield row[0]
            finally:
                cursor.close()

    def __getitem__(self, key):
        if not self.disk:
            return self.memory[key]
        row = self.store.database().execute("SELECT value FROM requests WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return row[0]

    def _memory_write(self, key, value):
        if key not in self.memory:
            self.memory_bytes += len(key) * 4 + 96
        self.memory[key] = value
        if len(self.memory) > self.store.limit or self.memory_bytes > self.store.byte_limit:
            database = self.store.database()
            self.store.flush()
            with database:
                database.executemany("INSERT INTO requests VALUES (?, ?, ?)",
                                     ((key, count, position) for position, (key, count) in enumerate(self.memory.items())))
            self.position = len(self.memory)
            self.disk = True
            self.memory.clear()
            self.memory_bytes = 0
            self.store.spilled("requests")

    def __setitem__(self, key, value):
        self._write(key, value, increment=False)

    def increment(self, key, amount=1):
        self._write(key, amount, increment=True)

    def _write(self, key, value, increment):
        if not isinstance(key, str) or not isinstance(value, int):
            raise TypeError("Request counters require string keys and integer values")
        self.store.check()
        try:
            if not self.disk:
                self._memory_write(key, self.memory.get(key, 0) + value if increment else value)
            else:
                update = "value + excluded.value" if increment else "excluded.value"
                self.store.database().execute(
                    f"INSERT INTO requests VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = {update}",
                    (key, value, self.position))
                self.position += 1
                self.store.written()
        except Exception as error:
            self.store.failure = error
            raise

    def __delitem__(self, key):
        if not self.disk:
            del self.memory[key]
            self.memory_bytes -= len(key) * 4 + 96
        else:
            try:
                cursor = self.store.database().execute("DELETE FROM requests WHERE key = ?", (key,))
                if cursor.rowcount == 0:
                    raise KeyError(key)
                self.store.written()
            except (sqlite3.Error, OSError) as error:
                self.store.failure = error
                raise

    def sorted_items(self):
        if not self.disk:
            yield from sorted(self.memory.items())
        else:
            cursor = self.store.database().execute("SELECT key, value FROM requests ORDER BY key")
            try:
                yield from cursor
            finally:
                cursor.close()

    def __eq__(self, other):
        return isinstance(other, Mapping) and len(self) == len(other) and all(
            key in other and other[key] == value for key, value in self.items())
