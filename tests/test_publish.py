"""Publishing a file without ever replacing one that is there (bibliopolis.store.publish_text, Store.import_journal): the text of `world export` and `world fold`, and the SQLite file of
`world new` and `world import`. Both are finished in a file of their own in the folder of the target, made exclusively under a random name, and published to the target by a hard link, which
fails when the target is there. Where a hard link cannot be made at all, nothing is published and the call is refused (`no_hard_links`): there is no second way that could write over a file.

The threat model of these tests (docs/world.md, "The files"): several runs of the tool by one user at once, a wrong name given to a command, a fault or an interrupt in the middle of a call,
and a file system without hard links are in; a hostile process with write access to the same folder is out (it could delete or replace the world itself, and no way of publishing stops that).
The interleavings are controlled: the other party's file appears at a chosen moment of the call, by a patch of the call itself, and no test sleeps."""

import errno
import os
import stat

import pytest
from hand_support import play

from bibliopolis import store
from bibliopolis.events import Refusal
from bibliopolis.journal import dumps_world, world_document
from bibliopolis.store import Store, publish_text


def refuse_links(error=errno.EPERM, text="Operation not permitted"):
    def no_links(*args, **kw):
        raise OSError(error, text)

    return no_links


@pytest.fixture
def no_links(monkeypatch):
    """A file system that has no hard links (`os.link` fails with EPERM, as on a FAT volume)."""
    monkeypatch.setattr(os, "link", refuse_links())


def names(folder):
    return sorted(p.name for p in folder.iterdir())


# ------------------------------------------------------------------------------------------------- text ----
def test_text_is_published_to_a_new_file_with_its_bytes_the_permissions_of_the_user_and_no_temporary_file_left(tmp_path):
    out = tmp_path / "new" / "out.json"  # (the folder is made)
    before = os.umask(0o027)
    try:
        publish_text(out, "a\nb\n預\n")
    finally:
        os.umask(before)
    assert out.read_bytes() == "a\nb\n預\n".encode("utf-8") and stat.S_IMODE(out.stat().st_mode) == 0o640
    assert names(out.parent) == ["out.json"] and out.stat().st_nlink == 1


