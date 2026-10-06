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


def test_prompt_has_the_in_course_cases_and_tone_matching():
    text = loader.read_grounding_prompt()
    for marker in ("CASE: IN_COURSE_MATCH", "CASE: IN_COURSE_RELATED", "CASE: IN_COURSE_NONE"):
        assert marker in text
    assert "match the student's tone, vocabulary and level from their messages and STUDENT MEMORY" in text
    assert "never name, recommend or link another course" in text.lower()
    assert "is about the current lecture whatever the in_course case" in " ".join(text.lower().split())


def test_prompt_in_course_citation_and_length_rules():
    text = " ".join(loader.read_grounding_prompt().lower().split())
    assert "never cite a lecture or time that is not listed under matches" in text
    assert "weak matches are only the closest moments" in text
    assert "a question that isn't about the current lecture gets a full answer" in text


def test_prompt_lists_find_moment():
    text = loader.read_grounding_prompt()
    assert "find_moment" in text and "never invent a lecture or a time" in text.lower()


def test_prompt_vague_lecture_request_is_never_only_a_question():
    text = " ".join(loader.read_grounding_prompt().split())
    assert "is never answered with only a question back" in text


def test_find_moment_is_restricted_to_explicit_navigation_requests():
    from app.services import tool_descriptions as D
    text = " ".join(loader.read_grounding_prompt().split())
    for t in (text, " ".join(D.FIND_MOMENT.split())):
        assert "ONLY when the student explicitly asks" in t
        assert "search_course_content" in t
        assert "never call it to look something up" in t.lower()


def test_prompt_has_the_all_cases_citation_rule():
    text = " ".join(loader.read_grounding_prompt().split())
    head, _, _ = text.partition("## Every IN_COURSE case")
    assert "## Every case" in head
    assert "use only what is listed under Matches" in head
    assert "returned by a tool such as find_moment" in head and "CURRENT LECTURE" in head
    assert "Never combine or blend two course names" in head
    assert "is not a pointer" in head and "get_enrolled_courses" in head
    assert "name no course at all" not in head


def test_prompt_enrolled_case_asks_for_the_deep_link_and_no_match_names_no_course():
    text = " ".join(loader.read_grounding_prompt().split())
    assert "the01.dev/course/<id>?chapter=<c>&sub=<s>&t=<seconds>" in text
    assert "t=87" not in text   # the placeholder is clearly fake: the real demo link must not be copyable
    assert "Name no course, lecture, link or time" in text
    assert "You're not enrolled in it yet" not in text


def test_prompt_builds_examples_from_the_lecture_and_the_running_project():
    text = " ".join(loader.read_grounding_prompt().split())
    assert "running project" in text and "COURSE DESCRIPTION" in text
    assert "don't invent a different example domain" in text.lower()


def test_player_prompt_forbids_writing_links():
    text = " ".join(loader.read_grounding_prompt().split())
    _, _, player = text.partition("## Every IN_COURSE case")
    assert "Never write a URL or link yourself" in player
