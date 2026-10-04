import pytest
from fastapi import HTTPException

from app import auth


async def test_valid_token_returns_uid(monkeypatch):
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", lambda token, app=None, **kw: {"uid": "u-123"})
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    assert await auth.current_student("Bearer good-token") == "u-123"


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic abc", "good-token"])
async def test_missing_or_malformed_header_is_401(header):
    with pytest.raises(HTTPException) as e:
        await auth.current_student(header)
    assert e.value.status_code == 401


async def test_expired_or_invalid_token_is_401_not_500(monkeypatch):
    def boom(token, app=None, **kw):
        raise auth.fb_auth.ExpiredIdTokenError("Token expired, 1700000000 < 1800000000", cause=None)
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", boom)
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer stale")
    assert e.value.status_code == 401
    assert "expired" not in e.value.detail.lower() or "sign in" in e.value.detail.lower()
    assert "1700000000" not in e.value.detail


async def test_verifier_outage_is_503_without_leaking_internals(monkeypatch):
    def boom(token, app=None, **kw):
        raise RuntimeError("cert fetch failed")
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", boom)
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer whatever")
    assert e.value.status_code == 503
    assert "cert" not in e.value.detail.lower()


async def test_real_verifier_without_service_account_rejects_bad_token_401():
    # Not mocked: the real "token-verifier" app runs firebase_admin's verifier with
    # no service-account credential. A malformed token is rejected before any cert
    # fetch, so this needs no network. A missing-credential setup error would be 503.
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer not-a-real-token")
    assert e.value.status_code == 401


async def test_emulator_env_is_refused_503_and_verify_never_runs(monkeypatch):
    # firebase_admin skips signature checks when FIREBASE_AUTH_EMULATOR_HOST is set.
    called = []
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", lambda *a, **kw: called.append(1) or {"uid": "forged"})
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer forged")
    assert e.value.status_code == 503
    assert called == []


async def test_setup_value_error_is_503_not_401(monkeypatch):
    def broken_setup():
        raise ValueError("bad app options")
    called = []
    monkeypatch.setattr(auth, "_firebase_app", broken_setup)
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", lambda *a, **kw: called.append(1) or {"uid": "x"})
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer whatever")
    assert e.value.status_code == 503
    assert called == []


async def test_verify_allows_five_seconds_clock_skew(monkeypatch):
    seen = {}

    def spy(token, app=None, **kw):
        seen.update(kw, token=token)
        return {"uid": "u-1"}
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", spy)
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    assert await auth.current_student("Bearer tok") == "u-1"
    assert seen["clock_skew_seconds"] == 5 and seen["token"] == "tok"


def test_empty_project_id_env_still_verifies_against_topdev(monkeypatch):
    # A separate copy of app/auth.py imported with FIREBASE_PROJECT_ID="" — reloading
    # app.auth itself would orphan the current_student used by dependency_overrides.
    import importlib.util

    import firebase_admin

    monkeypatch.setenv("FIREBASE_PROJECT_ID", "")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    spec = importlib.util.spec_from_file_location("auth_copy", auth.__file__)
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    copy._APP_NAME = "token-verifier-test-copy"
    try:
        app = copy._firebase_app()
        assert copy.FIREBASE_PROJECT_ID == "topdev-93530"
        assert app.options.get("projectId") == "topdev-93530"
        assert app.options.get("httpTimeout") == 10
    finally:
        firebase_admin.delete_app(firebase_admin.get_app("token-verifier-test-copy"))
