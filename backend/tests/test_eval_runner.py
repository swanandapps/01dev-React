import json

from app.eval import retrieval_systems as rs
from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row
from app.models import TranscriptChunk
from scripts import eval_retrieval as ev


import pytest

from app.services import catalog_service

FAKE_CATALOG = [
    {"id": 2, "slug": "custom-library", "title": "Custom Library", "launched": True, "url": "/course/2"},
    {"id": 11, "slug": "react-perf", "title": "React Perf", "launched": False, "url": "/course/11"},
]


@pytest.fixture(autouse=True)
def _fake_catalog(monkeypatch):
    """Never depend on the live launched flags: a two-course catalog, one launched."""
    monkeypatch.setattr(catalog_service, "all_courses", lambda: FAKE_CATALOG)


@pytest.fixture
async def owner(monkeypatch):
    from app.services import course_lookup as cl
    monkeypatch.setattr(cl, "_enrollments", cl._enrollments)  # restored on teardown
    await rs.own_every_course()


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


async def test_legacy_ask_uses_real_lookup_policy_and_navigate(monkeypatch, owner):
    from app.services import course_lookup as cl, tutor_agent

    async def lookup(q, student, scope):
        assert scope == cl.ChatScope() and not scope.in_player  # Ask: no course, no player
        cat = cl.Hit(source="catalog", course_id=2, course_slug="custom-library", course_title="C",
                     title="C", score=0.5, enrolled=True)
        tr = cl.Hit(source="transcript", course_id=2, course_slug="custom-library", course_title="C",
                    title="T", score=0.6, enrolled=True, lecture_id="custom-library-5-2")
        return cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[cat, tr], enrolled_titles=[])

    async def hits(q, scope, top_k=8):
        assert tuple(scope) == ("custom-library",)   # ask mode: launched AND owned only (react-perf is unlaunched)
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


def test_rows_for_mode_ask_keeps_only_launched_courses():
    rows = [_row("a"), _row("b", scope_course="react-perf")]
    assert [r.id for r in ev.rows_for_mode(rows, "ask")] == ["a"]
    assert [r.id for r in ev.rows_for_mode(rows, "player")] == ["a", "b"]


async def test_owner_of_every_course_enrolls_all_catalog_ids(monkeypatch):
    from app.services import course_lookup as cl
    monkeypatch.setattr(cl, "_enrollments", cl._enrollments)  # restore after own_every_course patches it
    await rs.own_every_course()
    ids, _ = await cl._enrollments(rs.EVAL_STUDENT)
    assert ids == {2, 11}


