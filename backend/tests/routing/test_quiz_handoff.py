from app.routing.quiz_handoff import build_handoff_message


def test_handoff_mentions_quizme_and_the_course():
    msg = build_handoff_message("react-performance")
    assert "Lab" in msg
    assert "notes" in msg.lower()
