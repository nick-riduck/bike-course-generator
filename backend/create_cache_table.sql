CREATE TABLE IF NOT EXISTS search_query_cache (
    query VARCHAR(255) PRIMARY KEY,
    embedding halfvec(3072),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