def test_a_name_that_is_taken_is_never_written_over_whatever_it_is(tmp_path):
    """A file of text, a folder, a link to a file and a link to nothing are all taken; nothing is made behind a link."""
    (tmp_path / "text.json").write_text("the first", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    taken = [tmp_path / "text.json", tmp_path / "folder"]
    try:
        (tmp_path / "to-file.json").symlink_to(tmp_path / "text.json")
        (tmp_path / "to-nothing.json").symlink_to(tmp_path / "behind.json")
        taken += [tmp_path / "to-file.json", tmp_path / "to-nothing.json"]
    except OSError:
        pass
    before = names(tmp_path)
    for path in taken:
        with pytest.raises(Refusal) as why:
            publish_text(path, "the second")
        assert (why.value.code, why.value.params) == ("output_exists", {"path": str(path)})
        assert str(why.value) == f"{path} is there already; a file is not written over (choose another file, or move that one away)"
    assert names(tmp_path) == before and (tmp_path / "text.json").read_text(encoding="utf-8") == "the first" and not (tmp_path / "behind.json").exists()


def test_a_file_that_appears_between_the_writing_and_the_publishing_is_never_written_over(tmp_path, monkeypatch):
    out = tmp_path / "out.json"
    real = store._publish

    def late(temp, dest):
        dest.write_bytes(b"the other party's file")  # made after the text was written, before it is published
        real(temp, dest)

    monkeypatch.setattr(store, "_publish", late)
    with pytest.raises(Refusal, match="is there already"):
        publish_text(out, "the text")
    assert out.read_bytes() == b"the other party's file" and names(tmp_path) == ["out.json"]


def test_a_failure_removes_the_temporary_file_and_nothing_else(tmp_path, monkeypatch):
    (tmp_path / "other.json").write_text("not mine", encoding="utf-8")
    (tmp_path / ".out.json.looks-like-a-temporary-file.part").write_text("not mine either", encoding="utf-8")
    before = names(tmp_path)

    def fail(temp, dest):
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(store, "_publish", fail)
    with pytest.raises(RuntimeError, match="disk is full"):
        publish_text(tmp_path / "out.json", "the text")
    assert names(tmp_path) == before


def test_the_temporary_file_is_made_exclusively_under_a_random_name_and_a_name_that_is_taken_is_not_opened(tmp_path, monkeypatch):
    """A file that is called what the temporary file is about to be called (a world, for example) is never opened: `O_EXCL` refuses the name and another random one is drawn."""
    taken = tmp_path / ".out.json.deadbeefdeadbeef.part"
    taken.write_text("a world, for example", encoding="utf-8")
    drawn = iter(["deadbeefdeadbeef", "0123456789abcdef"])
    monkeypatch.setattr("secrets.token_hex", lambda size: next(drawn))
    publish_text(tmp_path / "out.json", "the text")
    assert taken.read_text(encoding="utf-8") == "a world, for example" and (tmp_path / "out.json").read_text(encoding="utf-8") == "the text"
    assert names(tmp_path) == [".out.json.deadbeefdeadbeef.part", "out.json"] and list(drawn) == []


def test_a_temporary_file_is_given_up_after_a_hundred_names_that_are_taken_and_nothing_is_published(tmp_path, monkeypatch):
    """The names are drawn from the system's source of randomness: a hundred taken in a row is a folder that is not what it seems, and the error is the system's own."""
    taken = tmp_path / ".out.json.0000000000000000.part"
    taken.write_text("taken", encoding="utf-8")
    calls = []
    monkeypatch.setattr("secrets.token_hex", lambda size: (calls.append(size), "0000000000000000")[1])
    with pytest.raises(FileExistsError):
        publish_text(tmp_path / "out.json", "the text")
    assert len(calls) == store.TEMP_TRIES and names(tmp_path) == [taken.name]


def test_the_permissions_come_from_the_kernel_and_the_umask_is_never_read_or_set(tmp_path, monkeypatch):
    """Reading the umask means setting it for an instant, for the whole process; the file is made with the permissions asked for and the kernel takes the umask's bits away."""
    before = os.umask(0o027)
    try:
        def not_touched(*args):
            raise AssertionError("the umask was read or set")

        monkeypatch.setattr(os, "umask", not_touched)
        publish_text(tmp_path / "out.json", "the text")
        Store.import_journal(tmp_path / "w.sqlite", play(2, steps=30))
        monkeypatch.undo()
    finally:
        os.umask(before)
    assert stat.S_IMODE((tmp_path / "out.json").stat().st_mode) == 0o640 and stat.S_IMODE((tmp_path / "w.sqlite").stat().st_mode) == 0o640
    assert names(tmp_path) == ["out.json", "w.sqlite"]


def watching_syncs_and_links(monkeypatch):
    """The order of the calls that make a file safe: what is synced (a file, a folder) and when the link is made."""
    seen, real_fsync, real_link = [], os.fsync, os.link

    def fsync(fd):
        seen.append("sync folder" if stat.S_ISDIR(os.fstat(fd).st_mode) else "sync file")
        return real_fsync(fd)

    def link(src, dst, *args, **kw):
        seen.append("link")
        return real_link(src, dst, *args, **kw)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", link)
    return seen


@pytest.mark.parametrize("what", ["text", "a world"])
def test_the_finished_file_is_synced_before_it_is_published_and_the_folder_after_the_link(what, tmp_path, monkeypatch):
    """What survives a crash: the bytes are on the disk before the name is made, and the name after it. (SQLite syncs its own file at the commit, through the C library, not through here.)"""
    seen = watching_syncs_and_links(monkeypatch)
    if what == "text":
        publish_text(tmp_path / "out.json", "the text")
    else:
        Store.import_journal(tmp_path / "w.sqlite", play(2, steps=30))
    assert seen == ["sync file", "link", "sync folder"]


def test_a_name_that_is_taken_is_met_after_the_file_is_synced_and_nothing_is_synced_for_the_folder(tmp_path, monkeypatch):
    (tmp_path / "out.json").write_text("the first", encoding="utf-8")
    seen = watching_syncs_and_links(monkeypatch)
    with pytest.raises(Refusal, match="is there already"):
        publish_text(tmp_path / "out.json", "the second")
    assert seen == ["sync file", "link"]


# ------------------------------------------------------------------------------------ no hard links ----
@pytest.mark.parametrize("what", ["text", "a world"])
@pytest.mark.parametrize(("error", "reason"), [(errno.EPERM, "Operation not permitted"), (errno.ENOTSUP, "Operation not supported"), (errno.EACCES, "Permission denied")])
def test_where_a_hard_link_cannot_be_made_nothing_is_published_and_only_the_temporary_file_is_removed(what, error, reason, tmp_path, monkeypatch):
    """There is no second way: a copy into a name that was made for it can be overtaken by another party's file, and removed after it. The call is refused and says what to do."""
    (tmp_path / "other.json").write_text("not mine", encoding="utf-8")
    (tmp_path / ".out.json.looks-like-a-temporary-file.part").write_text("not mine either", encoding="utf-8")
    before = names(tmp_path)
    monkeypatch.setattr(os, "link", refuse_links(error, reason))
    out = tmp_path / "out.json"
    with pytest.raises(Refusal) as why:
        publish_text(out, "the text") if what == "text" else Store.import_journal(out, play(2, steps=30))
    assert (why.value.code, why.value.params) == ("no_hard_links", {"path": str(out), "folder": str(tmp_path), "reason": reason})
    assert str(why.value) == (f"{out} cannot be published: a hard link could not be made in {tmp_path} ({reason}); choose a folder on a disk that supports hard links")
    assert names(tmp_path) == before and not out.exists()


def test_where_there_are_no_hard_links_a_name_that_is_taken_is_still_not_written_over(no_links, tmp_path):
    (tmp_path / "text.json").write_text("the first", encoding="utf-8")
    before = names(tmp_path)
    with pytest.raises(Refusal) as why:
        publish_text(tmp_path / "text.json", "the second")
    assert why.value.code == "no_hard_links" and (tmp_path / "text.json").read_text(encoding="utf-8") == "the first" and names(tmp_path) == before


# ------------------------------------------------------------------------------------------- a world ----
def small_world():
    return play(2, steps=40)


def test_a_world_is_built_in_a_file_of_its_own_and_the_path_has_it_only_when_it_is_whole(tmp_path, monkeypatch):
    path, journal, seen = tmp_path / "w.sqlite", small_world(), []
    insert = Store._insert

    def watching(db, event):
        if event["seq"] == 5:
            seen.append((path.exists(), [n for n in names(tmp_path) if n.endswith(".part")]))
        insert(db, event)

    monkeypatch.setattr(Store, "_insert", staticmethod(watching))
    Store.import_journal(path, journal)
    assert len(seen) == 1 and seen[0][0] is False and len(seen[0][1]) == 1 and seen[0][1][0].startswith(".w.sqlite.")  # nothing under the name while it is built
    assert names(tmp_path) == ["w.sqlite"] and dumps_world(world_document(Store(path).journal())) == dumps_world(world_document(journal))


def other_world(tmp_path):
    """A world of another party, as a file to be put in place at the path of the world that is being made."""
    other = tmp_path / "other-party.sqlite"
    Store.import_journal(other, play(5, steps=40))
    return other, other.read_bytes()


def another_party_takes_the_path(monkeypatch, where, path, other, fail_at=None):
    """Patch the call so that at `where` ("before the world is built": when the database is connected to; "while the world is built": at the third event) the file `other` takes the
    path of the world, as another call's world would, and, with `fail_at`, so that the call fails at that event."""
    insert, connect, state = Store._insert, store._connect, {"taken": False}

    def takes_the_path():
        if not state["taken"]:
            state["taken"] = True
            os.replace(other, path)

    def watching(db, event):
        if event["seq"] == 3 and where == "while the world is built":
            takes_the_path()
        if event["seq"] == fail_at:
            raise RuntimeError("the disk is full")
        insert(db, event)

    def connecting(where_to):
        if where == "before the world is built":
            takes_the_path()
        return connect(where_to)

    monkeypatch.setattr(Store, "_insert", staticmethod(watching))
    monkeypatch.setattr(store, "_connect", connecting)


@pytest.mark.parametrize("where", ["before the world is built", "while the world is built"])
def test_a_world_that_takes_the_path_while_another_is_built_is_never_removed_when_the_call_fails(where, tmp_path, monkeypatch):
    """The call used to make the file at the path first and to remove it on any failure: whatever world stood there by then went with it."""
    path = tmp_path / "w.sqlite"
    other, bytes_of_other = other_world(tmp_path)
    another_party_takes_the_path(monkeypatch, where, path, other, fail_at=5)
    with pytest.raises(RuntimeError, match="disk is full"):
        Store.import_journal(path, small_world())
    monkeypatch.undo()
    assert path.read_bytes() == bytes_of_other and names(tmp_path) == ["w.sqlite"]  # the other party's world, and no temporary file


@pytest.mark.parametrize("where", ["before the world is built", "while the world is built"])
def test_a_world_that_takes_the_path_while_another_is_built_is_never_written_over_when_the_call_goes_on(where, tmp_path, monkeypatch):
    path = tmp_path / "w.sqlite"
    other, bytes_of_other = other_world(tmp_path)
    another_party_takes_the_path(monkeypatch, where, path, other)
    with pytest.raises(Refusal) as why:
        Store.import_journal(path, small_world())
    monkeypatch.undo()
    assert (why.value.code, why.value.params) == ("world_exists", {"path": str(path)})
    assert path.read_bytes() == bytes_of_other and names(tmp_path) == ["w.sqlite"]


def test_a_world_that_is_there_is_refused_before_anything_is_built(tmp_path, monkeypatch):
    """The refusal at the end is the guard; a quick look first spares the work (and says so at once)."""
    path = tmp_path / "w.sqlite"
    Store.create(path)
    before, built = path.read_bytes(), []
    insert = Store._insert
    monkeypatch.setattr(Store, "_insert", staticmethod(lambda db, event: (built.append(event["seq"]), insert(db, event))))
    with pytest.raises(Refusal, match="is there already"):
        Store.import_journal(path, small_world())
    assert built == [] and path.read_bytes() == before and names(tmp_path) == ["w.sqlite"]


def test_the_world_made_is_the_world_given_and_has_the_permissions_of_the_user(tmp_path):
    journal, path = small_world(), tmp_path / "w.sqlite"
    before = os.umask(0o027)
    try:
        Store.import_journal(path, journal)
    finally:
        os.umask(before)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640 and path.stat().st_nlink == 1 and names(tmp_path) == ["w.sqlite"]
    assert dumps_world(world_document(Store(path).journal())) == dumps_world(world_document(journal))
