#!/usr/bin/env python3
"""
Backfill embeddings for existing tags that have embedding IS NULL.
Uses gemini-embedding-001 via Vertex AI.

Usage:
    python scripts/data_refinement/embed_existing_tags.py
"""
import os
import sys
import time

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env'))

from google import genai

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "riduck"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def get_embedding(text: str) -> list[float]:
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
    )
    return result.embeddings[0].values


def main():
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("SELECT id, slug FROM tags WHERE embedding IS NULL ORDER BY id")
    tags = cur.fetchall()

    print(f"Found {len(tags)} tags without embeddings")

    success = 0
    errors = 0

    for i, tag in enumerate(tags):
        try:
            emb = get_embedding(tag["slug"])
            cur.execute(
                "UPDATE tags SET embedding = %s::vector WHERE id = %s",
                (str(emb), tag["id"]),
            )
            conn.commit()
            success += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(tags)}] Processed '{tag['slug']}' ...")
        except Exception as e:
            print(f"  ERROR: tag '{tag['slug']}' (id={tag['id']}): {e}")
            conn.rollback()
            errors += 1
            time.sleep(1)  # Rate limit backoff

    cur.close()
    conn.close()

    print(f"\nDone: {success} success, {errors} errors out of {len(tags)} tags")


if __name__ == "__main__":
    main()
