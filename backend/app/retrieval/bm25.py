"""Okapi BM25 over pre-tokenized docs (app.retrieval.text.lexical_doc), pure Python.
idf = ln(1 + (N - df + 0.5) / (df + 0.5)); a query term counts once however often it is typed."""
import math
from collections import Counter, defaultdict
from typing import Optional


class BM25Index:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.lens = [len(d) for d in docs]
        self.avg = (sum(self.lens) / len(docs)) if docs else 1.0
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for term, tf in Counter(d).items():
                self.postings[term].append((i, tf))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def search(self, query_tokens: list[str], allowed: Optional[set[int]], k: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in dict.fromkeys(query_tokens):
            for i, tf in self.postings.get(term, ()):
                if allowed is not None and i not in allowed:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avg or 1.0))
                scores[i] += self.idf[term] * tf * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda t: (-t[1], t[0]))[:k]
