"""Publishing a file without ever replacing one that is there (bibliopolis.store.publish_text): the text of `world export` and `world fold`. It is finished in a file of its own in the folder of
the target, made exclusively under a random name, and published to the target by a hard link, which fails when the target is there. A file system that has no hard links gets a fallback (the
target made with `O_EXCL` and the finished file copied into it), so every test of this module runs on both. The interleavings are controlled: the other party's file appears at a chosen moment
of the call, by a patch of the call itself, and no test sleeps."""

import errno
import os
import shutil
import stat
from pathlib import Path

import pytest
from bibliopolis import store
from bibliopolis.events import Refusal
from bibliopolis.store import publish_text


@pytest.fixture(params=["hard links", "no hard links"])
def files(request, monkeypatch):
    """The file system as it is, and one that has no hard links (`os.link` fails with EPERM, as on a FAT volume)."""
    if request.param == "no hard links":
        def no_links(*args, **kw):
            raise OSError(errno.EPERM, "Operation not permitted")

        monkeypatch.setattr(os, "link", no_links)
    return request.param


@pytest.fixture
def no_links(monkeypatch):
    def refuse(*args, **kw):
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", refuse)


def names(folder):
    return sorted(p.name for p in folder.iterdir())


# ------------------------------------------------------------------------------------------------- text ----
def test_text_is_published_to_a_new_file_with_its_bytes_the_permissions_of_the_user_and_no_temporary_file_left(files, tmp_path):
    out = tmp_path / "new" / "out.json"  # (the folder is made)
    before = os.umask(0o027)
    try:
        publish_text(out, "a\nb\n預\n")
    finally:
        os.umask(before)
    assert out.read_bytes() == "a\nb\n預\n".encode("utf-8") and stat.S_IMODE(out.stat().st_mode) == 0o640
    assert names(out.parent) == ["out.json"] and out.stat().st_nlink == 1


def test_a_name_that_is_taken_is_never_written_over_whatever_it_is(files, tmp_path):
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


def test_a_file_that_appears_between_the_writing_and_the_publishing_is_never_written_over(files, tmp_path, monkeypatch):
    out = tmp_path / "out.json"
    real = store._publish

    def late(temp, dest):
        dest.write_bytes(b"the other party's file")  # made after the text was written, before it is published
        real(temp, dest)

    monkeypatch.setattr(store, "_publish", late)
    with pytest.raises(Refusal, match="is there already"):
        publish_text(out, "the text")
    assert out.read_bytes() == b"the other party's file" and names(tmp_path) == ["out.json"]


def test_a_failure_removes_the_temporary_file_and_nothing_else(files, tmp_path, monkeypatch):
    (tmp_path / "other.json").write_text("not mine", encoding="utf-8")
    (tmp_path / ".out.json.looks-like-a-temporary-file.part").write_text("not mine either", encoding="utf-8")
    before = names(tmp_path)

    def fail(temp, dest):
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(store, "_publish", fail)
    with pytest.raises(RuntimeError, match="disk is full"):
        publish_text(tmp_path / "out.json", "the text")
    assert names(tmp_path) == before


def test_the_temporary_file_is_made_exclusively_under_a_name_of_its_own(files, tmp_path, monkeypatch):
    """A file that is called what the temporary file used to be called (`.<name>.<pid>.part`) is never opened: the name is random and made with `O_EXCL`."""
    victim = tmp_path / f".out.json.{os.getpid()}.part"
    victim.write_text("a world, for example", encoding="utf-8")
    seen = []
    real = store.tempfile.mkstemp

    def watching(*args, **kw):
        fd, name = real(*args, **kw)
        seen.append(Path(name).name)
        return fd, name

    monkeypatch.setattr(store.tempfile, "mkstemp", watching)
    publish_text(tmp_path / "out.json", "the text")
    assert victim.read_text(encoding="utf-8") == "a world, for example" and (tmp_path / "out.json").read_text(encoding="utf-8") == "the text"
    assert len(seen) == 1 and seen[0] != victim.name and seen[0].startswith(".out.json.") and seen[0].endswith(".part")


# ------------------------------------------------------------------------------------ no hard links ----
def test_where_there_are_no_hard_links_a_failed_copy_removes_the_file_it_made(no_links, tmp_path, monkeypatch):
    def fails(src, dst, *args, **kw):
        dst.write(b"half")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(shutil, "copyfileobj", fails)
    with pytest.raises(OSError, match="No space left"):
        publish_text(tmp_path / "out.json", "the text")
    assert names(tmp_path) == []  # not a half file under the name, and not the temporary file


def test_where_there_are_no_hard_links_a_failed_copy_never_removes_a_file_that_took_the_name(no_links, tmp_path, monkeypatch):
    out = tmp_path / "out.json"

    def fails_after_the_name_changed_hands(src, dst, *args, **kw):
        out.unlink()
        out.write_bytes(b"the other party's file")  # another file under the name now (another inode)
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(shutil, "copyfileobj", fails_after_the_name_changed_hands)
    with pytest.raises(OSError, match="No space left"):
        publish_text(out, "the text")
    assert out.read_bytes() == b"the other party's file" and names(tmp_path) == ["out.json"]


def test_a_hard_link_that_fails_for_another_reason_than_a_taken_name_is_the_fallback_and_a_taken_name_is_not(tmp_path, monkeypatch):
    """Only `FileExistsError` from the link says that the name is taken; the fallback has its own `O_EXCL`, so a name taken in the meantime is taken there too."""
    calls = []

    def link(temp, dest, *args, **kw):
        calls.append(("link", Path(dest).name))
        Path(dest).write_text("the other party's file", encoding="utf-8")  # taken after the first look, before the link
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", link)
    with pytest.raises(Refusal, match="is there already"):
        publish_text(tmp_path / "out.json", "the text")
    assert calls == [("link", "out.json")] and (tmp_path / "out.json").read_text(encoding="utf-8") == "the other party's file" and names(tmp_path) == ["out.json"]
