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


def test_falls_back_when_file_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(loader, "PROMPT_PATH", tmp_path / "missing.md")
    assert loader.read_grounding_prompt() == loader.FALLBACK_PROMPT
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1 and "FALLBACK" in out.upper() and "missing.md" in out


def test_falls_back_with_a_warning_when_file_empty(monkeypatch, tmp_path, capsys):
    empty = tmp_path / "empty.md"
    empty.write_text("  \n")
    monkeypatch.setattr(loader, "PROMPT_PATH", empty)
    assert loader.read_grounding_prompt() == loader.FALLBACK_PROMPT
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


def test_no_warning_when_the_prompt_file_is_read(capsys):
    loader.read_grounding_prompt()
    assert capsys.readouterr().out == ""
