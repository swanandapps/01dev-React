import pytest

from app.services.lab import artifacts_graph
from app.services.store import store


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setattr(artifacts_graph, "generate",
                        lambda t, doc: f"GENERATED-{t}")
    return artifacts_graph.build_lab_graph()


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def _reached_quiz_tail(g, cfg) -> bool:
    """True iff `quiz_tail` was ever the pending node for this thread — proof
    that `route_after_join` sent execution there rather than straight to END.

    `quiz_tail` deliberately does not set a `status` (see its docstring: a
    second vocabulary for "awaiting objectives" next to graph.py's real
    client-facing "awaiting_approval" is a trap, not a feature), so routing
    is verified structurally via state history instead of via a status value.
    """
    return any(h.next == ("quiz_tail",) for h in g.get_state_history(cfg))


def test_artifacts_only_runs_to_completion(graph):
    g = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary"],
                  "artifacts": {}}, _cfg("t1"))
    assert v["status"] == "complete"
    assert v["artifacts"]["flashcards"] == "GENERATED-flashcards"
    assert v["artifacts"]["summary"] == "GENERATED-summary"
    assert not v.get("__interrupt__")


def test_each_artifact_lands_in_state_after_the_fan_out(graph):
    """Persistence is the caller's job now (see artifacts_graph.py docstring —
    a sync node bridging into async artifact_store.save via asyncio.run()
    breaks the process-wide asyncpg pool's event-loop affinity in production).
    The graph's own contract is just: every requested artifact shows up in
    `artifacts` once the fan-out joins."""
    g = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary", "study_plan"],
                  "artifacts": {}}, _cfg("t2"))
    assert sorted(v["artifacts"]) == ["flashcards", "study_plan", "summary"]
    assert v["artifacts"]["flashcards"] == "GENERATED-flashcards"
    assert v["artifacts"]["summary"] == "GENERATED-summary"
    assert v["artifacts"]["study_plan"] == "GENERATED-study_plan"


def test_quiz_only_generates_no_artifacts_and_reaches_the_quiz_tail(graph):
    g = graph
    v = g.invoke({"document": "d", "outputs_requested": ["quiz"], "artifacts": {}},
                 _cfg("t3"))
    assert v["artifacts"] == {}, "quiz-only must be an empty fan-out passthrough"
    assert _reached_quiz_tail(g, _cfg("t3"))


def test_all_four_generates_artifacts_then_reaches_the_quiz_tail(graph):
    g = graph
    v = g.invoke({"document": "d",
                  "outputs_requested": ["quiz", "flashcards", "summary", "study_plan"],
                  "artifacts": {}}, _cfg("t4"))
    assert sorted(v["artifacts"]) == ["flashcards", "study_plan", "summary"]
    assert _reached_quiz_tail(g, _cfg("t4"))
    # THE PHASE 0 ASSUMPTION: artifacts finished before the tail are readable
    # from the checkpoint while it is suspended.
    snap = g.get_state(_cfg("t4"))
    assert sorted(snap.values["artifacts"]) == ["flashcards", "study_plan", "summary"]


def test_unknown_requested_output_is_ignored(graph):
    g = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "horoscope"],
                  "artifacts": {}}, _cfg("t5"))
    assert sorted(v["artifacts"]) == ["flashcards"]


def test_gen_node_does_no_io_even_if_the_store_would_explode(monkeypatch):
    """Regression guard for the asyncio.run()-vs-asyncpg-pool bug: the fan-out
    node must not touch the store at all, however a future edit reimports
    persistence — module-attribute call, `from ... import save as X` alias,
    anything. Patching `artifact_store.save` does NOT catch a from-import
    alias (the alias is a separate name bound at import time, unaffected by
    patching the original module's attribute afterwards), which is exactly
    the form the original bug used. So patch the one chokepoint every write
    path funnels through instead: the `store` singleton's own `.set` method.
    Point it at something that raises and confirm the graph still completes
    cleanly — if a future edit re-adds any persistence call inside _gen,
    this fails no matter how it's imported."""
    monkeypatch.setattr(artifacts_graph, "generate", lambda t, doc: f"GENERATED-{t}")

    async def exploding_set(*args, **kwargs):
        raise RuntimeError("_gen must never touch the store")

    monkeypatch.setattr(store, "set", exploding_set)

    g = artifacts_graph.build_lab_graph()
    # student_id must be non-empty: artifact_store.save() short-circuits to a
    # no-op for anonymous sessions (empty student_id), which would let a
    # reintroduced persistence call slip past this guard undetected.
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary"],
                  "artifacts": {}, "student_id": "s1", "doc_id": "doc1",
                  "doc_title": "Doc"}, _cfg("t6"))
    assert v["status"] == "complete"
    assert sorted(v["artifacts"]) == ["flashcards", "summary"]

    # Structural guard: the module shouldn't even hold references that would
    # let it do I/O — belt and suspenders alongside the behavioral check above.
    assert not hasattr(artifacts_graph, "save_artifact")
    assert not hasattr(artifacts_graph, "asyncio")
