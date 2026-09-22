import pytest

from app.services.lab import artifacts_graph


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setattr(artifacts_graph, "generate",
                        lambda t, doc: f"GENERATED-{t}")
    saved = []

    async def fake_save(student_id, doc_id, doc_title, artifact_type, content):
        saved.append((artifact_type, content))
        return f"aid-{artifact_type}"

    monkeypatch.setattr(artifacts_graph, "save_artifact", fake_save)
    return artifacts_graph.build_lab_graph(), saved


def _cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_artifacts_only_runs_to_completion(graph):
    g, saved = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary"],
                  "artifacts": {}}, _cfg("t1"))
    assert v["status"] == "complete"
    assert v["artifacts"]["flashcards"] == "GENERATED-flashcards"
    assert v["artifacts"]["summary"] == "GENERATED-summary"
    assert not v.get("__interrupt__")


def test_each_artifact_is_persisted_as_it_lands(graph):
    g, saved = graph
    g.invoke({"document": "d", "outputs_requested": ["flashcards", "summary", "study_plan"],
              "artifacts": {}}, _cfg("t2"))
    assert sorted(t for t, _ in saved) == ["flashcards", "study_plan", "summary"]


def test_quiz_only_generates_no_artifacts_and_reaches_the_quiz_tail(graph):
    g, saved = graph
    v = g.invoke({"document": "d", "outputs_requested": ["quiz"], "artifacts": {}},
                 _cfg("t3"))
    assert saved == [], "quiz-only must be an empty fan-out passthrough"
    assert v["artifacts"] == {}
    assert v["status"] == "awaiting_objectives"


def test_all_four_generates_artifacts_then_reaches_the_quiz_tail(graph):
    g, saved = graph
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
    g, saved = graph
    v = g.invoke({"document": "d", "outputs_requested": ["flashcards", "horoscope"],
                  "artifacts": {}}, _cfg("t5"))
    assert sorted(v["artifacts"]) == ["flashcards"]
