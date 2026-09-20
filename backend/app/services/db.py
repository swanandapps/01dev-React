"""
Shared async Postgres connection pool (asyncpg) for the durable store + RAG index.

One pool for the whole process, created lazily on first use so import-time code
(`store = _init_store()`) stays synchronous. Handles the Neon specifics:
  - TLS is required (SSL context passed explicitly; libpq-only DSN params like
    sslmode / channel_binding are stripped — asyncpg rejects them).
  - The connection string uses Neon's PgBouncer pooler, so the prepared-statement
    cache is disabled (statement_cache_size=0) to avoid transaction-pooling errors.
  - jsonb <-> dict is handled by a codec, so the store passes/returns plain dicts.
"""
import asyncio
import json
import os
import ssl
import urllib.parse as up

import asyncpg

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()


def _dsn() -> str:
    """DATABASE_URL with query params (sslmode/channel_binding) stripped for asyncpg."""
    p = up.urlsplit(os.environ["DATABASE_URL"])
    return up.urlunsplit((p.scheme, p.netloc, p.path, "", ""))


async def _configure(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def _init_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("create extension if not exists vector")
        await conn.execute(
            """
            create table if not exists docs (
                collection text not null,
                doc_id     text not null,
                data       jsonb not null,
                updated_at timestamptz not null default now(),
                primary key (collection, doc_id)
            );
            create index if not exists docs_collection_idx on docs (collection);
            """
        )
        # Full-text index for cross-session memory search over student turns
        # (session_search): keyword FTS over question+answer, no embeddings/OpenAI.
        await conn.execute(
            """
            create index if not exists docs_turns_fts on docs
            using gin (to_tsvector('english',
                coalesce(data->>'question','') || ' ' || coalesce(data->>'answer','')))
            where collection = 'student_turns';
            """
        )
        await conn.execute(
            """
            create table if not exists rag_chunks (
                chunk_id  text primary key,
                text      text not null,
                meta      jsonb not null,
                embedding vector(1536)
            );
            """
        )


async def get_pool() -> asyncpg.Pool:
    """Lazily create (once) and return the shared pool."""
    global _pool
    if _pool is None:
        async with _lock:
            if _pool is None:
                pool = await asyncpg.create_pool(
                    dsn=_dsn(),
                    ssl=ssl.create_default_context(),
                    min_size=1,
                    max_size=5,
                    statement_cache_size=0,  # required for Neon's PgBouncer pooler
                    init=_configure,
                )
                await _init_schema(pool)
                _pool = pool
    return _pool


async def ping() -> bool:
    """True if the DB is reachable (used by /health)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("select 1")
        return True
    except Exception:  # noqa: BLE001
        return False
