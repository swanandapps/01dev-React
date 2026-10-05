"""
"Why is this my strong topic?" — answered from data already stored.

concept_performance is only a running counter, so it cannot explain itself.
But quiz_sessions already records every answer with its concept, so the
attribution exists; this module is the read path over it. No new collection.

Matching is against the student's own answers only. Exact slugify() equality
wins; failing that, every concept of theirs whose slug words contain the asked
name's words (or vice versa) is counted — the model asks about "React.memo"
while the resolver stored "react-memo-purpose". If nothing matches,
`known_concepts` lists their real names so the model can ask again. This is a
READ path: it never calls concept_resolver.resolve(), which can create nodes.

`merged_tags` are the loosely-named tags (`raw_concept` on this student's own
answers) that were folded into the concept, which makes a merge auditable AND
contestable: if the student says "those aren't the same thing", that is the best
possible signal to split. The global concept_resolutions log is deliberately not
read — it carries no student id, so using it would leak other students' notes.
"""
from app.services.concept_resolver import slugify
from app.services.store import store


KNOWN_CONCEPTS_LIMIT = 20


def _matching_slugs(target: str, slugs: set[str]) -> set[str]:
    if target in slugs:
        return {target}
    words = set(target.split("-"))
    return {s for s in slugs
            if words <= set(s.split("-")) or set(s.split("-")) <= words}


async def explain_concept(user_id: str, concept: str) -> dict:
    sessions = await store.query("quiz_sessions", "user_id", user_id)
    counts: dict[str, int] = {}
    for s in sessions:
        for a in s.get("answers", []):
            slug = slugify(a.get("concept", ""))
            if slug:
                counts[slug] = counts.get(slug, 0) + 1
    targets = _matching_slugs(slugify(concept), set(counts))

    buckets: dict[tuple, dict] = {}
    merged: dict[str, int] = {}
    attempts = correct = 0
    for s in sessions:
        matching = [a for a in s.get("answers", []) if slugify(a.get("concept", "")) in targets]
        if not matching:
            continue
        source = s.get("source", "course")
        # Lab sessions carry a generic course_title ("Your own material"); the
        # document title is the meaningful label for self-study.
        if source in ("self_study", "lecture"):
            label = s.get("doc_title") or s.get("course_title")
        else:
            label = s.get("course_title") or s.get("doc_title")
        label = label or "Unknown source"
        # Key on the source's identity, not its label: a course titled "X" and a
        # Lab doc titled "X" are different sources. Label only as a last resort.
        key = (source, s.get("doc_id") or s.get("course_id") or label)
        done = s.get("completed_at", "")
        b = buckets.setdefault(key, {
            "label": label, "source": source, "attempts": 0, "correct": 0, "last_at": done})
        for a in matching:
            b["attempts"] += 1
            attempts += 1
            if a.get("correct"):
                b["correct"] += 1
                correct += 1
            raw = (a.get("raw_concept") or "").strip()
            if raw and slugify(raw) not in targets:
                merged[raw] = merged.get(raw, 0) + 1
        if done > b["last_at"]:
            b["last_at"] = done

    out = {
        "concept": concept,
        "matched_concepts": sorted(targets),
        "attempts": attempts,
        "correct": correct,
        "accuracy": round(correct / attempts, 3) if attempts else None,
        "sources": sorted(buckets.values(), key=lambda b: (-b["attempts"], b["label"])),
        "merged_tags": [{"candidate": c, "count": n}
                        for c, n in sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))],
    }
    if not targets:
        out["known_concepts"] = [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                                 ][:KNOWN_CONCEPTS_LIMIT]
    return out
