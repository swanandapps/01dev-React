"""Answer options must not give the answer away by length: the correct option was the longest 72% of the
time (13/18 real questions, chance 25%). A question whose correct option is clearly the longest is regenerated."""
from app.services.lab import llm

LONG = "The method was added before the language had its own, so later code broke when they differed"


def _q(i, right, wrongs=("Engines crash", "Libraries lock it", "Methods vanish")):
    return {"question": f"Q{i}?", "options": [right, *wrongs], "correctIndex": 0,
            "explanation": "e", "hint": "h", "concept": "c"}


def test_giveaway_is_a_correct_option_clearly_longer_than_every_other():
    assert llm._is_giveaway(_q(0, LONG))
    assert not llm._is_giveaway(_q(0, "Name clashes"))
    assert not llm._is_giveaway(_q(0, "Clashes with a later native method",
                                   ("Engines crash on prototype edits", "It locks the prototype objects", "It deletes native methods")))


def test_a_batch_with_giveaways_is_regenerated_once_and_balanced_questions_win(monkeypatch):
    batches = [{"questions": [_q(i, LONG) for i in range(3)]},
               {"questions": [_q(i, "Name clashes") for i in range(3)]}]
    calls = []

    def fake(system, user, max_tokens=900):
        calls.append(user)
        return batches[len(calls) - 1]

    monkeypatch.setattr(llm, "_chat_json", fake)
    qs = llm.gen_quiz("doc", {"title": "t"}, 3)
    assert len(calls) == 2 and len(qs) == 3
    assert all(q["options"][q["correctIndex"]] == "Name clashes" for q in qs)


def test_a_balanced_batch_is_not_regenerated(monkeypatch):
    calls = []

    def fake(system, user, max_tokens=900):
        calls.append(user)
        return {"questions": [_q(i, "Name clashes") for i in range(3)]}

    monkeypatch.setattr(llm, "_chat_json", fake)
    assert len(llm.gen_quiz("doc", {"title": "t"}, 3)) == 3 and len(calls) == 1


def test_if_the_retry_is_no_better_the_student_still_gets_n_questions(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda *a, **k: {"questions": [_q(i, LONG) for i in range(3)]})
    assert len(llm.gen_quiz("doc", {"title": "t"}, 3)) == 3
