#!/usr/bin/env python3
"""
Gemini 모델 벤치마크: 자동 태그/설명 생성 속도 + 품질 비교.

Google AI Studio (API 키 방식) 전용으로 테스트합니다.
"""

import os
import sys
import json
import time
import statistics
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai
from google.genai import types

from app.services.auto_tag_service import (
    _build_route_line_wkt,
    _get_waypoints_along_route,
    _extract_control_points,
    _get_waypoints_near_control_points,
    _extract_route_context,
    _build_prompt,
    get_existing_tags,
)

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

STORAGE_DIR = os.path.join(os.path.dirname(__file__), '..', 'backend', 'storage')


def prepare_prompt(conn, route_id: int) -> tuple[str, dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, data_file_path, distance, elevation_gain
        FROM routes WHERE id = %s
    """, (route_id,))
    route = cur.fetchone()
    if not route:
        print(f"Route {route_id} not found")
        sys.exit(1)

    json_path = os.path.join(STORAGE_DIR, route['data_file_path'])
    with open(json_path, 'r') as f:
        full_data = json.load(f)

    route_wkt = _build_route_line_wkt(full_data)
    route_pois = _get_waypoints_along_route(conn, route_wkt, radius_m=500) if route_wkt else []
    cp = _extract_control_points(full_data)
    cp_pois = _get_waypoints_near_control_points(conn, cp, radius_m=200) if cp else []

    seen_ids = set()
    merged = []
    for wp in cp_pois:
        seen_ids.add(wp["id"])
        merged.append(wp)
    for wp in route_pois:
        if wp["id"] not in seen_ids:
            merged.append(wp)

    existing_tags = get_existing_tags(conn)
    context = _extract_route_context(full_data, merged)
    prompt = _build_prompt(context, existing_tags)

    cur.close()
    return prompt, {
        "title": route["title"],
        "distance_km": round(route["distance"] / 1000, 1),
        "elevation_gain": route["elevation_gain"],
        "poi_count": len(merged),
    }


def benchmark_model(client, model_name: str, prompt: str, runs: int) -> dict:
    latencies = []
    results = []
    json_ok = 0
    errors = []

    for i in range(runs):
        t0 = time.time()
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )
            elapsed = time.time() - t0
            latencies.append(elapsed)

            parsed = json.loads(response.text)
            tags = parsed.get("tags", [])
            desc = parsed.get("description", "")
            json_ok += 1
            results.append({"tags": tags, "description": desc, "latency": round(elapsed, 3)})
            print(f"    run {i+1}: {elapsed:.2f}s, {len(tags)} tags")
        except Exception as e:
            elapsed = time.time() - t0
            latencies.append(elapsed)
            errors.append(f"run {i+1}: {type(e).__name__}: {e}")
            results.append({"tags": [], "description": "", "latency": round(elapsed, 3), "error": str(e)})
            print(f"    run {i+1}: {elapsed:.2f}s, ERROR: {e}")

        if i < runs - 1:
            time.sleep(0.5)

    if not latencies:
        return {"mean": 0, "median": 0, "p95": 0, "min": 0, "max": 0}

    lat_sorted = sorted(latencies)
    p50_idx = len(lat_sorted) // 2
    p95_idx = min(int(len(lat_sorted) * 0.95), len(lat_sorted) - 1)

    return {
        "model": model_name,
        "runs": runs,
        "json_success": json_ok,
        "json_fail": runs - json_ok,
        "latency": {
            "mean": round(statistics.mean(latencies), 3),
            "median": round(lat_sorted[p50_idx], 3),
            "p95": round(lat_sorted[p95_idx], 3),
            "min": round(min(latencies), 3),
            "max": round(max(latencies), 3),
        },
        "results": results,
        "errors": errors,
    }


def print_summary(all_results: list[dict], route_info: dict):
    print(f"\n{'='*80}")
    print(f"  Gemini Auto-Tag Benchmark Results")
    print(f"  Route: {route_info['title']} ({route_info['distance_km']}km, +{route_info['elevation_gain']}m)")
    print(f"  POIs: {route_info['poi_count']}개")
    print(f"{'='*80}\n")

    header = f"{'Model':<30} {'Mean':>6} {'P50':>6} {'P95':>6} {'Min':>6} {'Max':>6} {'JSON':>5}"
    print(header)
    print("-" * len(header))

    for r in all_results:
        lat = r["latency"]
        json_rate = f"{r['json_success']}/{r['runs']}"
        print(
            f"{r['model']:<30} "
            f"{lat['mean']:>5.2f}s "
            f"{lat['median']:>5.2f}s "
            f"{lat['p95']:>5.2f}s "
            f"{lat['min']:>5.2f}s "
            f"{lat['max']:>5.2f}s "
            f"{json_rate:>5}"
        )

    print(f"\n{'='*80}")
    print("  Sample Outputs (first successful run)")
    print(f"{'='*80}\n")

    for r in all_results:
        print(f"[{r['model']}]")
        first_ok = next((res for res in r["results"] if "error" not in res), None)
        if first_ok:
            print(f"  Tags ({len(first_ok['tags'])}): {first_ok['tags']}")
            desc = first_ok['description']
            # print full description to see the structure
            print(f"  Desc:\n{desc}\n")
        else:
            print(f"  (all runs failed)")
        if r["errors"]:
            for err in r["errors"][:3]:
                print(f"  Error: {err}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Benchmark Gemini models for auto-tagging")
    parser.add_argument("--route", type=int, default=283, help="Route ID to test")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per model")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

    print(f"Preparing prompt for route {args.route}...")
    prompt, route_info = prepare_prompt(conn, args.route)
    print(f"  Prompt length: {len(prompt)} chars")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    all_results = []
    for model_name in MODELS:
        print(f"\n--- Benchmarking {model_name} ({args.runs} runs) ---")
        result = benchmark_model(client, model_name, prompt, args.runs)
        all_results.append(result)

    print_summary(all_results, route_info)

    out_path = os.path.join(os.path.dirname(__file__), "output", "benchmark_gemini_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "route": route_info,
            "prompt_length": len(prompt),
            "runs_per_model": args.runs,
            "models": all_results,
        }, f, ensure_ascii=False, indent=2)

    conn.close()


if __name__ == "__main__":
    main()
