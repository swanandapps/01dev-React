from app.services import gepa_service


def test_soul_path_is_repo_relative_not_user_home():
    # Regression: gepa_service._SOUL used to be `~/.hermes/SOUL.md`, a path
    # that only exists on a machine that's run the Hermes CLI locally — on
    # a deployed container it silently fell back to the generic
    # _FALLBACK_SOUL persona instead of the real tutor identity. Must
    # resolve inside this repo instead.
    assert "hermes/SOUL.md" in str(gepa_service._SOUL)
    assert not str(gepa_service._SOUL).startswith("/root/.hermes")
    assert ".hermes" not in gepa_service._SOUL.parts


def test_read_soul_returns_the_real_persona_not_the_fallback():
    soul = gepa_service.read_soul()
    assert soul != gepa_service._FALLBACK_SOUL
    assert "0.1% Dev" in soul or "the01.dev" in soul
