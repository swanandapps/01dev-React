import pytest


@pytest.mark.asyncio
async def test_explain_concept_wraps_the_service(monkeypatch):
    from app.mcp import the01dev_tools
    from app.services import concept_explain

    async def fake_explain(user_id, concept):
        assert (user_id, concept) == ("student-1", "react-memo")
        return {
            "concept": "react-memo", "attempts": 4, "correct": 3, "accuracy": 0.75,
            "sources": [
                {"label": "React Performance Patterns", "source": "course",
                 "attempts": 2, "correct": 2, "last_at": "2026-09-01T00:00:00+00:00"},
                {"label": "React Perf Notes", "source": "self_study",
                 "attempts": 2, "correct": 1, "last_at": "2026-09-18T00:00:00+00:00"},
            ],
            "merged_tags": [{"candidate": "useCallback hook", "count": 2}],
        }

    monkeypatch.setattr(concept_explain, "explain_concept", fake_explain)

    out = await the01dev_tools.explain_concept(concept="react-memo", student_id="student-1")

    assert out["accuracy"] == 0.75
    assert {s["source"] for s in out["sources"]} == {"course", "self_study"}
    assert out["merged_tags"][0]["candidate"] == "useCallback hook"
