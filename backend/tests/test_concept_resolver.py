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
async def test_new_node_from_a_lecture_source_stays_out_of_the_fixed_taxonomy(store, monkeypatch):
    _stub_embeddings(monkeypatch, {"Fiber Architecture": [0.0, 1.0, 0.0]})

    assert await concept_resolver.resolve("Fiber Architecture", course_id="react-perf") \
        == "fiber-architecture"
    node = await store.get("concepts", "react-perf::fiber-architecture")
    # course_id=X means "part of course X's fixed taxonomy" to question_service,
    # knowledge_graph_service etc. A discovered concept must not join it.
    assert node["course_id"] is None
    assert node["source_course_id"] == "react-perf"


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
async def test_cold_pool_larger_than_bound_still_merges_beyond_the_bound(store, monkeypatch):
    """Fix-round-2 CRITICAL, mirrors the production reproduction directly:
    a cold 9-node pool with the bound at 5 must NOT fork a duplicate just
    because the true match sits beyond the bound. The pool comparison must
    complete before a node is created — creating is irreversible, merging
    is not."""
    bound = concept_resolver.MAX_BACKFILL_PER_RESOLVE
    assert bound < 9  # the test only proves anything if the pool exceeds the bound
    names = [f"topic-{i}" for i in range(8)] + ["closures"]
    for name in names:
        await store.set("concepts", f"react-perf::{name}", {
            "course_id": "react-perf", "name": name,
        })  # no embedding — cold, exactly like knowledge_graph_service writes

    # 9 mutually orthogonal 9-dim vectors: only the true match ("closures",
    # inserted LAST, i.e. beyond the bound) can score above 0 against the
    # candidate — nothing before it can accidentally pass the threshold.
    vectors = {name: [1.0 if j == idx else 0.0 for j in range(9)] for idx, name in enumerate(names)}
    vectors["Closures in JavaScript"] = vectors["closures"]
    _stub_embeddings(monkeypatch, vectors)

    result = await concept_resolver.resolve("Closures in JavaScript")
    assert result == "closures"  # merged onto the true match, not forked

    # only one "closures" node exists — a fork would show up as a second one
    assert await store.get("concepts", "self-study::closures-in-javascript") is None


@pytest.mark.asyncio
async def test_merge_found_within_the_bound_does_not_pay_to_backfill_the_rest(store, monkeypatch):
    """The fast path must stay cheap: a match found while backfilling
    within the bound returns without finishing the whole cold pool."""
    bound = concept_resolver.MAX_BACKFILL_PER_RESOLVE
    await store.set("concepts", "react-perf::closures", {
        "course_id": "react-perf", "name": "closures",
    })
    for i in range(bound + 3):
        await store.set("concepts", f"react-perf::topic-{i}", {
            "course_id": "react-perf", "name": f"topic-{i}",
        })

    embed_calls = {"n": 0}

    async def counting_embed(text):
        embed_calls["n"] += 1
        if text in ("closures", "Closures in JS"):
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", counting_embed)

    result = await concept_resolver.resolve("Closures in JS")
    assert result == "closures"
    # 1 candidate embed + at most `bound` backfills — must not have paid to
    # backfill the whole (bound + 3 + 1)-node pool just to confirm a match
    # it already found.
    assert embed_calls["n"] <= 1 + bound


@pytest.mark.asyncio
async def test_backfill_completes_fully_before_a_create_even_past_the_bound(store, monkeypatch):
    """The bound gates the FAST path only. A genuine miss (nothing in the
    pool matches, anywhere) must still pay to finish backfilling every cold
    node before create() is allowed to run — never just `bound` of them."""
    bound = concept_resolver.MAX_BACKFILL_PER_RESOLVE
    n = bound + 3
    for i in range(n):
        await store.set("concepts", f"react-perf::topic-{i}", {
            "course_id": "react-perf", "name": f"topic-{i}",
        })

    embed_calls = {"n": 0}

    async def routed_embed(text):
        embed_calls["n"] += 1
        if text == "something genuinely new":
            return [1.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0]  # orthogonal to the candidate — a genuine miss

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", routed_embed)

    result = await concept_resolver.resolve("something genuinely new")
    assert result == "something-genuinely-new"  # created — no match anywhere in the pool

    assert embed_calls["n"] == 1 + n  # every cold node backfilled, not just `bound`
    backfill_logs = [e for e in await store.list_all("concept_resolutions") if e["method"] == "backfill"]
    assert len(backfill_logs) == n


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
async def test_backfilled_vector_of_a_wrong_dimension_is_never_compared(store, monkeypatch):
    """The dimension guard must cover FRESHLY backfilled vectors too, not just
    stored ones. If a backfill returns a different-dimension vector, _cosine's
    zip would truncate and score an unrelated concept 1.0 — merging a student's
    Kubernetes notes onto 'event-loop' and moving the wrong course mastery.
    A vector we cannot compare is unreadable, not a match."""
    await store.set("concepts", "react-perf::event-loop", {
        "course_id": "react-perf", "name": "event-loop",  # cold: no embedding
    })
    _stub_embeddings(monkeypatch, {
        "event-loop": [1.0, 0.0, 0.0, 0.0, 0.0],          # backfill: 5-dim
        "totally unrelated kubernetes": [1.0, 0.0, 0.0],  # candidate: 3-dim
    })

    got = await concept_resolver.resolve("totally unrelated kubernetes")

    assert got != "event-loop", "truncated compare merged an unrelated concept"
    assert got == "totally-unrelated-kubernetes"


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


