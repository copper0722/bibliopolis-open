"""Where a hand-built world lives on disk: the home folder, a SQLite file, and the world file (bibliopolis.journal) that moves a world between stores.

    home() -> (folder, created)     the folder of the player's worlds: $BIBLIOPOLIS_HOME, else ~/Bibliopolis, made on first use
    Store.create(path, rule)        a new SQLite world; Store.import_journal(path, journal) makes one from a journal
    Store(path).journal()           the journal of the world in the file (every event appended again, under the rules of `append`)
    Store(path).append(event)       one more event, one transaction
    Store(path).export_text()       the world file text of the world in the file

The SQLite file holds the same content as a world file in three tables: `world` (one row: format, version and the rule the world started with), `event` (one row for
each event: seq, at, kind, and the payload as the canonical JSON text) and `item` (the metadata of each add_item event, by the seq of the event, as the canonical JSON
text). The event log is append-only: the file refuses an update or a delete of a row. Nothing else is stored; the city is the fold of the events. A world file that is read
into a store and written out again is the same bytes, and so is a store written out to a world file and read back.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .canonical import dumps
from .events import Refusal
from .journal import FORMAT, VERSION, Journal, WorldFileError, dumps_world, world_document

HOME_ENV = "BIBLIOPOLIS_HOME"
WORLD_NAME = "world.sqlite"  # the world of the home folder: one file, one city

SCHEMA = (
    "CREATE TABLE world (id INTEGER PRIMARY KEY CHECK (id = 1), format TEXT NOT NULL, version INTEGER NOT NULL, rule TEXT NOT NULL)",
    "CREATE TABLE event (seq INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE item (seq INTEGER PRIMARY KEY REFERENCES event (seq), id TEXT NOT NULL, json TEXT NOT NULL)",
    "CREATE INDEX item_id ON item (id)",
    *(f"CREATE TRIGGER {table}_{verb} BEFORE {verb.upper()} ON {table} BEGIN SELECT RAISE(ABORT, 'a world is append-only: {table} rows are not {verb}d'); END"
      for table in ("world", "event", "item") for verb in ("update", "delete")),
)


def home() -> tuple[Path, bool]:
    """The folder of the player's worlds, and whether this call made it: `$BIBLIOPOLIS_HOME` when that is set, else `Bibliopolis` in the home folder of the user. It is made
    (with the folders above it) on first use."""
    given = os.environ.get(HOME_ENV)
    folder = Path(given).expanduser() if given else Path.home() / "Bibliopolis"
    created = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    return folder, created


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    return db


class Store:
    """A SQLite file that holds a world."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    # ---- making one
    @classmethod
    def create(cls, path: str | Path, rule: dict | None = None) -> "Store":
        """A new world in a new file; `Refusal` when the file is there already (a world is never overwritten)."""
        return cls.import_journal(path, Journal(rule))

    @classmethod
    def import_journal(cls, path: str | Path, journal: Journal) -> "Store":
        """A new file with the world of `journal`, all or nothing: the file is not left behind when something goes wrong. `Refusal` when the file is there already."""
        store = cls(path)
        if store.path.exists():
            raise Refusal(f"{store.path} is there already; a world is not overwritten (choose another file with --world, or move that one away)")
        store.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(_connect(store.path)) as db, db:
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute("INSERT INTO world (id, format, version, rule) VALUES (1, ?, ?, ?)", (FORMAT, VERSION, dumps(journal.rule)))
                for e in journal.events:
                    cls._insert(db, e)
        except BaseException:
            store.path.unlink(missing_ok=True)
            raise
        return store

    @staticmethod
    def _insert(db: sqlite3.Connection, event: dict) -> None:
        db.execute("INSERT INTO event (seq, at, kind, payload) VALUES (?, ?, ?, ?)", (event["seq"], event["at"], event["kind"], dumps(event["payload"])))
        if event["kind"] == "add_item":
            item = event["payload"]["item"]
            db.execute("INSERT INTO item (seq, id, json) VALUES (?, ?, ?)", (event["seq"], item["id"], dumps(item)))

    # ---- reading and writing
    def journal(self) -> Journal:
        """The journal of the world in the file: its rule, then every event appended in turn under the rules of `append`, then the `item` table checked against the events.
        `WorldFileError` when the file is not a world of this program, or its content is not a world."""
        if not self.path.is_file():
            raise WorldFileError(f"{self.path}: there is no world here (make one with `world new`, or read a world file with `world import`)")
        try:
            with closing(_connect(self.path)) as db:
                head = db.execute("SELECT format, version, rule FROM world").fetchall()
                events = db.execute("SELECT seq, at, kind, payload FROM event ORDER BY seq").fetchall()
                items = db.execute("SELECT seq, id, json FROM item ORDER BY seq").fetchall()
        except sqlite3.DatabaseError as exc:
            raise WorldFileError(f"{self.path}: not a world of this program ({exc})") from None
        if len(head) != 1 or head[0][0] != FORMAT or head[0][1] != VERSION:
            raise WorldFileError(f"{self.path}: not a world of this program: its world table must hold one row, {FORMAT!r} version {VERSION}")
        try:
            rule = json.loads(head[0][2])
            log = [{"seq": seq, "at": at, "kind": kind, "payload": json.loads(payload)} for seq, at, kind, payload in events]
            kept = [(seq, id_, json.loads(text)) for seq, id_, text in items]
        except json.JSONDecodeError as exc:
            raise WorldFileError(f"{self.path}: a row does not hold JSON ({exc})") from None
        try:
            journal = Journal.replay(rule, log)
        except Refusal as why:
            raise WorldFileError(f"{self.path}: {why}") from None
        if kept != [(e["seq"], e["payload"]["item"]["id"], e["payload"]["item"]) for e in journal.events if e["kind"] == "add_item"]:
            raise WorldFileError(f"{self.path}: the item table is not the items of the add_item events")
        return journal

    def append(self, event: dict) -> None:
        """Write one event, which a journal has taken (`Journal.append` returned it): the next number only, one transaction. `Refusal` for any other."""
        with closing(_connect(self.path)) as db, db:
            (last,) = db.execute("SELECT COALESCE(MAX(seq), 0) FROM event").fetchone()
            if event["seq"] != last + 1:
                raise Refusal(f"{self.path} holds {last} events; the next is number {last + 1}, not {event['seq']}")
            self._insert(db, event)

    def export_text(self) -> str:
        """The world file text of the world in the file."""
        return dumps_world(world_document(self.journal()))
