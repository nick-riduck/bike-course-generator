#!/usr/bin/env python3
"""
Step 2: Gemini 3.1 Pro + Google Search grounding으로 POI 보강. (멀티스레딩 지원 버전)
description, waypoint_type[], nearby_landmarks 추출.

안정성 개선:
- API 호출 timeout (60초)
- 실패 시 3회 재시도 (exponential backoff)
- 매 건마다 progress 저장 (JSONL append, 메인 스레드에서 안전하게 처리)
- 완료된 POI 자동 스킵 (resume)
- ThreadPoolExecutor를 사용한 동시 병렬 처리 지원

Usage:
    python enrich_with_gemini_mt.py                    # 전체 실행 (자동 resume)
    python enrich_with_gemini_mt.py --limit 10         # 10개만 테스트
    python enrich_with_gemini_mt.py --reset            # 처음부터 다시
    python enrich_with_gemini_mt.py --workers 5        # 동시 5개 스레드로 처리

Output: enriched_gemini.json (최종), enriched_gemini_progress.jsonl (중간 저장)
"""

import os
import sys
import json
import time
import re
import argparse
import signal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm
from google import genai
from google.genai import types

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
INPUT_FILE = SCRIPT_DIR / "unique_pois_with_address.json"
OUTPUT_FILE = SCRIPT_DIR / "enriched_gemini.json"
PROGRESS_FILE = SCRIPT_DIR / "enriched_gemini_progress.jsonl"  # JSONL: 한 줄씩 append

DEFAULT_MODEL = "gemini-3.1-pro-preview"
QPS_DELAY = 1.0
MAX_RETRIES = 3
REQUEST_TIMEOUT = 60  # seconds

VALID_TYPES = {
    "convenience_store", "cafe", "restaurant", "restroom", "water_fountain",
    "rest_area", "bike_shop", "parking", "transit", "bridge", "tunnel",
    "checkpoint", "viewpoint", "river", "lake", "mountain", "beach",
    "park", "nature", "historic", "landmark", "museum", "hospital",
    "police", "other",
}

PROMPT_TEMPLATE = """당신은 한국 자전거 라이딩 전문가입니다.
아래 POI(관심 지점)에 대해 구글 검색을 활용하여 정보를 수집하고,
자전거 라이더 관점에서 정리해주세요.

## POI 정보
- 이름: {name}
- 좌표: {lat}, {lng}
- 주소: {address}
- Komoot 카테고리: {category}
- 등장 코스 수: {tour_count}개
{tips_line}

## 출력 (JSON만 출력, markdown 코드블록 없이 순수 JSON만)
{{
  "description": "라이더 관점 1~2줄 설명 (한국어, 최대 100자)",
  "waypoint_type": ["타입1", "타입2", ...],
  "nearby_landmarks": ["주변 랜드마크1"],
  "confidence": "high|medium|low",
  "name_correction": "실제 명칭이 다르면 수정, 같으면 null"
}}

## waypoint_type ENUM (반드시 이 중에서만 선택, 해당하는 것 모두)
convenience_store, cafe, restaurant, restroom, water_fountain,
rest_area, bike_shop, parking, transit, bridge, tunnel, checkpoint,
viewpoint, river, lake, mountain, beach, park, nature,
historic, landmark, museum, hospital, police, other

## 주의사항
- confidence: 검색 결과로 확인 가능하면 high, 부분적이면 medium, 추측이면 low
- waypoint_type은 반드시 위 ENUM 값만 사용
- description은 간결하게 1~2줄로
- 주소는 별도로 처리하므로 출력하지 마세요
"""

