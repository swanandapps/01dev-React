"""Who is asking: verifies the Firebase ID token the frontend sends.

The student id is the token's uid — the same id the frontend used to send in
the request body, so existing data keys don't change. Body/header ids are
ignored on routes that use this dependency.
"""
import asyncio
import os

import firebase_admin
import google.auth.credentials
from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "topdev-93530")
_APP_NAME = "token-verifier"

# Problems with the token itself → 401. ExpiredIdTokenError and RevokedIdTokenError
# subclass InvalidIdTokenError; UserDisabledError does not.
_TOKEN_ERRORS = (fb_auth.InvalidIdTokenError, fb_auth.UserDisabledError, ValueError)


class _NoCredential(firebase_admin.credentials.Base):
    # Verifying ID tokens needs only Google's public certs (fetched over HTTPS);
    # firebase_admin still checks signature, aud, iss, sub and expiry. Without this,
    # the app falls back to ApplicationDefault and every verify raises
    # DefaultCredentialsError where no service account is configured.
    def get_credential(self):
        return google.auth.credentials.AnonymousCredentials()


def _firebase_app():
    try:
        return firebase_admin.get_app(_APP_NAME)
    except ValueError:
        return firebase_admin.initialize_app(
            credential=_NoCredential(), options={"projectId": FIREBASE_PROJECT_ID}, name=_APP_NAME
        )


async def current_student(authorization: str = Header(default="")) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Sign in to use the AI tutor")
    try:
        decoded = await asyncio.to_thread(fb_auth.verify_id_token, token.strip(), app=_firebase_app())
    except _TOKEN_ERRORS:
        raise HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    except Exception as exc:  # noqa: BLE001 — verifier/setup outage, not the student's fault
        print(f"[auth] token verification unavailable: {exc!r}", flush=True)
        raise HTTPException(status_code=503, detail="The tutor is temporarily unavailable. Please try again.")
    return decoded["uid"]
