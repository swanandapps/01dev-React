from app.grounding import loader


def test_reads_the_repo_prompt_not_the_fallback():
    text = loader.read_grounding_prompt()
    assert text != loader.FALLBACK_PROMPT
    assert "CASE: NOT_ENROLLED_MATCH" in text
    assert "Hermes" not in text


def test_prompt_has_all_three_cases_and_lecture_mode():
    text = loader.read_grounding_prompt()
    for marker in ("CASE: ENROLLED_MATCH", "CASE: NOT_ENROLLED_MATCH", "CASE: NO_MATCH", "MODE: in-lecture"):
        assert marker in text


def test_fingerprint_is_stable_and_short():
    assert loader.prompt_fingerprint() == loader.prompt_fingerprint()
    assert len(loader.prompt_fingerprint()) == 12


def test_falls_back_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, "PROMPT_PATH", tmp_path / "missing.md")
    assert loader.read_grounding_prompt() == loader.FALLBACK_PROMPT
