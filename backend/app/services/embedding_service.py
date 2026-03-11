import os
from app.core.database import get_db_conn

_client = None

def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    return _client

def query_cache(text: str) -> list[float] | None:
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT embedding FROM search_query_cache WHERE query = %s", (text,))
                row = cur.fetchone()
                if row and row['embedding']:
                    emb_str = row['embedding']
                    if isinstance(emb_str, str):
                        emb_str = emb_str.strip('[]')
                        return [float(x) for x in emb_str.split(',')]
                    elif isinstance(emb_str, list):
                        return emb_str
    except Exception as e:
        print(f"[Embedding Cache] DB query error: {e}")
    return None

def set_cache(text: str, embedding_values: list[float]):
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO search_query_cache (query, embedding) VALUES (%s, %s::halfvec) ON CONFLICT (query) DO NOTHING",
                    (text, str(embedding_values))
                )
            conn.commit()
    except Exception as e:
        print(f"[Embedding Cache] DB set error: {e}")

def get_embedding(text: str) -> list[float]:
    # 1. Try to get from cache
    cached_emb = query_cache(text)
    if cached_emb is not None:
        print(f"[Embedding Cache] HIT for '{text}'")
        return cached_emb

    print(f"[Embedding Cache] MISS for '{text}'. Calling Gemini API...")

    # 2. Fetch from Gemini API
    client = _get_client()
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
    )
    embedding_values = result.embeddings[0].values

    # 3. Save to cache
    set_cache(text, embedding_values)

    return embedding_values
