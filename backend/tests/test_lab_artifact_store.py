import pytest

from app.services.lab import artifact_store
from app.services.store import InMemoryStore


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(artifact_store, "store", s)
    return s


@pytest.mark.asyncio
async def test_save_then_read_back(store):
    aid = await artifact_store.save(
        "s1", "doc1", "My Notes", "flashcards", [{"front": "f", "back": "b"}])
    got = await artifact_store.get(aid)
    assert got["student_id"] == "s1"
    assert got["artifact_type"] == "flashcards"
    assert got["content"] == [{"front": "f", "back": "b"}]
    assert got["doc_title"] == "My Notes"
    assert got["created_at"]


@pytest.mark.asyncio
async def test_library_is_scoped_to_the_student(store):
    await artifact_store.save("s1", "d", "t", "summary", "mine")
    await artifact_store.save("s2", "d", "t", "summary", "theirs")
    lib = await artifact_store.library("s1")
    assert [a["content"] for a in lib] == ["mine"]


@pytest.mark.asyncio
async def test_library_is_newest_first(store):
    a1 = await artifact_store.save("s1", "d", "t", "summary", "first")
    a2 = await artifact_store.save("s1", "d", "t", "summary", "second")
    lib = await artifact_store.library("s1")
    assert [a["artifact_id"] for a in lib] == [a2, a1]


@pytest.mark.asyncio
async def test_library_respects_the_limit(store):
    for i in range(5):
        await artifact_store.save("s1", "d", "t", "summary", f"s{i}")
    assert len(await artifact_store.library("s1", limit=2)) == 2


@pytest.mark.asyncio
async def test_anonymous_saves_nothing(store):
    aid = await artifact_store.save("", "d", "t", "summary", "orphan")
    assert aid == ""
    assert await store.list_all("lab_artifacts") == []
