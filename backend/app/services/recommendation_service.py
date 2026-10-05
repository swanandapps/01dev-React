"""
Recommendations cache — only the invalidation hook survives.

The "what to study next" generator and its /api/ai/recommendations route were
removed as dead code; adaptive_service still clears any cached entry for a user
when they finish a session.
"""

from app.services.store import store

COLLECTION = "recommendations"


async def invalidate(user_id: str) -> None:
    await store.delete(COLLECTION, user_id)
