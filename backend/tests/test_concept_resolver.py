import pytest

from app.services import concept_resolver
from app.services.store import InMemoryStore


@pytest.mark.parametrize("raw,expected", [
    ("React.memo", "react-memo"),
    ("useCallback hook", "usecallback-hook"),
    ("  Event  Loop  ", "event-loop"),
    ("V8 Hidden Classes!", "v8-hidden-classes"),
    ("closures", "closures"),
    # Distinguishing symbols must be spelled out, not stripped — otherwise
    # C++, C# and C all collapse to "c" and a student's C# notes would
    # silently move their C++ mastery via the exact-slug-match branch.
    ("C++", "c-plus-plus"),
    ("C#", "c-sharp"),
    ("C", "c"),
    # Non-ASCII letters must be kept, not deleted — "Café" must not become
    # "caf" (which could then collide with an unrelated "Caf" concept).
    ("Café", "café"),
])
def test_slugify(raw, expected):
    assert concept_resolver.slugify(raw) == expected


def test_slugify_distinguishes_c_variants():
    """Belt-and-suspenders on the parametrized cases above: the three must
    be pairwise distinct, not just individually match an expected string."""
    slugs = {concept_resolver.slugify(s) for s in ("C++", "C#", "C")}
    assert len(slugs) == 3


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


# ---------------------------------------------------------------------------
# Fix round 1 — findings 1, 2, 4, 5
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_node_without_embedding_is_backfilled_and_reused(store, monkeypatch):
    """Mirrors production: knowledge_graph_service writes {course_id, name,
    description} with NO embedding field at all (verified true of all 9 live
    concept nodes). The embedding branch must still be able to reach it —
    backfilling the vector onto the SAME document, preserving every existing
    field — rather than silently skipping it and forcing everything onto the
    slug branch."""
    await store.set("concepts", "react-perf::closures", {
        "course_id": "react-perf", "name": "closures", "description": "some description",
    })
    _stub_embeddings(monkeypatch, {
        "closures": [1.0, 0.0, 0.0],                 # backfill embed of the pool node's own name
        "Closures in JavaScript": [0.98, 0.2, 0.0],  # candidate — close to the backfilled vector
    })

    assert await concept_resolver.resolve("Closures in JavaScript") == "closures"

    node = await store.get("concepts", "react-perf::closures")
    assert node["embedding"] == [1.0, 0.0, 0.0]
    assert node["course_id"] == "react-perf"          # preserved, not clobbered
    assert node["description"] == "some description"  # preserved, not clobbered

    backfill_logs = [e for e in await store.list_all("concept_resolutions") if e["method"] == "backfill"]
    assert len(backfill_logs) == 1
    assert backfill_logs[0]["candidate"] == "closures"

    # Second call must reuse the now-persisted embedding — not re-embed the
    # pool node again, only the new candidate text.
    calls = []

    async def tracking_embed(text):
        calls.append(text)
        return [0.98, 0.2, 0.0]

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", tracking_embed)

    assert await concept_resolver.resolve("Closures in JS again") == "closures"
    assert calls == ["Closures in JS again"]


@pytest.mark.asyncio
async def test_backfill_is_bounded_per_call(store, monkeypatch):
    """A cold pool with more embedding-less nodes than
    MAX_BACKFILL_PER_RESOLVE must not block the request embedding all of
    them — it backfills up to the bound and proceeds."""
    bound = concept_resolver.MAX_BACKFILL_PER_RESOLVE
    for i in range(bound + 3):
        await store.set("concepts", f"react-perf::topic-{i}", {
            "course_id": "react-perf", "name": f"topic-{i}",
        })

    embed_calls = {"n": 0}

    async def counting_embed(text):
        embed_calls["n"] += 1
        return [0.0, 1.0, 0.0]  # orthogonal to nothing in particular; just needs a fixed dim

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", counting_embed)

    await concept_resolver.resolve("something unrelated")

    # 1 embed for the candidate + at most `bound` backfills, never one per node.
    assert embed_calls["n"] <= 1 + bound
    backfill_logs = [e for e in await store.list_all("concept_resolutions") if e["method"] == "backfill"]
    assert len(backfill_logs) <= bound


@pytest.mark.asyncio
async def test_dimension_mismatch_triggers_reembed_not_truncated_compare(store, monkeypatch):
    """A node's stored embedding may be stale (e.g. embedded under the
    256-dim local hash fallback before an OPENAI_API_KEY was ever set, now
    compared against 1536-dim OpenAI vectors). It must be re-embedded, never
    compared via truncated zip — a truncated compare is not a real
    similarity score."""
    await store.set("concepts", "react-perf::event-loop", {
        "course_id": "react-perf", "name": "event-loop",
        "embedding": [1.0, 0.0, 0.0],  # stale 3-dim vector
    })
    _stub_embeddings(monkeypatch, {
        "event-loop": [0.0, 0.0, 1.0, 0.0],        # re-embed of the pool node, new 4-dim space
        "the event loop": [0.0, 0.0, 0.99, 0.05],  # candidate, 4-dim, close to the NEW vector
    })

    assert await concept_resolver.resolve("the event loop") == "event-loop"

    node = await store.get("concepts", "react-perf::event-loop")
    assert len(node["embedding"]) == 4  # replaced, not left at the stale 3-dim vector
    assert node["embedding_dim"] == 4


@pytest.mark.asyncio
async def test_exact_threshold_score_of_0_64_merges(store, monkeypatch):
    """0.64 is not an approximate cutoff — pin the exact boundary so a later
    change from >= to > can't silently raise the effective threshold."""
    await store.set("concepts", "react-perf::example", {
        "course_id": "react-perf", "name": "example", "embedding": [1.0, 0.0],
    })
    # cosine(candidate, [1, 0]) == exactly 0.64
    _stub_embeddings(monkeypatch, {"candidate": [0.64, (1 - 0.64 ** 2) ** 0.5]})

    assert await concept_resolver.resolve("candidate") == "example"


@pytest.mark.asyncio
async def test_punctuation_only_candidate_never_returns_empty_string(store, monkeypatch):
    """A candidate that slugifies to nothing (emoji/punctuation-only) must
    fall back to a stable hash-derived slug, never "" — an empty canonical
    name would collide every such candidate onto the same
    concept_performance row (f"{user_id}__{concept}" -> f"{user_id}__")."""
    _stub_embeddings(monkeypatch, {"!!!": [0.0, 1.0, 0.0]})

    result = await concept_resolver.resolve("!!!")
    assert result != ""
    assert result.startswith("concept-")

    logged = await store.list_all("concept_resolutions")
    assert len(logged) == 1
    assert logged[0]["candidate"] == "!!!"
    assert logged[0]["used_fallback_slug"] is True


@pytest.mark.asyncio
async def test_punctuation_only_candidate_is_stable_across_calls(store, monkeypatch):
    """The same unresolvable candidate must fall back to the SAME slug every
    time (hashlib, not the per-process-randomised builtin hash()), so repeat
    submissions land on one node instead of forking a new one each call."""
    _stub_embeddings(monkeypatch, {"???": [0.0, 1.0, 0.0]})

    first = await concept_resolver.resolve("???")

    async def fail_embed(text):
        raise AssertionError("second resolution of the identical fallback candidate must hit the slug path")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    second = await concept_resolver.resolve("???")
    assert first == second
