from app.eval import retrieval_metrics as m
from app.eval.retrieval_metrics import COVERED, NOT_COVERED, PARTIAL, Prediction, Row


def _rows():
    return {r.id: r for r in [
        Row(id="p1", question="what is an IIFE", scope_course="custom-library", expect=COVERED,
            gold_lecture_ids=["custom-library-5-2"]),
        Row(id="p2", question="np publish", scope_course="custom-library", expect=COVERED,
            gold_lecture_ids=["custom-library-10-0"]),
        Row(id="n1", question="sourdough", scope_course="custom-library", expect=NOT_COVERED, style="off_topic"),
        Row(id="n2", question="kubernetes pods", scope_course="react-perf", expect=NOT_COVERED, style="off_topic"),
        Row(id="v1", question="take me to the np part", scope_course="custom-library", expect=COVERED,
            gold_lecture_ids=["custom-library-10-0"], intent="navigate", navigate_phrase="np"),
    ]}


def _preds():
    return [
        Prediction("p1", "player", ["custom-library-5-2", "custom-library-9-0"], COVERED, "custom-library-5-2",
                   latency_ms=100),
        Prediction("p2", "player", ["custom-library-7-0", "custom-library-10-0"], PARTIAL, "custom-library-7-0",
                   latency_ms=300),
        Prediction("n1", "player", ["custom-library-0-0"], NOT_COVERED, None, latency_ms=200),
        Prediction("n2", "player", ["react-perf-4-0"], PARTIAL, "react-perf-4-0", latency_ms=400),
        Prediction("v1", "player", [], NOT_COVERED, None, moment_lecture="custom-library-10-0", latency_ms=500),
    ]


def test_summary_metrics():
    s = m.summarize(_rows(), _preds())
    assert s["recall@1"] == 0.5          # p1 hit at 1, p2 only at 2
    assert s["recall@5"] == 1.0
    assert s["mrr"] == 0.75              # (1 + 1/2) / 2
    # explain rows: p1 ok (covered), p2 wrong (partial != covered), n1 ok, n2 ok (partial is not "covered")
    assert s["coverage_accuracy"] == 0.75
    assert s["false_cite_rate"] == 0.5   # n2 cited something (partial counts as a cite)
    assert s["cite_accuracy"] == 1.0     # only p1 is covered, and it cites gold
    assert s["partial_rate_pos"] == 0.5
    assert s["navigate_accuracy"] == 1.0
    assert s["counts"] == {"positives": 2, "negatives": 2, "navigate": 1, "errors": 0}
    assert s["latency_p50_ms"] == 300 and s["latency_p95_ms"] == 500


def test_errors_are_counted_and_excluded():
    preds = _preds()
    preds[0] = Prediction("p1", "player", [], NOT_COVERED, None, error="TimeoutError()")
    s = m.summarize(_rows(), preds)
    assert s["counts"]["errors"] == 1 and s["counts"]["positives"] == 1


def test_empty_groups_give_none_not_zero_division():
    rows = {"n1": _rows()["n1"]}
    s = m.summarize(rows, [_preds()[2]])
    assert s["recall@5"] is None and s["navigate_accuracy"] is None and s["false_cite_rate"] == 0.0


def test_percentile_nearest_rank():
    assert m.percentile([], 95) is None
    assert m.percentile([5.0], 95) == 5.0
    assert m.percentile([float(i) for i in range(1, 101)], 95) == 95.0
    assert m.percentile([float(i) for i in range(1, 101)], 50) == 50.0


def test_per_course_groups_by_scope_course():
    pc = m.per_course(_rows(), _preds())
    assert set(pc) == {"custom-library", "react-perf"}
    assert pc["react-perf"]["false_cite_rate"] == 1.0


def test_markdown_and_compare():
    rows, preds = _rows(), _preds()
    run = {"label": "phase1-baseline", "system": "legacy", "created": "2026-10-06T00:00:00",
           "modes": {"player": {"overall": m.summarize(rows, preds), "per_course": m.per_course(rows, preds)}},
           "predictions": []}
    md = m.render_markdown(run)
    assert "phase1-baseline" in md and "| recall@5 |" in md and "custom-library" in md
    better = {**run, "label": "phase2", "modes": {"player": {"overall": {**run["modes"]["player"]["overall"],
                                                                        "recall@1": 1.0}, "per_course": {}}}}
    diff = m.compare(run, better)
    assert "| recall@1 | 0.500 | 1.000 | +0.500 |" in diff
