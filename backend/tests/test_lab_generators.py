import pytest

from app.services.lab import generators


class _FakeResp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


def _fake_client(content):
    class _Completions:
        def create(self, **kwargs):
            return _FakeResp(content)

    class _Chat:
        completions = _Completions()

    return type("Client", (), {"chat": _Chat()})()


def test_output_types_are_exactly_the_four(monkeypatch):
    assert generators.OUTPUT_TYPES == ["quiz", "flashcards", "summary", "study_plan"]
    # quiz is the interactive tail, not a fan-out artifact
    assert generators.ARTIFACT_TYPES == ["flashcards", "summary", "study_plan"]
    assert "notes" not in generators.OUTPUT_TYPES


def test_gen_flashcards_parses_front_back_pairs(monkeypatch):
    payload = '{"cards":[{"front":"What is a closure?","back":"A function plus its captured scope."},{"front":"Why use useCallback?","back":"To keep a function reference stable."}]}'
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client(payload), "m"))

    cards = generators.gen_flashcards("material")

    assert cards == [
        {"front": "What is a closure?", "back": "A function plus its captured scope."},
        {"front": "Why use useCallback?", "back": "To keep a function reference stable."},
    ]


def test_gen_flashcards_drops_malformed_cards(monkeypatch):
    payload = '{"cards":[{"front":"Good?","back":"Yes."},{"front":"","back":"no front"},{"back":"missing front"},{"front":"no back"}]}'
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client(payload), "m"))

    cards = generators.gen_flashcards("material")

    assert cards == [{"front": "Good?", "back": "Yes."}]


def test_gen_flashcards_returns_empty_on_unparseable_json(monkeypatch):
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client("not json at all"), "m"))
    assert generators.gen_flashcards("material") == []


def test_gen_summary_returns_prose(monkeypatch):
    monkeypatch.setattr(generators, "_get_client",
                        lambda: (_fake_client("  Closures capture scope.  "), "m"))
    assert generators.gen_summary("material") == "Closures capture scope."


def test_gen_study_plan_parses_numbered_steps(monkeypatch):
    payload = '{"steps":[{"title":"Understand scope","detail":"Read about lexical scope."},{"title":"Practise closures","detail":"Write three counters."}]}'
    monkeypatch.setattr(generators, "_get_client", lambda: (_fake_client(payload), "m"))

    plan = generators.gen_study_plan("material")

    assert plan == [
        {"step": 1, "title": "Understand scope", "detail": "Read about lexical scope."},
        {"step": 2, "title": "Practise closures", "detail": "Write three counters."},
    ]


def test_generate_dispatches_by_type(monkeypatch):
    monkeypatch.setattr(generators, "_get_client",
                        lambda: (_fake_client('{"cards":[{"front":"f","back":"b"}]}'), "m"))
    assert generators.generate("flashcards", "material") == [{"front": "f", "back": "b"}]


def test_generate_rejects_an_unknown_type(monkeypatch):
    with pytest.raises(ValueError, match="unknown artifact type"):
        generators.generate("horoscope", "material")
