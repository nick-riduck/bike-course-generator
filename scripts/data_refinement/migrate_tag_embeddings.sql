-- Tag embedding migration for semantic tag search
-- Requires pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE tags ADD COLUMN IF NOT EXISTS embedding vector(3072);

-- NOTE: pgvector 0.8.x limits HNSW/IVFFlat to 2000 dimensions.
-- With ~226 tags, sequential scan is fast enough (<1ms).
-- Add index when pgvector supports >2000 dims or if tag count exceeds ~10k.
