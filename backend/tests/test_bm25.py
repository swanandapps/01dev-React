from app.retrieval.bm25 import BM25Index


DOCS = [["iife", "scope", "function"], ["npm", "publish", "np", "np"], ["module", "scope"], ["np"] + ["filler"] * 40]


def test_rare_term_and_term_frequency_rank_first():
    idx = BM25Index(DOCS)
    out = idx.search(["np"], None, 10)
    assert [i for i, _ in out] == [1, 3]                    # tf 2 in a short doc beats tf 1 in a long doc
    assert out[0][1] > out[1][1] > 0


def test_allowed_positions_filter_and_k():
    idx = BM25Index(DOCS)
    assert [i for i, _ in idx.search(["scope"], {2}, 10)] == [2]
    assert len(idx.search(["scope"], None, 1)) == 1
    assert idx.search(["missing"], None, 10) == []
    assert idx.search([], None, 10) == []


def test_repeated_query_terms_count_once_and_ties_break_by_position():
    idx = BM25Index([["a1", "b1"], ["a1", "b1"]])
    assert idx.search(["a1", "a1"], None, 5) == idx.search(["a1"], None, 5)
    assert [i for i, _ in idx.search(["a1"], None, 5)] == [0, 1]


def test_empty_corpus():
    assert BM25Index([]).search(["np"], None, 5) == []