# Graceful shutdown
_shutdown = False
def _signal_handler(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n⚠️  종료 요청 수신. 현재 작업 완료 후 안전하게 종료합니다...")

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def load_tips_map():
    crawl_dir = SCRIPT_DIR / ".." / "KOMOOT_FULL"
    tips_map = {}
    for d in sorted(os.listdir(crawl_dir)):
        meta_path = crawl_dir / d / "metadata.json"
        if not meta_path.exists():
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        for wp in meta.get("waypoints", []):
            name = wp.get("name", "").strip()
            if not name:
                continue
            for tip in wp.get("tips", []):
                text = tip.get("text", "").strip()
                if text and len(text) > 5:
                    tips_map.setdefault(name, []).append(text)
    return tips_map


def parse_json_response(text):
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"JSON not found in response: {text[:200]}")


def validate_result(result):
    raw_types = result.get("waypoint_type", [])
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    result["waypoint_type"] = [t for t in raw_types if t in VALID_TYPES] or ["other"]
    result.setdefault("description", "")
    result.setdefault("nearby_landmarks", [])
    result.setdefault("name_correction", None)
    result.setdefault("confidence", "low")
    if len(result["description"]) > 200:
        result["description"] = result["description"][:197] + "..."
    return result


def build_prompt(poi, tips_map):
    name = poi["name"]
    tips_texts = tips_map.get(name, [])
    tips_line = ""
    if tips_texts:
        best_tip = max(tips_texts, key=len)[:300]
        tips_line = f'- 사용자 팁: "{best_tip}"'

    category = poi["category"]
    if isinstance(category, list):
        category = ", ".join(category)

    address = poi.get("address") or "알 수 없음"

    return PROMPT_TEMPLATE.format(
        name=name, lat=poi["lat"], lng=poi["lng"],
        address=address, category=category,
        tour_count=poi["tour_count"], tips_line=tips_line,
    )


def enrich_single(client, model, tool, poi, tips_map):
    """Call Gemini with timeout + retry."""
    prompt = build_prompt(poi, tips_map)

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[tool],
                    temperature=0.3,
                    http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT * 1000),
                ),
            )

            result = parse_json_response(response.text)
            result = validate_result(result)

            # Grounding metadata
            search_queries = []
            sources = []
            if response.candidates and response.candidates[0].grounding_metadata:
                gm = response.candidates[0].grounding_metadata
                search_queries = gm.web_search_queries or []
                if gm.grounding_chunks:
                    sources = [
                        {"title": c.web.title, "uri": c.web.uri}
                        for c in gm.grounding_chunks[:5]
                        if c.web
                    ]

            result["_grounding"] = {
                "search_queries": search_queries,
                "sources": sources,
            }
            return result

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                time.sleep(wait)

    raise last_error


