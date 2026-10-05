from app.services import catalog_index
from app.services.embeddings import embedding_service


def test_one_entry_per_course_and_per_module():
    entries = catalog_index.build_entries()
    lib = [e for e in entries if e.course_id == 2]
    assert sum(1 for e in lib if e.module_title is None) == 1
    assert any(e.module_title == "NPM Package Development" and "npm link" in e.text for e in lib)


async def test_search_ranks_by_similarity(monkeypatch):
    catalog_index.reset()

    async def fake_embed(text: str):
        return [1.0, 0.0] if "npm" in text.lower() else [0.0, 1.0]

    monkeypatch.setattr(embedding_service, "embed", fake_embed)
    hits = await catalog_index.search("how do I publish an npm package", top_k=3)
    assert hits[0][0].module_title == "NPM Package Development"
    assert hits[0][1] > 0.99
    catalog_index.reset()
