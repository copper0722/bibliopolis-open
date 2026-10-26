"""Where a hand-built world lives on disk: the home folder, a SQLite file, and the world file (bibliopolis.journal) that moves a world between stores.

    home() -> (folder, created)     the folder of the player's worlds: $BIBLIOPOLIS_HOME, else ~/Bibliopolis, made on first use
    Store.create(path, rule)        a new SQLite world; Store.import_journal(path, journal) makes one from a journal; neither ever writes over a file
    Store(path).journal()           the journal of the world in the file (every event appended again, under the rules of `append`)
    Store(path).append(event)       one more event, one transaction
    Store(path).export_text()       the world file text of the world in the file
    check_output(path, world)       before a file is written at `path`: `Refusal` when `path` is the world at `world`, a SQLite file, or anything else that is there
    publish_text(path, text)        write `text` to a new file at `path`, never over a file that is there (`world export`, `world fold`)

The SQLite file holds the same content as a world file in three tables: `world` (one row: format, version and the rule the world started with), `event` (one row for
each event: seq, at, kind, and the payload as the canonical JSON text) and `item` (the metadata of each add_item event, by the seq of the event, as the canonical JSON
text). The event log is append-only: the file refuses an update, a delete or a replace of a row. Nothing else is stored; the city is the fold of the events. A world file that is read
into a store and written out again is the same bytes, and so is a store written out to a world file and read back.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import tempfile
from contextlib import closing
from pathlib import Path

from .canonical import dumps
from .events import Refusal
from .inputs import _shown
from .journal import FORMAT, VERSION, Journal, WorldFileError, dumps_world, world_document

HOME_ENV = "BIBLIOPOLIS_HOME"
WORLD_NAME = "world.sqlite"  # the world of the home folder: one file, one city
SQLITE_MAGIC = b"SQLite format 3\x00"  # how every SQLite database file begins

SCHEMA = (
    "CREATE TABLE world (id INTEGER PRIMARY KEY CHECK (id = 1), format TEXT NOT NULL, version INTEGER NOT NULL, rule TEXT NOT NULL)",
    "CREATE TABLE event (seq INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE item (seq INTEGER PRIMARY KEY REFERENCES event (seq), id TEXT NOT NULL, json TEXT NOT NULL)",
    "CREATE INDEX item_id ON item (id)",
    *(f"CREATE TRIGGER {table}_{verb} BEFORE {verb.upper()} ON {table} BEGIN SELECT RAISE(ABORT, 'a world is append-only: {table} rows are not {verb}d'); END"
      for table in ("world", "event", "item") for verb in ("update", "delete")),
    # `INSERT OR REPLACE` (and `REPLACE INTO`) deletes the row in its way without firing the delete trigger, and `OR IGNORE` and `ON CONFLICT` would pass over it: a row that is there is not
    # inserted again under any form of the statement, so history cannot be rewritten by insert
    *(f"CREATE TRIGGER {table}_replace BEFORE INSERT ON {table} WHEN EXISTS (SELECT 1 FROM {table} WHERE {key} = NEW.{key}) "
      f"BEGIN SELECT RAISE(ABORT, 'a world is append-only: {table} rows are not replaced'); END" for table, key in (("world", "id"), ("event", "seq"), ("item", "seq"))),
)


def home() -> tuple[Path, bool]:
    """The folder of the player's worlds, and whether this call made it: `$BIBLIOPOLIS_HOME` when that is set, else `Bibliopolis` in the home folder of the user. It is made
    (with the folders above it) on first use."""
    given = os.environ.get(HOME_ENV)
    folder = Path(given).expanduser() if given else Path.home() / "Bibliopolis"
    created = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    return folder, created


def _same_file(a: Path, b: Path) -> bool:
    """Whether two names are one file: the same path once every link is followed (the file need not be there), or the same file on the disk (a hard link, a spelling that the
    system takes for the same, such as another case on a system that ignores it)."""
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:  # one of them is not there
        return False


def output_taken(path: Path) -> Refusal:
    """The refusal when a file is to be written at `path` and something is there already (a file, a folder, a link, a link that leads nowhere)."""
    return Refusal(f"{path} is there already; a file is not written over (choose another file, or move that one away)", "output_exists", path=str(path))


def check_output(path: str | Path, world: str | Path) -> None:
    """Call this before a file is written at `path` by a command that reads the world in the file `world` (`world export`, `world fold`), to spare the work and say what the file is.
    `Refusal` (`output_is_the_world`) when `path` is that file under any name, since the world would be replaced by the text written from it; `Refusal` (`output_is_a_database`) when
    `path` is a SQLite database already, a world or not; `Refusal` (`output_exists`) when anything else is there. Nothing is touched. This is a look, not the guard: a file that appears
    after it is met by `publish_text`, which never writes over a file."""
    out, source = Path(path), Path(world)
    if _same_file(out, source):
        raise Refusal(f"{out} is the world that is being read ({source}); a world is not written over (choose another file)", "output_is_the_world", path=str(out), world=str(source))
    if out.is_file():
        with open(out, "rb") as f:
            if f.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC:
                raise Refusal(f"{out} is a SQLite database already; a world is not written over (choose another file, or move that one away)", "output_is_a_database", path=str(out))
    if os.path.lexists(out):
        raise output_taken(out)


def _new_file_mode(base: int) -> int:
    """The permissions that a file gets when it is made asking for `base` (0o666 for text, 0o644 for a SQLite file): the umask of this user takes its bits away."""
    umask = os.umask(0)
    os.umask(umask)
    return base & ~umask


def temp_file(folder: Path, name: str, base: int = 0o666) -> tuple[int, Path]:
    """A new, empty file in `folder` for the file `name` to be written to before it is published. It is made by `tempfile.mkstemp`: exclusively and under a random name, so it is never a
    file that was there (a world or a city that is called what a temporary file used to be called is never opened) and its name cannot be guessed. It has the permissions that any file made
    by this user gets (`base` less the bits of the umask), not the private ones of mkstemp. Returns the open descriptor, which the caller closes, and the path."""
    fd, made = tempfile.mkstemp(dir=folder, prefix=f".{name}.", suffix=".part")
    temp = Path(made)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, _new_file_mode(base))
    except BaseException:
        os.close(fd)
        temp.unlink(missing_ok=True)
        raise
    return fd, temp


def _remove_if_ours(path: Path, made: os.stat_result) -> None:
    """Remove `path` if it is still the file that was made (`made` is the stat of its descriptor: the same device and inode); a file that has taken the name since is not ours to remove.
    (The name could change hands once more between the look and the removal; no system call removes a file by what it is.)"""
    try:
        now = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return
    if os.path.samestat(made, now):
        path.unlink(missing_ok=True)


def _publish(temp: Path, dest: Path) -> None:
    """Make the finished file `temp` the file `dest` without ever replacing a file that is there: `FileExistsError` when something is (a file, a folder, a link, a link that leads
    nowhere), however late it came. A hard link does it in one step, whole or not at all, and the caller removes `temp` after. On a file system that has no hard links (`os.link` fails
    with anything but `FileExistsError`) `dest` is made with `O_CREAT | O_EXCL`, so it is still never a file that was there, and `temp` is copied into it with its permissions; that takes
    time, so a reader can see part of the file, and a failed copy removes `dest` if it is still the file that was made here, and nothing else."""
    try:
        os.link(temp, dest)
        return
    except FileExistsError:
        raise
    except OSError:
        pass
    with open(temp, "rb") as src:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
        made = os.fstat(fd)
        try:
            with os.fdopen(fd, "wb") as out:
                if hasattr(os, "fchmod"):
                    os.fchmod(out.fileno(), stat.S_IMODE(os.fstat(src.fileno()).st_mode))
                shutil.copyfileobj(src, out)
        except BaseException:
            _remove_if_ours(dest, made)
            raise


def publish_text(path: str | Path, text: str) -> None:
    """Write `text` (UTF-8, \\n line ends on every system) to a new file at `path`, never over a file that is there: `Refusal` (`output_exists`) when something is, even if it came after the
    call began. The text is written first to a file of its own in the folder of `path` (`temp_file`) and that file is published to `path` (`_publish`), so a reader never sees half a file; a
    failure removes the file of its own and nothing else. The folder is made when it is not there."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = temp_file(dest.parent, dest.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        _publish(temp, dest)
    except FileExistsError:
        raise output_taken(dest) from None
    finally:
        temp.unlink(missing_ok=True)


