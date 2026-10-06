from app.services.lab import llm


def _fixture(n=8):
    return {"questions": [
        {"question": f"Question number {i}?",
         "options": [f"right-{i}", f"wrong-{i}-a", f"wrong-{i}-b", f"wrong-{i}-c"],
         "correctIndex": 0, "explanation": "e", "hint": "h", "concept": "c"}
        for i in range(n)]}


def test_gen_quiz_shuffles_and_keeps_correct_index_consistent(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda *a, **k: _fixture())
    qs = llm.gen_quiz("doc", {"title": "t"}, 8)
    assert len(qs) == 8
    assert {q["correctIndex"] for q in qs} != {0}
    for i, q in enumerate(qs):
        assert q["options"][q["correctIndex"]] == f"right-{i}"
        assert sorted(q["options"]) == sorted(
            [f"right-{i}", f"wrong-{i}-a", f"wrong-{i}-b", f"wrong-{i}-c"])


def test_gen_quiz_shuffle_is_deterministic(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda *a, **k: _fixture())
    a = llm.gen_quiz("doc", {"title": "t"}, 8)
    b = llm.gen_quiz("doc", {"title": "t"}, 8)
    assert a == b
