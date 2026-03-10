#!/usr/bin/env python3
"""
벡터 인덱스 벤치마크: MRL 768차원 vs halfvec 3072차원

비교 항목:
1. 인덱스 생성 가능 여부
2. 인덱스 크기
3. 쿼리 속도 (top-5 검색)
4. Recall (3072 풀스캔 대비 결과 일치율)

Usage:
    python scripts/benchmark_vector_index.py
"""

import os
import sys
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from google import genai

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# 검색 테스트용 쿼리들
TEST_QUERIES = [
    "한강 자전거길",
    "업힐 산악",
    "바다 해안 도로",
    "초보 평지 라이딩",
    "서울 근교 당일치기",
    "강원도 산",
    "야간 라이딩",
    "국토종주",
    "카페 맛집",
    "벚꽃 봄",
]

TOP_K = 5
BENCHMARK_RUNS = 20  # 쿼리당 반복 횟수 (워밍업 후 평균)


def get_embedding(text: str, dims: int = None) -> list[float]:
    """Gemini 임베딩 생성. dims 지정 시 MRL 적용."""
    config = {}
    if dims:
        config["output_dimensionality"] = dims
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=config,
    )
    return result.embeddings[0].values


def setup_benchmark_tables(conn):
    """벤치마크용 테이블 생성."""
    cur = conn.cursor()

    print("[1/4] 벤치마크 테이블 생성...")

    # halfvec 확장 확인
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 기존 벤치마크 테이블 정리
    cur.execute("DROP TABLE IF EXISTS bench_mrl768;")
    cur.execute("DROP TABLE IF EXISTS bench_halfvec3072;")
    cur.execute("DROP TABLE IF EXISTS bench_fullscan3072;")

    # 방안 2: MRL 768차원 (vector)
    cur.execute("""
        CREATE TABLE bench_mrl768 (
            id INTEGER PRIMARY KEY,
            slug VARCHAR(50),
            embedding vector(768)
        );
    """)

    # 방안 3: halfvec 3072차원
    cur.execute("""
        CREATE TABLE bench_halfvec3072 (
            id INTEGER PRIMARY KEY,
            slug VARCHAR(50),
            embedding halfvec(3072)
        );
    """)

    # 기준: 3072 풀스캔 (인덱스 없음)
    cur.execute("""
        CREATE TABLE bench_fullscan3072 (
            id INTEGER PRIMARY KEY,
            slug VARCHAR(50),
            embedding vector(3072)
        );
    """)

    conn.commit()
    cur.close()


def populate_tables(conn):
    """기존 태그 데이터 + MRL 768 임베딩 생성."""
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 기존 3072 임베딩 로드
    cur.execute("SELECT id, slug, embedding::text FROM tags WHERE embedding IS NOT NULL ORDER BY id")
    tags = cur.fetchall()
    print(f"[2/4] 태그 {len(tags)}개 로드 완료")

    # fullscan3072, halfvec3072 채우기 (기존 임베딩 사용)
    cur2 = conn.cursor()
    for tag in tags:
        emb_str = tag["embedding"]
        # fullscan3072
        cur2.execute(
            "INSERT INTO bench_fullscan3072 (id, slug, embedding) VALUES (%s, %s, %s::vector)",
            (tag["id"], tag["slug"], emb_str),
        )
        # halfvec3072
        cur2.execute(
            "INSERT INTO bench_halfvec3072 (id, slug, embedding) VALUES (%s, %s, %s::halfvec)",
            (tag["id"], tag["slug"], emb_str),
        )
    conn.commit()
    print(f"  fullscan3072, halfvec3072 채움")

    # MRL 768 임베딩 생성
    print(f"  MRL 768 임베딩 생성 중 ({len(tags)}개)...")
    for i, tag in enumerate(tags):
        emb768 = get_embedding(tag["slug"], dims=768)
        cur2.execute(
            "INSERT INTO bench_mrl768 (id, slug, embedding) VALUES (%s, %s, %s::vector)",
            (tag["id"], tag["slug"], str(emb768)),
        )
        if (i + 1) % 50 == 0:
            print(f"    {i+1}/{len(tags)}")
            conn.commit()
    conn.commit()
    print(f"  MRL 768 임베딩 생성 완료")
    cur.close()
    cur2.close()


