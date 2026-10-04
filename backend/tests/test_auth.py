import pytest
from fastapi import HTTPException

from app import auth


async def test_valid_token_returns_uid(monkeypatch):
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", lambda token, app=None: {"uid": "u-123"})
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    assert await auth.current_student("Bearer good-token") == "u-123"


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic abc", "good-token"])
async def test_missing_or_malformed_header_is_401(header):
    with pytest.raises(HTTPException) as e:
        await auth.current_student(header)
    assert e.value.status_code == 401


async def test_expired_or_invalid_token_is_401_not_500(monkeypatch):
    def boom(token, app=None):
        raise auth.fb_auth.ExpiredIdTokenError("Token expired, 1700000000 < 1800000000", cause=None)
    monkeypatch.setattr(auth.fb_auth, "verify_id_token", boom)
    monkeypatch.setattr(auth, "_firebase_app", lambda: None)
    with pytest.raises(HTTPException) as e:
        await auth.current_student("Bearer stale")
    assert e.value.status_code == 401
    assert "expired" not in e.value.detail.lower() or "sign in" in e.value.detail.lower()
    assert "1700000000" not in e.value.detail


async def test_verifier_outage_is_503_without_leaking_internals(monkeypatch):
    def boom(token, app=None):
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