def load_completed_indices(progress_file: Path) -> dict[int, dict]:
    """JSONL progress 파일에서 완료된 항목 로드. {index: result}"""
    completed = {}
    if not progress_file.exists():
        return completed
    with open(progress_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                idx = item.get("_index")
                if idx is not None:
                    completed[idx] = item
            except json.JSONDecodeError:
                continue
    return completed


def append_progress(result: dict, progress_file: Path):
    """JSONL에 한 줄 append."""
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def main():
    print("작업시작", flush=True)
    parser = argparse.ArgumentParser(description="Enrich POIs with Gemini + Google Search")
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to process (0=all)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reset", action="store_true", help="처음부터 다시 (progress 삭제)")
    parser.add_argument("--workers", type=int, default=1, help="동시 처리 수 (default: 1)")
    args = parser.parse_args()

    api_key = "AIzaSyAZunIBnGhBa491-I9RWiaOCTq1eVQWh0I"
    if not api_key:
        print("ERROR: API key not set")
        sys.exit(1)

    # Load input
    with open(INPUT_FILE, encoding="utf-8") as f:
        pois = json.load(f)
    print(f"입력: {len(pois)}개 POI")

    # Load tips
    print("Tips 로딩 중...")
    tips_map = load_tips_map()
    tips_count = sum(1 for name in tips_map if any(p["name"] == name for p in pois))
    print(f"  매칭된 tips: {tips_count}개 POI")

    # Reset or resume
    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("⚠️  Progress 초기화")

    completed = load_completed_indices(PROGRESS_FILE)
    print(f"완료된 항목: {len(completed)}개")

    # Determine work
    todo_indices = [i for i in range(len(pois)) if i not in completed]
    if args.limit > 0:
        todo_indices = todo_indices[:args.limit]

    if not todo_indices:
        print("처리할 POI가 없습니다.")
        # Finalize
        if completed:
            _finalize(pois, completed)
        return

    print(f"처리 대상: {len(todo_indices)}개 (전체 {len(pois)}개 중)")
    print(f"모델: {args.model} / timeout: {REQUEST_TIMEOUT}s / retry: {MAX_RETRIES}회")
    print()

    # Init client
    client = genai.Client(api_key=api_key)
    tool = types.Tool(google_search=types.GoogleSearch())

    errors = 0
    pbar = tqdm(total=len(todo_indices), desc="POI 보강", unit="poi", initial=0)

    # Worker function for ThreadPoolExecutor
    def process_item(i):
        if _shutdown:
            return i, None, None
        poi = pois[i]
        try:
            result = enrich_single(client, args.model, tool, poi, tips_map)
            enriched = {**poi, **result, "_index": i}
            return i, enriched, None
        except Exception as e:
            enriched = {
                **poi,
                "description": "",
                "waypoint_type": ["other"],
                "nearby_landmarks": [],
                "confidence": "error",
                "name_correction": None,
                "_error": str(e),
                "_index": i,
            }
            return i, enriched, e

    workers = max(1, args.workers)
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # 모든 작업을 스레드 풀에 제출
        futures = {executor.submit(process_item, i): i for i in todo_indices}
        
        # 완료되는 순서대로 처리 (메인 스레드)
        for future in as_completed(futures):
            if _shutdown:
                continue

            i, enriched, error = future.result()
            
            if enriched is None:
                continue

            poi = pois[i]

            # 메인 스레드에서 파일 쓰기를 진행하므로 충돌 위험 없음 (안전)
            append_progress(enriched, PROGRESS_FILE)
            completed[i] = enriched

            if error:
                errors += 1
                pbar.set_postfix_str(f"{poi['name'][:15]} | ERROR")
            else:
                conf = enriched.get("confidence", "?")
                types_str = ", ".join(enriched.get("waypoint_type", []))
                pbar.set_postfix_str(f"{poi['name'][:15]} | {conf} | [{types_str}]")

            pbar.update(1)
            
            # 단일 워커일 때만 딜레이 적용 (멀티 스레드 시에는 딜레이 없이 병렬 처리)
            if workers == 1:
                time.sleep(QPS_DELAY)

    if _shutdown:
        print(f"\n안전 종료: {len(completed)}개 저장됨")

    pbar.close()

    # Finalize
    if not _shutdown:
        _finalize(pois, completed)

    # Summary
    print(f"\n=== {'중단' if _shutdown else '완료'} ===")
    print(f"저장: {len(completed)}/{len(pois)}개")
    print(f"에러: {errors}개")

    conf_counts = {}
    for r in completed.values():
        c = r.get("confidence", "unknown")
        conf_counts[c] = conf_counts.get(c, 0) + 1
    print(f"신뢰도 분포: {conf_counts}")

    type_counts = {}
    for r in completed.values():
        for t in r.get("waypoint_type", []):
            type_counts[t] = type_counts.get(t, 0) + 1
    if type_counts:
        print(f"타입 분포 (상위 10):")
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {t:20s} {c}")


def _finalize(pois, completed):
    """완료된 결과를 원본 순서대로 최종 JSON 생성."""
    results = []
    for i in range(len(pois)):
        if i in completed:
            item = {k: v for k, v in completed[i].items() if k != "_index"}
            results.append(item)
        else:
            # 미처리 항목은 원본 그대로
            results.append({
                **pois[i],
                "description": "",
                "waypoint_type": ["other"],
                "nearby_landmarks": [],
                "confidence": "pending",
                "name_correction": None,
            })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n→ 최종 파일: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
