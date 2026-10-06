"""Retrieval-eval metrics — pure functions, no I/O and no models (spec §5).

A Row is one labelled question; a Prediction is what a system did with it in one mode
("player" = scope is the row's course, "ask" = scope is every course). Navigate rows are scored
only by navigate accuracy; explain rows by recall/MRR (positives), coverage accuracy (all) and
false-cite rate (negatives). A PARTIAL outcome names a lecture, so on a negative it is a false cite.
"""
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

COVERED, PARTIAL, NOT_COVERED = "covered", "partial", "not_covered"
METRIC_KEYS = ["recall@1", "recall@5", "mrr", "coverage_accuracy", "cite_accuracy", "partial_rate_pos",
               "false_cite_rate", "navigate_accuracy", "fallback_rate", "latency_p50_ms", "latency_p95_ms"]


@dataclass
class Row:
    id: str
    question: str
    scope_course: str
    expect: str                                   # COVERED | NOT_COVERED
    gold_lecture_ids: list[str] = field(default_factory=list)
    gold_chunk_ids: list[str] = field(default_factory=list)
    style: str = "direct"                         # direct|casual|keyword|how_do_i|off_topic|cross_course|follow_up
    intent: str = "explain"                       # explain | navigate
    source: str = "generated"                     # generated | hand
    history: list[dict] = field(default_factory=list)
    lecture_title: Optional[str] = None
    navigate_phrase: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Row":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Prediction:
    row_id: str
    mode: str                                     # "player" | "ask"
    ranked_lectures: list[str]                    # distinct lecture ids, best first
    outcome: str                                  # COVERED | PARTIAL | NOT_COVERED
    cited_lecture: Optional[str]                  # lecture of the cited chunk, None when nothing cited
    moment_lecture: Optional[str] = None          # navigate rows: where the player would jump
    latency_ms: float = 0.0
    fallback: bool = False                        # reranker fell back to the fused rule
    error: Optional[str] = None


def _mean(values: Iterable) -> Optional[float]:
    vals = [float(v) for v in values]
    return round(sum(vals) / len(vals), 4) if vals else None


def _rr(ranked: list[str], gold: list[str]) -> float:
    for i, lid in enumerate(ranked, 1):
        if lid in gold:
            return 1.0 / i
    return 0.0


def percentile(values: list[float], p: float) -> Optional[float]:
    """Nearest-rank percentile; None for no values."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def summarize(rows: dict[str, Row], preds: list[Prediction]) -> dict:
    ok = [(rows[p.row_id], p) for p in preds if p.error is None]
    explain = [(r, p) for r, p in ok if r.intent == "explain"]
    pos = [(r, p) for r, p in explain if r.expect == COVERED and r.gold_lecture_ids]
    neg = [(r, p) for r, p in explain if r.expect == NOT_COVERED]
    nav = [(r, p) for r, p in ok if r.intent == "navigate"]
    lat = [p.latency_ms for _, p in ok]
    return {
        "recall@1": _mean(bool(set(p.ranked_lectures[:1]) & set(r.gold_lecture_ids)) for r, p in pos),
        "recall@5": _mean(bool(set(p.ranked_lectures[:5]) & set(r.gold_lecture_ids)) for r, p in pos),
        "mrr": _mean(_rr(p.ranked_lectures, r.gold_lecture_ids) for r, p in pos),
        "coverage_accuracy": _mean((p.outcome == COVERED) == (r.expect == COVERED) for r, p in explain),
        "cite_accuracy": _mean(p.cited_lecture in r.gold_lecture_ids for r, p in pos if p.outcome == COVERED),
        "partial_rate_pos": _mean(p.outcome == PARTIAL for _, p in pos),
        "false_cite_rate": _mean(p.outcome in (COVERED, PARTIAL) for _, p in neg),
        "navigate_accuracy": _mean(p.moment_lecture in r.gold_lecture_ids for r, p in nav),
        "fallback_rate": _mean(p.fallback for _, p in ok),
        "latency_p50_ms": percentile(lat, 50),
        "latency_p95_ms": percentile(lat, 95),
        "counts": {"positives": len(pos), "negatives": len(neg), "navigate": len(nav),
                   "errors": sum(p.error is not None for p in preds)},
    }


def per_course(rows: dict[str, Row], preds: list[Prediction]) -> dict[str, dict]:
    groups: dict[str, list[Prediction]] = {}
    for p in preds:
        groups.setdefault(rows[p.row_id].scope_course, []).append(p)
    return {slug: summarize(rows, ps) for slug, ps in sorted(groups.items())}


def _fmt(v) -> str:
    return "—" if v is None else (f"{v:.0f}" if isinstance(v, float) and v > 1.0 else f"{v:.3f}")


def render_markdown(run: dict) -> str:
    out = [f"# Retrieval eval — {run['label']}", "",
           f"System: `{run['system']}` · created {run['created']}", ""]
    for mode, data in run["modes"].items():
        o = data["overall"]
        out += [f"## Mode: {mode}", "", f"Counts: {o['counts']}", "", "| metric | value |", "|---|---|"]
        out += [f"| {k} | {_fmt(o.get(k))} |" for k in METRIC_KEYS]
        if data.get("per_course"):
            keys = ["recall@1", "recall@5", "mrr", "coverage_accuracy", "false_cite_rate", "navigate_accuracy"]
            out += ["", "| course | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
            for slug, s in data["per_course"].items():
                out.append(f"| {slug} | " + " | ".join(_fmt(s.get(k)) for k in keys) + " |")
        out.append("")
    return "\n".join(out)


def compare(base: dict, new: dict) -> str:
    out = [f"# Delta: {base['label']} → {new['label']}", ""]
    for mode in new["modes"]:
        if mode not in base["modes"]:
            continue
        b, n = base["modes"][mode]["overall"], new["modes"][mode]["overall"]
        out += [f"## Mode: {mode}", "", f"| metric | {base['label']} | {new['label']} | delta |", "|---|---|---|---|"]
        for k in METRIC_KEYS:
            bv, nv = b.get(k), n.get(k)
            delta = "—" if bv is None or nv is None else f"{nv - bv:+.3f}"
            fmt = (lambda v: "—" if v is None else f"{v:.3f}")
            out.append(f"| {k} | {fmt(bv)} | {fmt(nv)} | {delta} |")
        out.append("")
    return "\n".join(out)