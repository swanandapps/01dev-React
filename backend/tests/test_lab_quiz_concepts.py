from app.services.lab import llm as lab_llm

OBJ = {"title": "Memoization", "difficulty": "beginner", "focus": "memo"}


def _q(**extra):
    return {"question": "What does React.memo skip?", "options": ["a1", "b1", "c1", "d1"],
            "correctIndex": 0, "explanation": "because", "hint": "nudge", **extra}


def test_gen_quiz_passes_the_raw_concept_through_unchanged(monkeypatch):
    def fake_chat_json(system, user, max_tokens=900):
        assert "concept" in system, "prompt must ask the model for a concept tag"
        return {"questions": [_q(concept="React.memo")]}

    monkeypatch.setattr(lab_llm, "_chat_json", fake_chat_json)
    out = lab_llm.gen_quiz("material", OBJ, 1)
    assert out[0]["concept"] == "React.memo"  # resolution happens at submit time
    assert out[0]["hint"] and out[0]["explanation"]
    assert out[0]["correctIndex"] == 0


def test_missing_concept_defaults_to_empty(monkeypatch):
    monkeypatch.setattr(lab_llm, "_chat_json", lambda s, u, max_tokens=900: {"questions": [_q()]})
    out = lab_llm.gen_quiz("material", OBJ, 1)
    assert out[0]["concept"] == ""


def test_null_concept_does_not_drop_the_question(monkeypatch):
    monkeypatch.setattr(lab_llm, "_chat_json",
                        lambda s, u, max_tokens=900: {"questions": [_q(concept=None)]})
    out = lab_llm.gen_quiz("material", OBJ, 1)
    assert out[0]["question"].startswith("What does React.memo") and out[0]["concept"] == ""
