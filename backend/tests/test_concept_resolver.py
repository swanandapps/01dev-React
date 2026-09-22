import pytest

from app.services import concept_resolver
from app.services.store import InMemoryStore


@pytest.mark.parametrize("raw,expected", [
    ("React.memo", "react-memo"),
    ("useCallback hook", "usecallback-hook"),
    ("  Event  Loop  ", "event-loop"),
    ("V8 Hidden Classes!", "v8-hidden-classes"),
    ("closures", "closures"),
])
def test_slugify(raw, expected):
    assert concept_resolver.slugify(raw) == expected


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(concept_resolver, "store", s)
    return s


def _stub_embeddings(monkeypatch, vectors: dict[str, list[float]]):
    """Map exact text -> vector; anything unmapped gets an orthogonal vector."""
    async def fake_embed(text):
        return vectors.get(text, [0.0, 0.0, 1.0])
    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fake_embed)


@pytest.mark.asyncio
async def test_exact_slug_match_resolves_without_embedding(store, monkeypatch):
    await store.set("concepts", "react-perf::react-memo",
                    {"course_id": "react-perf", "name": "react-memo"})

    async def fail_embed(text):
        raise AssertionError("must not embed when the slug matches exactly")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    assert await concept_resolver.resolve("React.memo") == "react-memo"


@pytest.mark.asyncio
async def test_embedding_match_above_threshold_resolves_to_existing(store, monkeypatch):
    await store.set("concepts", "react-perf::use-callback", {
        "course_id": "react-perf", "name": "use-callback", "embedding": [1.0, 0.0, 0.0],
    })
    _stub_embeddings(monkeypatch, {"useCallback hook": [0.95, 0.31, 0.0]})  # cos ~0.95

    assert await concept_resolver.resolve("useCallback hook") == "use-callback"


@pytest.mark.asyncio
async def test_below_threshold_creates_a_new_node(store, monkeypatch):
    await store.set("concepts", "react-perf::event-loop", {
        "course_id": "react-perf", "name": "event-loop", "embedding": [1.0, 0.0, 0.0],
    })
    _stub_embeddings(monkeypatch, {"kubernetes": [0.0, 1.0, 0.0]})  # cos 0.0

    assert await concept_resolver.resolve("kubernetes") == "kubernetes"
    node = await store.get("concepts", "self-study::kubernetes")
    assert node is not None
    assert node["name"] == "kubernetes"
    assert node["created_by"] == "student_content"
    # MUST be None, not a sentinel string — a string would read to the model as
    # a real course name (the "all-courses" bug).
    assert node["course_id"] is None
    assert node["embedding"] == [0.0, 1.0, 0.0]


@pytest.mark.asyncio
async def test_new_node_from_a_lecture_source_attaches_to_that_course(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"Fiber Architecture": [0.0, 1.0, 0.0]})

    assert await concept_resolver.resolve("Fiber Architecture", course_id="react-perf") \
        == "fiber-architecture"
    node = await store.get("concepts", "react-perf::fiber-architecture")
    assert node["course_id"] == "react-perf"


@pytest.mark.asyncio
async def test_every_decision_is_logged_with_its_score(store, monkeypatch):
    await store.set("concepts", "react-perf::use-callback", {
        "course_id": "react-perf", "name": "use-callback", "embedding": [1.0, 0.0, 0.0],
    })
    _stub_embeddings(monkeypatch, {"useCallback hook": [0.95, 0.31, 0.0]})

    await concept_resolver.resolve("useCallback hook")
    logged = await store.list_all("concept_resolutions")
    assert len(logged) == 1
    entry = logged[0]
    assert entry["candidate"] == "useCallback hook"
    assert entry["resolved_to"] == "use-callback"
    assert entry["method"] == "embedding"
    assert entry["score"] > 0.64


@pytest.mark.asyncio
async def test_a_created_concept_is_logged_as_created(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"kubernetes": [0.0, 1.0, 0.0]})
    await concept_resolver.resolve("kubernetes")
    entry = (await store.list_all("concept_resolutions"))[0]
    assert entry["method"] == "created"
    assert entry["resolved_to"] == "kubernetes"


@pytest.mark.asyncio
async def test_score_just_above_threshold_merges(store, monkeypatch):
    """0.64 is the exact cutoff — a candidate scoring just above it must merge
    onto the existing concept, not create a new node."""
    await store.set("concepts", "react-perf::example", {
        "course_id": "react-perf", "name": "example", "embedding": [1.0, 0.0],
    })
    # cosine(candidate, [1,0]) == 0.645, just above SIMILARITY_THRESHOLD (0.64)
    _stub_embeddings(monkeypatch, {"candidate": [0.645, 0.7641825698090737]})

    assert await concept_resolver.resolve("candidate") == "example"
    node = await concept_resolver.store.get("concepts", "self-study::candidate")
    assert node is None  # no new node was created


@pytest.mark.asyncio
async def test_score_just_below_threshold_creates_new_node(store, monkeypatch):
    """A candidate scoring just below 0.64 must NOT merge — it gets its own
    node instead of being forced onto a near-miss."""
    await store.set("concepts", "react-perf::example", {
        "course_id": "react-perf", "name": "example", "embedding": [1.0, 0.0],
    })
    # cosine(candidate, [1,0]) == 0.635, just below SIMILARITY_THRESHOLD (0.64)
    _stub_embeddings(monkeypatch, {"candidate": [0.635, 0.7725121358270044]})

    assert await concept_resolver.resolve("candidate") == "candidate"
    node = await store.get("concepts", "self-study::candidate")
    assert node is not None
    assert node["course_id"] is None


@pytest.mark.asyncio
async def test_second_resolution_of_the_same_candidate_hits_the_slug_path(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"kubernetes": [0.0, 1.0, 0.0]})
    await concept_resolver.resolve("kubernetes")   # creates the node

    async def fail_embed(text):
        raise AssertionError("second resolution must hit the slug path, not embed again")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    assert await concept_resolver.resolve("Kubernetes") == "kubernetes"
