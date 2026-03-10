#!/usr/bin/env python3
"""
벡터 인덱스 벤치마크 v2 — 스케일 테스트 + 시각화

비교 대상:
  A) fullscan vector(3072) — 인덱스 없음 (현재 상태)
  B) MRL vector(768) + HNSW
  C) halfvec(3072) + HNSW

스케일: 227(실제) → 500 → 1000 → 2000 → 5000 (합성 데이터로 확장)

Output:
  scripts/benchmark_vector_v2_results.png
  scripts/benchmark_vector_v2_results.json
"""

import os
import sys
import time
import json
import random
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

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

SCALES = [227, 500, 1000, 2000, 5000]
TOP_K = 5
RUNS_PER_QUERY = 30
SCRIPT_DIR = os.path.dirname(__file__)


def get_embedding(text, dims=None):
    config = {}
    if dims:
        config["output_dimensionality"] = dims
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=config,
    )
    return result.embeddings[0].values


def generate_synthetic_embeddings(base_embeddings, target_count):
    """기존 임베딩에 노이즈를 추가해 합성 데이터 생성."""
    synth_3072 = []
    synth_768 = []
    base_3072 = [e["emb3072"] for e in base_embeddings]
    base_768 = [e["emb768"] for e in base_embeddings]

    while len(synth_3072) < target_count:
        idx = random.randint(0, len(base_3072) - 1)
        noise_scale = random.uniform(0.05, 0.3)

        vec3072 = np.array(base_3072[idx])
        noise = np.random.randn(3072) * noise_scale
        new_vec = vec3072 + noise
        new_vec = new_vec / np.linalg.norm(new_vec)  # normalize
        synth_3072.append(new_vec.tolist())

        vec768 = np.array(base_768[idx])
        noise768 = np.random.randn(768) * noise_scale
        new_vec768 = vec768 + noise768
        new_vec768 = new_vec768 / np.linalg.norm(new_vec768)
        synth_768.append(new_vec768.tolist())

    return synth_3072[:target_count], synth_768[:target_count]


def setup_tables(conn, n, base_data, synth_3072, synth_768):
    """특정 스케일에 대한 테이블 생성 + 데이터 삽입."""
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS bench_full;")
    cur.execute("DROP TABLE IF EXISTS bench_mrl;")
    cur.execute("DROP TABLE IF EXISTS bench_half;")

    cur.execute("CREATE TABLE bench_full (id INT PRIMARY KEY, embedding vector(3072));")
    cur.execute("CREATE TABLE bench_mrl (id INT PRIMARY KEY, embedding vector(768));")
    cur.execute("CREATE TABLE bench_half (id INT PRIMARY KEY, embedding halfvec(3072));")

    # 실제 데이터 삽입
    real_count = min(n, len(base_data))
    for i in range(real_count):
        e = base_data[i]
        cur.execute("INSERT INTO bench_full VALUES (%s, %s::vector)", (i, str(e["emb3072"])))
        cur.execute("INSERT INTO bench_mrl VALUES (%s, %s::vector)", (i, str(e["emb768"])))
        cur.execute("INSERT INTO bench_half VALUES (%s, %s::halfvec)", (i, str(e["emb3072"])))

    # 합성 데이터로 나머지 채움
    for i in range(real_count, n):
        si = i - len(base_data)
        cur.execute("INSERT INTO bench_full VALUES (%s, %s::vector)", (i, str(synth_3072[si])))
        cur.execute("INSERT INTO bench_mrl VALUES (%s, %s::vector)", (i, str(synth_768[si])))
        cur.execute("INSERT INTO bench_half VALUES (%s, %s::halfvec)", (i, str(synth_3072[si])))

    conn.commit()

    # 인덱스 생성
    t0 = time.time()
    cur.execute("""
        CREATE INDEX idx_bmrl ON bench_mrl
        USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
    """)
    conn.commit()
    t_mrl = time.time() - t0

    t0 = time.time()
    cur.execute("""
        CREATE INDEX idx_bhalf ON bench_half
        USING hnsw (embedding halfvec_cosine_ops) WITH (m=16, ef_construction=64);
    """)
    conn.commit()
    t_half = time.time() - t0

    # 인덱스 크기
    cur.execute("""
        SELECT indexname, pg_relation_size(indexname::regclass) as bytes
        FROM pg_indexes WHERE tablename IN ('bench_mrl', 'bench_half')
        AND indexname LIKE 'idx_b%'
    """)
    sizes = {row[0]: row[1] for row in cur.fetchall()}

    cur.close()
    return t_mrl, t_half, sizes.get("idx_bmrl", 0), sizes.get("idx_bhalf", 0)


