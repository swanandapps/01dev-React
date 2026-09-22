import app.services.lab.llm as llm_mod


def test_importing_llm_does_not_build_a_client():
    # Importing a service module must not construct an API client or require
    # credentials. This module used to do `_client, _MODEL = _make_client()`
    # at import time; the eagerly-built module attributes must be gone.
    #
    # Deliberately does NOT reload the module or touch sys.modules: that would
    # change module identity for every other test in the run.
    assert not hasattr(llm_mod, "_client"), "_client must not exist at module level"
    assert not hasattr(llm_mod, "_MODEL"), "_MODEL must not exist at module level"


def test_get_client_builds_once_and_caches(monkeypatch):
    calls = []

    def fake_make_client():
        calls.append(1)
        return ("CLIENT", "MODEL")

    # monkeypatch (not direct assignment) so the cache is restored afterwards
    # even if an assertion fails partway through.
    monkeypatch.setattr(llm_mod, "_CLIENT_CACHE", None)
    monkeypatch.setattr(llm_mod, "_make_client", fake_make_client)

    assert llm_mod._get_client() == ("CLIENT", "MODEL")
    assert llm_mod._get_client() == ("CLIENT", "MODEL")
    assert calls == [1], "client must be built once and cached"