# ---------------------------------------------------------------------------
# Fix round 2 — findings 2, 4, 5, 6, 7
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_embed_failure_does_not_crash_resolution(store, monkeypatch):
    """A failed backfill embed (OpenAI down, rate limited, whatever) must
    not propagate out of resolve() and fail the student's request —
    pre-round-1, a vectorless node was merely unreachable via the embedding
    branch, never a crash, and that must still hold. Since the pool
    couldn't be fully compared, the resulting create is flagged
    incomplete/auditable rather than silently forking."""
    await store.set("concepts", "react-perf::closures", {
        "course_id": "react-perf", "name": "closures",
    })

    async def flaky_embed(text):
        if text == "closures":
            raise RuntimeError("OpenAI is down")
        return [0.0, 1.0, 0.0]

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", flaky_embed)

    result = await concept_resolver.resolve("Something Else Entirely")  # must not raise
    assert result

    logged = await store.list_all("concept_resolutions")
    created = [e for e in logged if e["method"] == "created"]
    assert created
    assert created[-1]["comparison_incomplete"] is True
    assert created[-1]["unreadable_pool_nodes"] >= 1


@pytest.mark.asyncio
async def test_pool_node_with_empty_name_is_never_returned(store, monkeypatch):
    """A pool node with name: "" and a usable, perfectly-matching embedding
    must never be returned as the resolved name — "" is exactly the value
    that poisons _perf_id (f"{user_id}__{concept}" -> f"{user_id}__")."""
    await store.set("concepts", "react-perf::empty", {
        "course_id": "react-perf", "name": "", "embedding": [1.0, 0.0, 0.0],
        "embedding_model": concept_resolver._current_embedding_model(),
    })
    _stub_embeddings(monkeypatch, {"candidate text": [1.0, 0.0, 0.0]})  # perfect cosine match

    result = await concept_resolver.resolve("candidate text")
    assert result != ""


def test_symbol_only_junk_slug_differs_from_a_real_word_slug():
    """"#" alone must not slug to the same thing as "Sharp" — pure symbol
    junk has to fall through to the hash fallback, not spell itself into a
    plausible-looking real word that could then merge with an unrelated
    concept of that name."""
    assert concept_resolver.slugify("#") != concept_resolver.slugify("Sharp")
    assert concept_resolver.slugify("+") != concept_resolver.slugify("Plus")
    assert concept_resolver.slugify("#") == ""
    assert concept_resolver.slugify("@#$%^&*") == ""
    # names with real alphanumeric content still get the symbol spelled out
    assert concept_resolver.slugify("C#") == "c-sharp"


@pytest.mark.asyncio
async def test_resolve_none_does_not_raise_or_reach_embeddings(store, monkeypatch):
    async def fail_embed(text):
        raise AssertionError("None candidate must never reach embed()")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    result = await concept_resolver.resolve(None)
    assert result


@pytest.mark.asyncio
async def test_resolve_blank_string_does_not_reach_embeddings(store, monkeypatch):
    async def fail_embed(text):
        raise AssertionError("blank/whitespace-only candidate must never reach embed()")

    from app.services import embeddings
    monkeypatch.setattr(embeddings.embedding_service, "embed", fail_embed)

    result = await concept_resolver.resolve("   ")
    assert result


@pytest.mark.asyncio
async def test_stale_model_tag_triggers_reembed_even_with_matching_dim(store, monkeypatch):
    """embeddings.py's local hash fallback is per-process non-deterministic,
    so a dimension match alone isn't proof a stored vector is still valid.
    An explicit embedding_model tag that no longer matches the service's
    current choice must trigger re-embed too, not just a dimension
    change."""
    await store.set("concepts", "react-perf::event-loop", {
        "course_id": "react-perf", "name": "event-loop",
        "embedding": [1.0, 0.0, 0.0],          # same dim as the candidate below
        "embedding_model": "stale-model-v0",   # explicitly tagged, doesn't match current
    })
    _stub_embeddings(monkeypatch, {
        "event-loop": [0.0, 0.0, 1.0],       # re-embed of the pool node
        "the event loop": [0.0, 0.0, 0.99],  # candidate, close to the NEW vector
    })

    assert await concept_resolver.resolve("the event loop") == "event-loop"
    node = await store.get("concepts", "react-perf::event-loop")
    assert node["embedding"] == [0.0, 0.0, 1.0]
    assert node["embedding_model"] != "stale-model-v0"