def run_queries(conn, query_embeddings):
    """각 방식별 쿼리 속도 + recall 측정."""
    cur = conn.cursor()

    latencies = {"full": [], "mrl": [], "half": []}
    recalls = {"mrl": [], "half": []}

    for qe in query_embeddings:
        emb3072_str = str(qe["emb3072"])
        emb768_str = str(qe["emb768"])

        # Ground truth: fullscan 3072
        cur.execute(f"SELECT id FROM bench_full ORDER BY embedding <=> %s::vector LIMIT {TOP_K}", (emb3072_str,))
        gt_ids = set(r[0] for r in cur.fetchall())

        # Benchmark each method
        for _ in range(RUNS_PER_QUERY):
            # fullscan
            t0 = time.time()
            cur.execute(f"SELECT id FROM bench_full ORDER BY embedding <=> %s::vector LIMIT {TOP_K}", (emb3072_str,))
            cur.fetchall()
            latencies["full"].append(time.time() - t0)

            # mrl hnsw
            t0 = time.time()
            cur.execute(f"SELECT id FROM bench_mrl ORDER BY embedding <=> %s::vector LIMIT {TOP_K}", (emb768_str,))
            cur.fetchall()
            latencies["mrl"].append(time.time() - t0)

            # halfvec hnsw
            t0 = time.time()
            cur.execute(f"SELECT id FROM bench_half ORDER BY embedding <=> %s::halfvec LIMIT {TOP_K}", (emb3072_str,))
            cur.fetchall()
            latencies["half"].append(time.time() - t0)

        # Recall (1회)
        cur.execute(f"SELECT id FROM bench_mrl ORDER BY embedding <=> %s::vector LIMIT {TOP_K}", (emb768_str,))
        mrl_ids = set(r[0] for r in cur.fetchall())
        recalls["mrl"].append(len(mrl_ids & gt_ids) / TOP_K)

        cur.execute(f"SELECT id FROM bench_half ORDER BY embedding <=> %s::halfvec LIMIT {TOP_K}", (emb3072_str,))
        half_ids = set(r[0] for r in cur.fetchall())
        recalls["half"].append(len(half_ids & gt_ids) / TOP_K)

    cur.close()

    def percentiles(arr):
        a = sorted(arr)
        # skip first 10% as warmup
        a = a[len(a)//10:]
        return {
            "p50": np.percentile(a, 50) * 1000,
            "p95": np.percentile(a, 95) * 1000,
            "p99": np.percentile(a, 99) * 1000,
            "avg": np.mean(a) * 1000,
        }

    return {
        "latency": {k: percentiles(v) for k, v in latencies.items()},
        "recall": {k: np.mean(v) for k, v in recalls.items()},
    }


def cleanup(conn):
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS bench_full, bench_mrl, bench_half;")
    conn.commit()
    cur.close()


def plot_results(all_results, output_path):
    """결과 시각화."""
    fig = plt.figure(figsize=(16, 12))
    fig.suptitle("pgvector Index Benchmark: MRL 768 vs halfvec 3072 vs fullscan 3072",
                 fontsize=14, fontweight='bold', y=0.98)
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    scales = [r["n"] for r in all_results]

    # --- 1. Query Latency (p50) ---
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(scales, [r["latency"]["full"]["p50"] for r in all_results],
             'o-', label='fullscan 3072', color='#e74c3c', linewidth=2, markersize=8)
    ax1.plot(scales, [r["latency"]["mrl"]["p50"] for r in all_results],
             's-', label='MRL 768 + HNSW', color='#2ecc71', linewidth=2, markersize=8)
    ax1.plot(scales, [r["latency"]["half"]["p50"] for r in all_results],
             '^-', label='halfvec 3072 + HNSW', color='#3498db', linewidth=2, markersize=8)
    ax1.set_xlabel('Number of vectors')
    ax1.set_ylabel('Latency (ms)')
    ax1.set_title('Query Latency — p50 (median)')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_xscale('log')
    ax1.set_xticks(scales)
    ax1.set_xticklabels([str(s) for s in scales])

    # --- 2. Query Latency (p95) ---
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(scales, [r["latency"]["full"]["p95"] for r in all_results],
             'o-', label='fullscan 3072', color='#e74c3c', linewidth=2, markersize=8)
    ax2.plot(scales, [r["latency"]["mrl"]["p95"] for r in all_results],
             's-', label='MRL 768 + HNSW', color='#2ecc71', linewidth=2, markersize=8)
    ax2.plot(scales, [r["latency"]["half"]["p95"] for r in all_results],
             '^-', label='halfvec 3072 + HNSW', color='#3498db', linewidth=2, markersize=8)
    ax2.set_xlabel('Number of vectors')
    ax2.set_ylabel('Latency (ms)')
    ax2.set_title('Query Latency — p95 (tail)')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_xscale('log')
    ax2.set_xticks(scales)
    ax2.set_xticklabels([str(s) for s in scales])

    # --- 3. Recall@5 ---
    ax3 = fig.add_subplot(gs[1, 0])
    x = np.arange(len(scales))
    width = 0.35
    bars_mrl = ax3.bar(x - width/2, [r["recall"]["mrl"] * 100 for r in all_results],
                       width, label='MRL 768', color='#2ecc71', alpha=0.85)
    bars_half = ax3.bar(x + width/2, [r["recall"]["half"] * 100 for r in all_results],
                        width, label='halfvec 3072', color='#3498db', alpha=0.85)
    ax3.set_xlabel('Number of vectors')
    ax3.set_ylabel('Recall@5 (%)')
    ax3.set_title('Recall@5 vs fullscan ground truth')
    ax3.set_xticks(x)
    ax3.set_xticklabels([str(s) for s in scales])
    ax3.set_ylim(70, 102)
    ax3.axhline(y=100, color='#e74c3c', linestyle='--', alpha=0.5, label='fullscan (baseline)')
    ax3.legend(fontsize=9)
    ax3.grid(True, alpha=0.3, axis='y')
    # 값 표시
    for bar in bars_mrl:
        ax3.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                f'{bar.get_height():.0f}%', ha='center', va='bottom', fontsize=8)
    for bar in bars_half:
        ax3.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                f'{bar.get_height():.0f}%', ha='center', va='bottom', fontsize=8)

    # --- 4. Index Size ---
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.plot(scales, [r["idx_size_mrl"] / 1024 for r in all_results],
             's-', label='MRL 768 HNSW', color='#2ecc71', linewidth=2, markersize=8)
    ax4.plot(scales, [r["idx_size_half"] / 1024 for r in all_results],
             '^-', label='halfvec 3072 HNSW', color='#3498db', linewidth=2, markersize=8)
    ax4.set_xlabel('Number of vectors')
    ax4.set_ylabel('Index Size (KB)')
    ax4.set_title('HNSW Index Size')
    ax4.legend(fontsize=9)
    ax4.grid(True, alpha=0.3)
    ax4.set_xscale('log')
    ax4.set_xticks(scales)
    ax4.set_xticklabels([str(s) for s in scales])

    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"\n→ 차트 저장: {output_path}")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    print("=== 벡터 인덱스 벤치마크 v2 (스케일 테스트) ===\n")

    try:
        # Step 1: 실제 태그 임베딩 로드
        print("[1/5] 실제 태그 임베딩 로드...")
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, slug, embedding::text FROM tags WHERE embedding IS NOT NULL ORDER BY id")
        raw_tags = cur.fetchall()
        cur.close()
        print(f"  {len(raw_tags)}개 태그 로드")

        # Step 2: MRL 768 임베딩 생성
        print("[2/5] MRL 768 임베딩 생성...")
        base_data = []
        for i, tag in enumerate(raw_tags):
            emb768 = get_embedding(tag["slug"], dims=768)
            # parse 3072 from text
            emb3072 = json.loads(tag["embedding"])
            base_data.append({"emb3072": emb3072, "emb768": emb768})
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(raw_tags)}")
        print(f"  완료")

        # Step 3: 합성 데이터 생성
        max_synth = max(SCALES) - len(base_data)
        print(f"[3/5] 합성 데이터 생성 ({max_synth}개)...")
        synth_3072, synth_768 = generate_synthetic_embeddings(base_data, max_synth)
        print(f"  완료")

        # Step 4: 쿼리 임베딩 준비
        print("[4/5] 테스트 쿼리 임베딩 생성...")
        query_embeddings = []
        for qt in TEST_QUERIES:
            query_embeddings.append({
                "text": qt,
                "emb3072": get_embedding(qt),
                "emb768": get_embedding(qt, dims=768),
            })
        print(f"  {len(query_embeddings)}개 쿼리 준비 완료")

        # Step 5: 스케일별 벤치마크
        print("[5/5] 스케일별 벤치마크 시작...\n")
        all_results = []

        for n in SCALES:
            print(f"--- n={n} ---")
            setup_start = time.time()
            t_mrl, t_half, sz_mrl, sz_half = setup_tables(conn, n, base_data, synth_3072, synth_768)
            print(f"  테이블/인덱스 생성: {time.time()-setup_start:.1f}s")
            print(f"  인덱스: MRL={sz_mrl/1024:.0f}KB ({t_mrl:.3f}s) | halfvec={sz_half/1024:.0f}KB ({t_half:.3f}s)")

            qr = run_queries(conn, query_embeddings)
            print(f"  p50: full={qr['latency']['full']['p50']:.2f}ms | mrl={qr['latency']['mrl']['p50']:.2f}ms | half={qr['latency']['half']['p50']:.2f}ms")
            print(f"  p95: full={qr['latency']['full']['p95']:.2f}ms | mrl={qr['latency']['mrl']['p95']:.2f}ms | half={qr['latency']['half']['p95']:.2f}ms")
            print(f"  recall: mrl={qr['recall']['mrl']:.0%} | half={qr['recall']['half']:.0%}")
            print()

            all_results.append({
                "n": n,
                "idx_build_mrl": t_mrl,
                "idx_build_half": t_half,
                "idx_size_mrl": sz_mrl,
                "idx_size_half": sz_half,
                **qr,
            })

            cleanup(conn)

        # 시각화
        chart_path = os.path.join(SCRIPT_DIR, "benchmark_vector_v2_results.png")
        plot_results(all_results, chart_path)

        # JSON 저장
        json_path = os.path.join(SCRIPT_DIR, "benchmark_vector_v2_results.json")
        # numpy float → python float
        def to_serializable(obj):
            if isinstance(obj, (np.floating, np.integer)):
                return float(obj)
            if isinstance(obj, dict):
                return {k: to_serializable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [to_serializable(i) for i in obj]
            return obj

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(to_serializable(all_results), f, ensure_ascii=False, indent=2)
        print(f"→ JSON 저장: {json_path}")

        # 최종 요약 테이블
        print("\n" + "=" * 70)
        print(f"{'n':>6s} | {'fullscan p50':>13s} | {'MRL 768 p50':>12s} | {'halfvec p50':>12s} | {'MRL recall':>10s} | {'half recall':>11s}")
        print("-" * 70)
        for r in all_results:
            print(f"{r['n']:>6d} | {r['latency']['full']['p50']:>11.2f}ms | {r['latency']['mrl']['p50']:>10.2f}ms | {r['latency']['half']['p50']:>10.2f}ms | {r['recall']['mrl']:>9.0%} | {r['recall']['half']:>10.0%}")

    finally:
        cleanup(conn)
        conn.close()


if __name__ == "__main__":
    main()
