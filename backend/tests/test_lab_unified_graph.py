import pytest

from app.services.lab import artifact_store, artifacts_graph


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setattr(artifacts_graph, "generate",
                        lambda t, doc: f"GENERATED-{t}")
    return artifacts_graph.build_lab_graph()


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


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
    assert v["status"] == "awaiting_objectives"


def test_all_four_generates_artifacts_then_reaches_the_quiz_tail(graph):
    g = graph
    v = g.invoke({"document": "d",
                  "outputs_requested": ["quiz", "flashcards", "summary", "study_plan"],
                  "artifacts": {}}, _cfg("t4"))
    assert sorted(v["artifacts"]) == ["flashcards", "study_plan", "summary"]
    assert v["status"] == "awaiting_objectives"
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
    node must not touch artifact_store at all. Point the real save() at
    something that raises, and confirm the graph still completes cleanly —
    if a future edit re-adds a save call inside _gen, this fails."""
    monkeypatch.setattr(artifacts_graph, "generate", lambda t, doc: f"GENERATED-{t}")

    async def exploding_save(*args, **kwargs):
        raise RuntimeError("_gen must never call artifact_store.save")

    monkeypatch.setattr(artifact_store, "save", exploding_save)

    g = artifacts_graph.build_lab_graph()
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary"],
                  "artifacts": {}}, _cfg("t6"))
    assert v["status"] == "complete"
    assert sorted(v["artifacts"]) == ["flashcards", "summary"]
