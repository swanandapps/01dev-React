"""Shared FastAPI dependencies used across route modules.

Lives here (rather than inline in app/main.py, where it originated) so route
modules imported by main.py — e.g. app.services.lab.routes — can depend on it
without a circular import back into main.py.
"""
import os

from fastapi import Header, HTTPException

# Admin/audit/compliance routes (audit log, memory transparency+erase, eval
# RAG outputs + history, lab audit) have no per-user auth model yet — gate
# them with a shared secret instead of leaving them open on a public URL.
# Unset locally on purpose (dev convenience); Railway sets a real value.
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


async def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    if not _ADMIN_API_KEY:
        return  # no key configured (local dev) — leave routes open, same as today
    if x_admin_key != _ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Admin-Key")
