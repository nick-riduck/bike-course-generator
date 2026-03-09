-- Tag embedding migration for semantic tag search
-- Requires pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;

-- 기존 vector(3072) → halfvec(3072) 마이그레이션
-- halfvec(float16): HNSW 인덱스 지원 (vector float32는 2,000차원 제한)
-- 벤치마크: Recall 100%, 인덱스 크기 MRL의 2배지만 재임베딩 불필요
-- 상세: docs/db/benchmark_vector_index.md

-- Case 1: 기존 vector(3072) 컬럼이 있는 경우 (타입 변환)
ALTER TABLE tags ALTER COLUMN embedding TYPE halfvec(3072)
    USING embedding::halfvec;

-- Case 2: 컬럼이 없는 경우 (신규 추가)
-- ALTER TABLE tags ADD COLUMN IF NOT EXISTS embedding halfvec(3072);

-- HNSW 인덱스 생성 (cosine distance)
CREATE INDEX IF NOT EXISTS idx_tags_embedding ON tags
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