def _plain(value):
    """A cell as it goes into the params of an error (plain JSON): null, text and whole numbers as they are, anything else (bytes, a real) as a short text."""
    return value if value is None or isinstance(value, (str, int)) else _shown(value)


def _cell(path: Path, table: str, column: str, row: int | None, value, expected: str) -> None:
    """`WorldFileError` (`cell_wrong_type`) unless the cell `column` of the `row`-th row of `table` (`row` None: the largest of the column) is text (`expected` "text") or a whole number
    (anything else): a store made elsewhere may hold any type of value in any column, and nothing is decoded or added to before its type is right."""
    if not (isinstance(value, str) if expected == "text" else isinstance(value, int) and not isinstance(value, bool)):
        raise WorldFileError(f"{path}: {table}.{column}{'' if row is None else f' (row {row})'} must be {expected}, got {type(value).__name__}", "cell_wrong_type", path=str(path),
                             table=table, column=column, row=row, expected=expected, got=type(value).__name__)


def _decode(path: Path, text: str):
    """The JSON value of a cell of text. `WorldFileError` (`row_not_json`) when it is not JSON, holds a number of too many digits to read, or is nested too deeply to read."""
    try:
        return json.loads(text)
    except RecursionError:
        raise WorldFileError(f"{path}: a row does not hold JSON (nested too deeply to read)", "row_not_json", path=str(path), reason="nested too deeply to read") from None
    except ValueError as exc:  # not JSON (`json.JSONDecodeError`), or a number of more digits than Python reads
        raise WorldFileError(f"{path}: a row does not hold JSON ({exc})", "row_not_json", path=str(path), reason=str(exc)) from None


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
        """A new file with the world of `journal`, all or nothing: the file is not left behind when something goes wrong. `Refusal` when the file is there already.

        The world is built in a file of its own in the folder of `path` (`temp_file`) and published to `path` by `_publish`, which never writes over a file: of two calls for one path
        only one gets it, the other is refused (also when its world was finished second), a name that is a link to a file or to nothing is a taken name, and `path` has the world only
        when it is whole. A failure removes the file of its own and nothing else: the path is never removed, since by then it may be another call's world."""
        store = cls(path)
        if os.path.lexists(store.path):  # a quick look, to spare the work and say so at once; the publishing is the guard
            raise Refusal(f"{store.path} is there already; a world is not overwritten (choose another file with --world, or move that one away)", "world_exists", path=str(store.path))
        store.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = temp_file(store.path.parent, store.path.name, 0o644)
        os.close(fd)
        try:
            with closing(_connect(temp)) as db:
                db.execute("BEGIN")  # one transaction for the tables and the rows
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute("INSERT INTO world (id, format, version, rule) VALUES (1, ?, ?, ?)", (FORMAT, VERSION, dumps(journal.rule)))
                for e in journal.events:
                    cls._insert(db, e)
                db.commit()
            _publish(temp, store.path)
        except FileExistsError:
            raise Refusal(f"{store.path} is there already; a world is not overwritten (choose another file with --world, or move that one away)", "world_exists", path=str(store.path)) from None
        finally:
            temp.unlink(missing_ok=True)
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
            raise WorldFileError(f"{self.path}: there is no world here (make one with `world new`, or read a world file with `world import`)", "no_world", path=str(self.path))
        try:
            with closing(_connect(self.path)) as db:
                db.execute("BEGIN")  # one read transaction: the three tables are read as they are at one moment, whatever another call appends in between (it waits for this one)
                head = db.execute("SELECT format, version, rule FROM world").fetchall()
                events = db.execute("SELECT seq, at, kind, payload FROM event ORDER BY seq").fetchall()
                items = db.execute("SELECT seq, id, json FROM item ORDER BY seq").fetchall()
                db.rollback()
        except sqlite3.DatabaseError as exc:
            raise WorldFileError(f"{self.path}: not a world of this program ({exc})", "not_a_world", path=str(self.path), reason=str(exc)) from None
        if len(head) != 1 or head[0][0] != FORMAT or type(head[0][1]) is not int or head[0][1] != VERSION:
            raise WorldFileError(f"{self.path}: not a world of this program: its world table must hold one row, {FORMAT!r} version {VERSION}", "world_table_wrong",
                                 path=str(self.path), format=_plain(head[0][0]) if len(head) == 1 else None, version=_plain(head[0][1]) if len(head) == 1 else None)
        _cell(self.path, "world", "rule", 1, head[0][2], "text")
        for row, (seq, at, kind, payload) in enumerate(events, start=1):
            _cell(self.path, "event", "seq", row, seq, "a whole number")
            for column, value in (("at", at), ("kind", kind), ("payload", payload)):
                _cell(self.path, "event", column, row, value, "text")
        for row, (seq, id_, text) in enumerate(items, start=1):
            _cell(self.path, "item", "seq", row, seq, "a whole number")
            _cell(self.path, "item", "id", row, id_, "text")
            _cell(self.path, "item", "json", row, text, "text")
        rule = _decode(self.path, head[0][2])
        log = [{"seq": seq, "at": at, "kind": kind, "payload": _decode(self.path, payload)} for seq, at, kind, payload in events]
        kept = [(seq, id_, _decode(self.path, text)) for seq, id_, text in items]
        try:
            journal = Journal.replay(rule, log)
        except Refusal as why:
            error = WorldFileError(f"{self.path}: {why}", why.code, **why.params)
            error.event, error.where = why.event, str(self.path)
            raise error from None
        if kept != [(e["seq"], e["payload"]["item"]["id"], e["payload"]["item"]) for e in journal.events if e["kind"] == "add_item"]:
            raise WorldFileError(f"{self.path}: the item table is not the items of the add_item events", "item_table_differs", path=str(self.path))
        return journal

    def append(self, event: dict) -> None:
        """Write one event, which a journal has taken (`Journal.append` returned it): the next number only, one transaction. `Refusal` for any other."""
        with closing(_connect(self.path)) as db, db:
            (last,) = db.execute("SELECT COALESCE(MAX(seq), 0) FROM event").fetchone()
            _cell(self.path, "event", "seq", None, last, "a whole number")  # (the largest of a column that holds text is text)
            if event["seq"] != last + 1:
                raise Refusal(f"{self.path} holds {last} events; the next is number {last + 1}, not {event['seq']}", "not_next_event", path=str(self.path), held=last,
                              next=last + 1, seq=event["seq"])
            self._insert(db, event)

    def export_text(self) -> str:
        """The world file text of the world in the file."""
        return dumps_world(world_document(self.journal()))