def create_indexes(conn):
    """HNSW 인덱스 생성."""
    cur = conn.cursor()
    print("[3/4] 인덱스 생성...")

    # MRL 768 - HNSW
    t0 = time.time()
    cur.execute("""
        CREATE INDEX idx_bench_mrl768_hnsw
        ON bench_mrl768 USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    conn.commit()
    t_mrl = time.time() - t0
    print(f"  MRL 768 HNSW: {t_mrl:.3f}s")

    # halfvec 3072 - HNSW
    t0 = time.time()
    cur.execute("""
        CREATE INDEX idx_bench_halfvec3072_hnsw
        ON bench_halfvec3072 USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    conn.commit()
    t_half = time.time() - t0
    print(f"  halfvec 3072 HNSW: {t_half:.3f}s")

    # 인덱스 크기
    cur.execute("""
        SELECT
            indexname,
            pg_size_pretty(pg_relation_size(indexname::regclass)) as size,
            pg_relation_size(indexname::regclass) as size_bytes
        FROM pg_indexes
        WHERE tablename LIKE 'bench_%'
        AND indexname LIKE '%hnsw%'
        ORDER BY indexname;
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.close()
    return t_mrl, t_half


def benchmark_queries(conn):
    """쿼리 속도 + recall 비교."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    print(f"[4/4] 쿼리 벤치마크 ({len(TEST_QUERIES)}개 쿼리 × {BENCHMARK_RUNS}회)...")

    results = []

    for query_text in TEST_QUERIES:
        # 임베딩 생성 (3072 + 768)
        emb3072 = get_embedding(query_text)
        emb768 = get_embedding(query_text, dims=768)
        emb3072_str = str(emb3072)
        emb768_str = str(emb768)

        # --- Ground truth: 3072 풀스캔 ---
        cur.execute(f"""
            SELECT id, slug, 1 - (embedding <=> %s::vector) as similarity
            FROM bench_fullscan3072
            ORDER BY embedding <=> %s::vector
            LIMIT {TOP_K}
        """, (emb3072_str, emb3072_str))
        gt_ids = [r["id"] for r in cur.fetchall()]
        gt_slugs = []
        cur.execute(f"""
            SELECT id, slug, 1 - (embedding <=> %s::vector) as similarity
            FROM bench_fullscan3072
            ORDER BY embedding <=> %s::vector
            LIMIT {TOP_K}
        """, (emb3072_str, emb3072_str))
        gt_results = cur.fetchall()
        gt_ids = [r["id"] for r in gt_results]
        gt_slugs = [r["slug"] for r in gt_results]

        # --- MRL 768 HNSW ---
        times_mrl = []
        for _ in range(BENCHMARK_RUNS):
            t0 = time.time()
            cur.execute(f"""
                SELECT id, slug, 1 - (embedding <=> %s::vector) as similarity
                FROM bench_mrl768
                ORDER BY embedding <=> %s::vector
                LIMIT {TOP_K}
            """, (emb768_str, emb768_str))
            mrl_results = cur.fetchall()
            times_mrl.append(time.time() - t0)
        mrl_ids = [r["id"] for r in mrl_results]
        mrl_recall = len(set(mrl_ids) & set(gt_ids)) / TOP_K

        # --- halfvec 3072 HNSW ---
        times_half = []
        for _ in range(BENCHMARK_RUNS):
            t0 = time.time()
            cur.execute(f"""
                SELECT id, slug, 1 - (embedding <=> %s::halfvec) as similarity
                FROM bench_halfvec3072
                ORDER BY embedding <=> %s::halfvec
                LIMIT {TOP_K}
            """, (emb3072_str, emb3072_str))
            half_results = cur.fetchall()
            times_half.append(time.time() - t0)
        half_ids = [r["id"] for r in half_results]
        half_recall = len(set(half_ids) & set(gt_ids)) / TOP_K

        # --- 3072 풀스캔 속도 ---
        times_full = []
        for _ in range(BENCHMARK_RUNS):
            t0 = time.time()
            cur.execute(f"""
                SELECT id, slug, 1 - (embedding <=> %s::vector) as similarity
                FROM bench_fullscan3072
                ORDER BY embedding <=> %s::vector
                LIMIT {TOP_K}
            """, (emb3072_str, emb3072_str))
            cur.fetchall()
            times_full.append(time.time() - t0)

        avg_mrl = sum(times_mrl[2:]) / len(times_mrl[2:]) * 1000  # skip warmup
        avg_half = sum(times_half[2:]) / len(times_half[2:]) * 1000
        avg_full = sum(times_full[2:]) / len(times_full[2:]) * 1000

        results.append({
            "query": query_text,
            "fullscan_ms": round(avg_full, 2),
            "mrl768_ms": round(avg_mrl, 2),
            "halfvec3072_ms": round(avg_half, 2),
            "mrl768_recall": mrl_recall,
            "halfvec3072_recall": half_recall,
            "gt_top5": gt_slugs,
            "mrl_top5": [r["slug"] for r in mrl_results],
            "half_top5": [r["slug"] for r in half_results],
        })

        print(f"  \"{query_text}\"")
        print(f"    fullscan: {avg_full:.2f}ms | mrl768: {avg_mrl:.2f}ms | halfvec: {avg_half:.2f}ms")
        print(f"    recall — mrl768: {mrl_recall:.0%} | halfvec: {half_recall:.0%}")
        if mrl_recall < 1.0:
            print(f"    GT:  {gt_slugs}")
            print(f"    MRL: {[r['slug'] for r in mrl_results]}")

    cur.close()
    return results


def cleanup(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS bench_mrl768;")
    cur.execute("DROP TABLE IF EXISTS bench_halfvec3072;")
    cur.execute("DROP TABLE IF EXISTS bench_fullscan3072;")
    conn.commit()
    cur.close()


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    print("=== 벡터 인덱스 벤치마크 ===\n")

    try:
        setup_benchmark_tables(conn)
        populate_tables(conn)
        t_mrl_idx, t_half_idx = create_indexes(conn)
        results = benchmark_queries(conn)

        # 최종 요약
        print("\n" + "=" * 60)
        print("=== 최종 요약 ===\n")

        avg_full = sum(r["fullscan_ms"] for r in results) / len(results)
        avg_mrl = sum(r["mrl768_ms"] for r in results) / len(results)
        avg_half = sum(r["halfvec3072_ms"] for r in results) / len(results)
        avg_recall_mrl = sum(r["mrl768_recall"] for r in results) / len(results)
        avg_recall_half = sum(r["halfvec3072_recall"] for r in results) / len(results)

        print(f"{'':20s} {'fullscan 3072':>15s} {'MRL 768+HNSW':>15s} {'halfvec 3072+HNSW':>18s}")
        print(f"{'인덱스':20s} {'없음':>15s} {'HNSW':>15s} {'HNSW':>18s}")
        print(f"{'인덱스 생성시간':20s} {'N/A':>15s} {t_mrl_idx:>14.3f}s {t_half_idx:>17.3f}s")
        print(f"{'평균 쿼리 속도':20s} {avg_full:>14.2f}ms {avg_mrl:>14.2f}ms {avg_half:>17.2f}ms")
        print(f"{'평균 Recall@5':20s} {'100%':>15s} {avg_recall_mrl:>14.0%} {avg_recall_half:>17.0%}")
        print(f"{'저장 차원':20s} {'3072':>15s} {'768':>15s} {'3072 (half)':>18s}")

        # 결과 저장
        output = {
            "summary": {
                "fullscan_avg_ms": round(avg_full, 2),
                "mrl768_avg_ms": round(avg_mrl, 2),
                "halfvec3072_avg_ms": round(avg_half, 2),
                "mrl768_avg_recall": round(avg_recall_mrl, 3),
                "halfvec3072_avg_recall": round(avg_recall_half, 3),
                "index_build_mrl_s": round(t_mrl_idx, 3),
                "index_build_half_s": round(t_half_idx, 3),
            },
            "queries": results,
        }
        out_path = os.path.join(os.path.dirname(__file__), "benchmark_vector_results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n→ 상세 결과: {out_path}")

    finally:
        cleanup(conn)
        conn.close()


if __name__ == "__main__":
    main()
