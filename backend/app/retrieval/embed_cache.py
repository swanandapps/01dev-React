"""Opt-in on-disk embedding cache for LOCAL runs (eval, demo checks): set RAG_EMBED_CACHE=<dir>.
Keyed by content_hash (which already includes the embedding model), one JSON line per vector.
Never used in prod or tests (the variable is unset there)."""
import json
import os
from pathlib import Path
from typing import Optional

from app.services.embeddings import EMBED_MODEL

FILE = f"{EMBED_MODEL}.jsonl"


class EmbedCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict[str, list[float]] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                try:
                    row = json.loads(line)
                    self._data[row["k"]] = row["v"]
                except (ValueError, KeyError, TypeError):
                    continue  # e.g. a truncated last line

    @classmethod
    def from_env(cls) -> Optional["EmbedCache"]:
        d = os.getenv("RAG_EMBED_CACHE")
        return cls(Path(d) / FILE) if d else None

    def get_many(self, keys) -> dict[str, list[float]]:
        return {k: self._data[k] for k in keys if k in self._data}

    def put_many(self, items: dict[str, list[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            for k, v in items.items():
                f.write(json.dumps({"k": k, "v": v}) + "\n")
        self._data.update(items)