def test_refuses_when_database_url_set(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    assert ev.main(["--label", "x"]) == 2


def test_rows_for_mode_ask_all_widens_to_every_course_but_keeps_exclusions():
    rows = [_row("a"), _row("b", scope_course="react-perf"), _row("n", intent="navigate"),
            _row("c", style="cross_course", expect=NOT_COVERED)]
    assert [r.id for r in ev.rows_for_mode(rows, "ask_all")] == ["a", "b"]


def test_all_courses_launched_patches_and_restores():
    from app.services import course_lookup as cl
    assert cl._is_launched(11) is False
    with rs.all_courses_launched():
        assert cl._is_launched(11) is True and cl._is_launched(999) is False
    assert cl._is_launched(11) is False
    assert rs.launched_slugs("ask") == ["custom-library"] and rs.launched_slugs("ask_all") == ["custom-library", "react-perf"]


async def test_catalog_only_match_is_partial_and_records_case(monkeypatch):
    from app.services import course_lookup as cl

    async def lookup(q, student, scope):
        cat = cl.Hit(source="catalog", course_id=2, course_slug="custom-library", course_title="C",
                     title="C", score=0.5, enrolled=True)
        return cl.CourseLookup(case=cl.LookupCase.ENROLLED_MATCH, hits=[cat], enrolled_titles=[])

    async def hits(q, scope, top_k=8):
        return []

    monkeypatch.setattr(cl, "course_lookup", lookup)
    monkeypatch.setattr(cl, "_transcript_hits", hits)
    p = await rs.LegacySystem().predict(_row("a", expect=NOT_COVERED, gold_lecture_ids=[]), "ask")
    assert (p.outcome, p.cited_lecture, p.lookup_case) == (PARTIAL, None, "enrolled_match")


async def test_ask_ranking_is_the_whole_fused_list_scoped_to_launched_owned(monkeypatch, owner):
    from app.services import course_lookup as cl
    from app.retrieval import pipeline

    def other(lid):
        c = _chunk(lid)
        return c.model_copy(update={"course_id": "react-perf"})

    seen = {}

    async def hits(q, scope, top_k=8):
        seen["top_k"], seen["scope"] = top_k, tuple(scope)
        rows = [(other("react-perf-1-0"), 0.9), (_chunk("custom-library-5-2"), 0.8), (_chunk("custom-library-9-0"), 0.7)]
        return [(c, sc) for c, sc in rows if c.course_id in scope]

    monkeypatch.setattr(cl, "_transcript_hits", hits)
    ranked = await rs.LegacySystem._ask_ranking("q")
    assert seen["top_k"] == pipeline.VEC_K + pipeline.LEX_K and seen["scope"] == ("custom-library",)
    assert ranked == ["custom-library-5-2", "custom-library-9-0"]


def test_watched_lecture_is_deterministic_non_gold_and_respects_explicit_title(monkeypatch):
    from app.services.vector_store import vector_store
    chunks = [_chunk(f"custom-library-{i}-0") for i in range(6)]
    monkeypatch.setattr(vector_store, "chunks", chunks)
    row = _row("a", gold_lecture_ids=["custom-library-5-2", "custom-library-1-0"])
    first = rs.watched_lecture(row)
    assert first == rs.watched_lecture(row) and first not in ("T custom-library-1-0",)
    assert rs.watched_lecture(_row("a", lecture_title="Given")) == "Given"
    assert rs.watched_lecture(_row("z", scope_course="nope")) is None


async def test_run_latency_sample_is_sequential_decision_only():
    calls = []

    class Fake:
        name = "fake"

        async def predict(self, row, mode, rank=True):
            calls.append((row.id, rank))
            return Prediction(row.id, mode, [], COVERED, None, latency_ms=7)

    rows = [_row(f"r{i}") for i in range(10)]
    out = await ev.run_latency_sample(Fake(), rows, "player", 4)
    assert len(out) == 4 and all(rank is False for _, rank in calls)
    assert [r.id for r in ev.latency_sample_rows(rows, 4)] == [p.row_id for p in out]


def test_build_run_takes_latency_from_the_sample_and_records_config_and_shown():
    rows = {r.id: r for r in [_row("a")]}
    main = {"player": [Prediction("a", "player", ["custom-library-5-2"], COVERED, "custom-library-5-2",
                                  latency_ms=999, shown_lectures=["custom-library-9-0", "custom-library-5-2"])]}
    sample = {"player": [Prediction("a", "player", [], COVERED, "custom-library-5-2", latency_ms=12)]}
    run = ev.build_run("x", "legacy", rows, main, config={"concurrency": 6}, latency_by_mode=sample)
    o = run["modes"]["player"]["overall"]
    assert (o["latency_p50_ms"], o["latency_p95_ms"], o["shown@3"]) == (12, 12, 1.0)
    assert run["config"] == {"concurrency": 6} and run["latency_sample"]["player"]["n"] == 1
    assert run["predictions"][0]["latency_ms"] == 0.0


def test_rerun_replaces_history_line_and_missing_compare_fails_before_writing(tmp_path):
    rows = {r.id: r for r in [_row("a")]}
    preds = {"player": [Prediction("a", "player", ["custom-library-5-2"], COVERED, "custom-library-5-2", latency_ms=9)]}
    ev.write_report(ev.build_run("lbl", "legacy", rows, preds), tmp_path)
    ev.write_report(ev.build_run("lbl", "legacy", rows, preds), tmp_path)
    assert sum("| lbl | legacy | player |" in ln for ln in (tmp_path / "HISTORY.md").read_text().splitlines()) == 1
    with pytest.raises(FileNotFoundError):
        ev.write_report(ev.build_run("other", "legacy", rows, preds), tmp_path, compare_to="missing")
    assert not (tmp_path / "other.json").exists()


def test_compare_warns_on_config_difference():
    from app.eval.retrieval_metrics import compare
    rows = {r.id: r for r in [_row("a")]}
    preds = {"player": [Prediction("a", "player", ["custom-library-5-2"], COVERED, "custom-library-5-2")]}
    a = ev.build_run("a", "legacy", rows, preds, config={"concurrency": 6, "git_sha": "x"})
    b = ev.build_run("b", "legacy", rows, preds, config={"concurrency": 1, "git_sha": "y"})
    out = compare(a, b)
    assert "WARNING" in out and "concurrency" in out and "git_sha" not in out


def test_refuses_without_openai_embeddings(monkeypatch):
    from app.services.embeddings import embedding_service
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(embedding_service, "use_openai", False)
    assert ev.main(["--label", "x"]) == 2


async def test_v2_mapping(monkeypatch):
    from app.retrieval import pipeline
    from app.retrieval.base import Candidate
    from app.retrieval.rerank import Graded, Outcome

    async def fake_graded(question, scope, **kw):
        assert list(scope) == ["custom-library"] and kw["history"] == [] and kw["lecture_title"] is None
        a, b = Candidate(chunk=_chunk("custom-library-9-0")), Candidate(chunk=_chunk("custom-library-5-2"))
        return pipeline.RetrievalResult(Outcome.PARTIAL, [Graded(b, "partial", "x"), Graded(a, "related", "y")],
                                        fallback=True)

    async def fake_search(question, scope, **kw):
        return [Candidate(chunk=_chunk("custom-library-1-0")), Candidate(chunk=_chunk("custom-library-9-0"))]

    monkeypatch.setattr(pipeline, "graded_search", fake_graded)
    monkeypatch.setattr(pipeline, "search", fake_search)
    p = await rs.V2System().predict(_row("a"), "player")
    assert (p.outcome, p.cited_lecture, p.fallback) == (PARTIAL, "custom-library-5-2", True)
    assert p.ranked_lectures == ["custom-library-5-2", "custom-library-9-0", "custom-library-1-0"]
    assert p.shown_lectures == ["custom-library-5-2"]
    assert (await rs.V2System().predict(_row("a"), "player", rank=False)).ranked_lectures == []
