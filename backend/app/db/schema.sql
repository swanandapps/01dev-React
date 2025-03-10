-- pgvector production schema
-- Run after: CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS transcript_chunks (
    chunk_id     VARCHAR PRIMARY KEY,
    course_id    VARCHAR NOT NULL,
    course_title VARCHAR NOT NULL,
    lecture_id   VARCHAR NOT NULL,
    lecture_title VARCHAR NOT NULL,
    text         TEXT NOT NULL,
    start_time   INTEGER NOT NULL DEFAULT 0,
    end_time     INTEGER NOT NULL DEFAULT 0,
    -- text-embedding-3-small = 1536 dims; local fallback = 256 dims
    embedding    vector(1536)
);

CREATE INDEX IF NOT EXISTS transcript_chunks_embedding_idx
    ON transcript_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS transcript_chunks_course_idx
    ON transcript_chunks (course_id);

-- Example similarity search (replace $1 and $2 with query embedding and threshold):
-- SELECT *, 1 - (embedding <=> $1::vector) AS score
-- FROM transcript_chunks
-- WHERE 1 - (embedding <=> $1::vector) > $2
-- ORDER BY embedding <=> $1::vector
-- LIMIT 5;
