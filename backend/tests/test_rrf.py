from app.models import TranscriptChunk
from app.retrieval.base import RRF_K, rrf_fuse


def _c(cid, lecture):
    return TranscriptChunk(chunk_id=cid, course_id="c", course_title="C", lecture_id=lecture, lecture_title=lecture,
                           text=cid, start_time=0, end_time=1)


A, B, C, D, E = _c("a", "L1"), _c("b", "L1"), _c("c", "L2"), _c("d", "L1"), _c("e", "L1")


def test_rrf_formula_ranks_and_scores():
    out = rrf_fuse([[(A, 0.9), (C, 0.5)]], [[(C, 7.0), (B, 3.0)]], limit=10, per_lecture=None)
    assert [x.chunk.chunk_id for x in out] == ["c", "a", "b"]
    c = out[0]
    assert c.fused == 1 / (RRF_K + 2) + 1 / (RRF_K + 1)
    assert (c.vec_rank, c.lex_rank, c.vec_score, c.lex_score) == (2, 1, 0.5, 7.0)
    assert (out[1].vec_rank, out[1].lex_rank) == (1, None)


def test_per_lecture_cap_and_limit():
    vec = [[(A, 0.9), (B, 0.8), (D, 0.7), (E, 0.6), (C, 0.5)]]
    out = rrf_fuse(vec, [], limit=12, per_lecture=3)
    assert [x.chunk.chunk_id for x in out] == ["a", "b", "d", "c"]      # 4th chunk of L1 dropped
    assert len(rrf_fuse(vec, [], limit=2, per_lecture=3)) == 2


def test_multiple_lists_keep_the_best_rank_and_ties_prefer_vector_rank():
    out = rrf_fuse([[(A, 0.9)], [(B, 0.95), (A, 0.4)]], [[(B, 1.0)], [(A, 2.0)]], limit=5, per_lecture=None)
    a = next(x for x in out if x.chunk.chunk_id == "a")
    assert a.vec_rank == 1 and a.vec_score == 0.9 and a.lex_rank == 1
    assert rrf_fuse([], [], limit=5) == []
