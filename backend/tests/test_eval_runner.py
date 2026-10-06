import json

from app.eval import retrieval_systems as rs
from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row
from app.models import TranscriptChunk
from scripts import eval_retrieval as ev


def _row(id, **kw):
    base = dict(id=id, question="q", scope_course="custom-library", expect=COVERED,
                gold_lecture_ids=["custom-library-5-2"])
    return Row(**{**base, **kw})


def _chunk(lid, n=0):
    return TranscriptChunk(chunk_id=f"{lid}-{n}", course_id="custom-library", course_title="C", lecture_id=lid,
                           lecture_title=f"T {lid}", text="t", start_time=n * 60, end_time=n * 60 + 60)


def test_rows_for_mode_ask_skips_navigate_and_cross_course():
    rows = [_row("a"), _row("b", intent="navigate"), _row("c", style="cross_course", expect=NOT_COVERED)]
    assert [r.id for r in ev.rows_for_mode(rows, "player")] == ["a", "b", "c"]
    assert [r.id for r in ev.rows_for_mode(rows, "ask")] == ["a"]


async def test_run_system_records_errors_and_keeps_order():
    class Fake:
        name = "fake"

        async def predict(self, row, mode):
            if row.id == "b":
                raise TimeoutError("slow")
            return Prediction(row.id, mode, ["custom-library-5-2"], COVERED, "custom-library-5-2", latency_ms=5)

    preds = await ev.run_system(Fake(), [_row("a"), _row("b"), _row("c")], "player", concurrency=2)
    assert [p.row_id for p in preds] == ["a", "b", "c"]
    assert preds[1].error == "TimeoutError('slow')" and preds[0].error is None


def test_write_report_writes_json_md_history_and_compare(tmp_path):
    rows = {r.id: r for r in [_row("a")]}
    preds = {"player": [Prediction("a", "player", ["custom-library-5-2"], COVERED, "custom-library-5-2", latency_ms=9)]}
    base = ev.build_run("phase1-baseline", "legacy", rows, preds)
    ev.write_report(base, tmp_path)
    assert base["modes"]["player"]["clean"]["counts"]["positives"] == 1
    new = ev.build_run("phase2-enriched", "legacy", rows, preds)
    j, md = ev.write_report(new, tmp_path, compare_to="phase1-baseline")
    assert json.loads(j.read_text())["label"] == "phase2-enriched"
    assert "Delta: phase1-baseline → phase2-enriched" in md.read_text()
    history = (tmp_path / "HISTORY.md").read_text().splitlines()
    assert sum("| phase1-baseline | legacy | player |" in line for line in history) == 1
    assert sum("| phase2-enriched | legacy | player |" in line for line in history) == 1


def test_check_targets_names_misses():
    misses = ev.check_targets({"recall@5": 0.95, "coverage_accuracy": 0.8, "false_cite_rate": 0.05,
                               "latency_p95_ms": 1200.0})
    assert misses == ["coverage_accuracy 0.800 (target >= 0.9)", "false_cite_rate 0.050 (target <= 0.03)"]


async def test_legacy_player_mapping(monkeypatch):
    from app.services import course_lookup as cl

    async def lookup(q, student, scope):
        assert scope.in_player and scope.course_slug == "custom-library"
        hit = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="C",
                     title="T", score=0.5, enrolled=True, lecture_id="custom-library-5-2")
        return cl.CourseLookup(case=cl.LookupCase.IN_COURSE_RELATED, hits=[hit], enrolled_titles=[])

    async def in_course(q, slug, top_k=8):
        return [(_chunk("custom-library-9-0"), 0.5), (_chunk("custom-library-5-2"), 0.45),
                (_chunk("custom-library-9-0", 1), 0.44)]

    monkeypatch.setattr(cl, "course_lookup", lookup)
    monkeypatch.setattr(cl, "search_in_course", in_course)
    p = await rs.LegacySystem().predict(_row("a"), "player")
    assert (p.outcome, p.cited_lecture) == (PARTIAL, "custom-library-5-2")
    assert p.ranked_lectures == ["custom-library-9-0", "custom-library-5-2"]


async def test_legacy_ask_uses_real_lookup_policy_and_navigate(monkeypatch):
    from app.services import course_lookup as cl, tutor_agent

    async def lookup(q, student, scope):
        assert scope == cl.ChatScope() and not scope.in_player  # Ask: no course, no player
        cat = cl.Hit(source="catalog", course_id=2, course_slug="custom-library", course_title="C",
                     title="C", score=0.5, enrolled=True)
        tr = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="C",
                    title="T", score=0.6, enrolled=True, lecture_id="custom-library-5-2")
        return cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[cat, tr], enrolled_titles=[])

    async def hits(q, top_k=8):
        return [(_chunk("custom-library-9-0"), 0.6), (_chunk("custom-library-5-2"), 0.5)]

    async def locate(what, slug):
        assert what == "np"
        return _chunk("custom-library-10-0"), 0.7

    monkeypatch.setattr(cl, "course_lookup", lookup)
    monkeypatch.setattr(cl, "_transcript_hits", hits)
    monkeypatch.setattr(tutor_agent, "_locate_moment", locate)
    p = await rs.LegacySystem().predict(_row("a"), "ask")
    assert (p.outcome, p.cited_lecture) == (COVERED, "custom-library-5-2")
    assert p.ranked_lectures == ["custom-library-9-0", "custom-library-5-2"]
    nav = await rs.LegacySystem().predict(_row("n", intent="navigate", navigate_phrase="np"), "player")
    assert nav.moment_lecture == "custom-library-10-0"


async def test_legacy_ask_catalog_only_is_not_covered(monkeypatch):
    from app.services import course_lookup as cl

    async def lookup(q, student, scope):
        cat = cl.Hit(source="catalog", course_id=2, course_slug="custom-library", course_title="C",
                     title="C", score=0.5, enrolled=True)
        return cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[cat], enrolled_titles=[])

    async def hits(q, top_k=8):
        return []

    monkeypatch.setattr(cl, "course_lookup", lookup)
    monkeypatch.setattr(cl, "_transcript_hits", hits)
    p = await rs.LegacySystem().predict(_row("a"), "ask")
    assert (p.outcome, p.cited_lecture) == (NOT_COVERED, None)


def test_rows_for_mode_ask_keeps_only_launched_courses():
    rows = [_row("a"), _row("b", scope_course="react-perf")]
    assert [r.id for r in ev.rows_for_mode(rows, "ask")] == ["a"]
    assert [r.id for r in ev.rows_for_mode(rows, "player")] == ["a", "b"]


async def test_owner_of_every_course_enrolls_all_catalog_ids(monkeypatch):
    from app.services import course_lookup as cl
    monkeypatch.setattr(cl, "_enrollments", cl._enrollments)  # restore after own_every_course patches it
    await rs.own_every_course()
    ids, _ = await cl._enrollments(rs.EVAL_STUDENT)
    assert 2 in ids and 11 in ids


def test_refuses_when_database_url_set(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    assert ev.main(["--label", "x"]) == 2
