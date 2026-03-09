#!/usr/bin/env python3
"""
enriched_gemini.json에서 confidence='error'인 항목을 재처리.

주소+좌표 중심 프롬프트로 Gemini에게 triage + enrichment 요청:
  - keep: 자전거 POI로 유효 → description, waypoint_type 생성
  - rename: 이름 부적절하지만 장소 유효 → 새 이름 + enrichment
  - discard: 아파트, 의미없는 장소 → DB 제외

Usage:
    python recover_error_pois.py                      # 전체 실행 (자동 resume)
    python recover_error_pois.py --limit 10           # 10개만 테스트
    python recover_error_pois.py --workers 5          # 병렬 5개
    python recover_error_pois.py --reset              # 처음부터 다시
    python recover_error_pois.py --apply              # 결과를 enriched_gemini.json에 반영

Output: recovered_errors.json, recovered_errors_progress.jsonl
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
INPUT_FILE = SCRIPT_DIR / "enriched_gemini.json"
OUTPUT_FILE = SCRIPT_DIR / "recovered_errors.json"
PROGRESS_FILE = SCRIPT_DIR / "recovered_errors_progress.jsonl"

DEFAULT_MODEL = "gemini-3.1-pro-preview"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 120  # 2분

VALID_TYPES = {
    "convenience_store", "cafe", "restaurant", "restroom", "water_fountain",
    "rest_area", "bike_shop", "parking", "transit", "bridge", "tunnel",
    "checkpoint", "viewpoint", "river", "lake", "mountain", "beach",
    "park", "nature", "historic", "landmark", "museum", "hospital",
    "police", "other",
}

PROMPT_TEMPLATE = """당신은 한국 자전거 라이딩 전문가이자 지도 데이터 에디터입니다.
아래는 자전거 경로 앱에서 수집된 POI인데, 이름이 모호하여 자동 분류에 실패한 항목입니다.
주소와 좌표를 기반으로 이 장소를 판단해주세요.

## POI 정보
- 현재 이름: {name}
- 좌표: {lat}, {lng}
- 주소: {address}
- 원본 카테고리: {category}
- 등장 코스 수: {tour_count}개
- 이미지 있음: {has_images}

## 판단 기준
1. 자전거 라이더에게 유용한 장소인가? (보급, 휴식, 경관, 인프라, 랜드마크 등)
2. 아파트, 빌라, 일반 주택, 의미없는 이름(P, ㅇㅇ 등)은 discard
3. 지하철역, 버스터미널 등 교통시설은 transit으로 keep
4. 저수지, 하천, 해변 등 자연지형은 keep
5. 이름이 지역명만 있으면(양평, 안동) rename하여 구체화

## 출력 (JSON만, markdown 없이)
{{
  "action": "keep|rename|discard",
  "corrected_name": "수정된 이름 (action=keep이면 기존 이름, discard면 null)",
  "description": "라이더 관점 1~2줄 설명 (discard면 빈 문자열)",
  "waypoint_type": ["타입1", "타입2"],
  "nearby_landmarks": ["주변 랜드마크"],
  "confidence": "high|medium|low",
  "discard_reason": "discard인 경우 이유 (아니면 null)"
}}

## waypoint_type ENUM (반드시 이 중에서만 선택)
convenience_store, cafe, restaurant, restroom, water_fountain,
rest_area, bike_shop, parking, transit, bridge, tunnel, checkpoint,
viewpoint, river, lake, mountain, beach, park, nature,
historic, landmark, museum, hospital, police, other
"""

# Graceful shutdown
_shutdown = False
def _signal_handler(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n⚠️  종료 요청 수신. 현재 작업 완료 후 안전하게 종료합니다...")

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def parse_json_response(text):
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    # 여러 JSON 블록이 있을 수 있으므로 가장 큰 것을 시도
    matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for m in sorted(matches, key=len, reverse=True):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    # fallback: 전체에서 시도
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"JSON not found in response: {text[:200]}")


def validate_result(result):
    raw_types = result.get("waypoint_type", [])
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    result["waypoint_type"] = [t for t in raw_types if t in VALID_TYPES] or ["other"]
    result.setdefault("description", "")
    result.setdefault("nearby_landmarks", [])
    result.setdefault("confidence", "low")
    result.setdefault("action", "keep")
    result.setdefault("corrected_name", None)
    result.setdefault("discard_reason", None)
    if result["description"] and len(result["description"]) > 200:
        result["description"] = result["description"][:197] + "..."
    return result


def build_prompt(poi):
    category = poi.get("category", "")
    if isinstance(category, list):
        category = ", ".join(category)

    return PROMPT_TEMPLATE.format(
        name=poi.get("name", ""),
        lat=poi.get("lat", ""),
        lng=poi.get("lng", ""),
        address=poi.get("address", "알 수 없음"),
        category=category,
        tour_count=poi.get("tour_count", poi.get("count", 1)),
        has_images=poi.get("has_images", False),
    )


def recover_single(client, model, tool, poi):
    prompt = build_prompt(poi)
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[tool],
                    temperature=0.2,
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
                wait = (2 ** attempt) * 2
                time.sleep(wait)

    raise last_error


def load_completed(progress_file: Path) -> dict[int, dict]:
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
                idx = item.get("_error_index")
                if idx is not None:
                    completed[idx] = item
            except json.JSONDecodeError:
                continue
    return completed


def append_progress(result: dict, progress_file: Path):
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def process_item(client, model, tool, orig_idx, poi):
    """단일 POI 처리 (스레드에서 실행)."""
    if _shutdown:
        return orig_idx, None, None
    try:
        result = recover_single(client, model, tool, poi)
        enriched = {
            **poi,
            **result,
            "_error_index": orig_idx,
        }
        return orig_idx, enriched, None
    except Exception as e:
        enriched = {
            **poi,
            "action": "error",
            "description": "",
            "waypoint_type": [],
            "confidence": "error",
            "_recover_error": str(e),
            "_error_index": orig_idx,
        }
        return orig_idx, enriched, e


def main():
    parser = argparse.ArgumentParser(description="Recover error POIs with address-based prompting")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=3, help="동시 처리 수 (default: 3)")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--apply", action="store_true", help="결과를 enriched_gemini.json에 반영")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY 환경변수를 설정하세요")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        all_pois = json.load(f)

    # 에러 항목만 추출 (원본 인덱스 보존)
    error_items = [(i, poi) for i, poi in enumerate(all_pois) if poi.get("confidence") == "error"]
    print(f"전체: {len(all_pois)}개 / 에러: {len(error_items)}개")

    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("⚠️  Progress 초기화")

    completed = load_completed(PROGRESS_FILE)
    print(f"완료된 항목: {len(completed)}개")

    todo = [(i, poi) for i, poi in error_items if i not in completed]
    if args.limit > 0:
        todo = todo[:args.limit]

    if not todo and not args.apply:
        print("처리할 항목 없음")
        if completed:
            _save_results(error_items, completed)
        return

    if todo:
        print(f"처리 대상: {len(todo)}개")
        print(f"모델: {args.model} / workers: {args.workers} / timeout: {REQUEST_TIMEOUT}s")
        print()

        client = genai.Client(api_key=api_key)
        tool = types.Tool(google_search=types.GoogleSearch())

        errors = 0
        workers = max(1, args.workers)
        pbar = tqdm(total=len(todo), desc="에러 복구", unit="poi")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(process_item, client, args.model, tool, orig_idx, poi): (orig_idx, poi)
                for orig_idx, poi in todo
            }

            for future in as_completed(futures):
                if _shutdown:
                    continue

                orig_idx, enriched, error = future.result()
                if enriched is None:
                    continue

                append_progress(enriched, PROGRESS_FILE)
                completed[orig_idx] = enriched

                poi_name = enriched.get("name", "?")[:12]
                action = enriched.get("action", "?")

                if error:
                    errors += 1
                    pbar.set_postfix_str(f"{poi_name} | ERROR")
                elif action == "discard":
                    pbar.set_postfix_str(f"{poi_name} → DISCARD")
                elif action == "rename":
                    new_name = (enriched.get("corrected_name") or "?")[:12]
                    pbar.set_postfix_str(f"{poi_name} → {new_name}")
                else:
                    pbar.set_postfix_str(f"{poi_name} → KEEP")

                pbar.update(1)

        pbar.close()

        if _shutdown:
            print(f"\n안전 종료: {len(completed)}개 저장됨")

        _save_results(error_items, completed)

        # Summary
        actions = {}
        for r in completed.values():
            a = r.get("action", "unknown")
            actions[a] = actions.get(a, 0) + 1
        print(f"\n=== 결과 ===")
        print(f"처리: {len(completed)}/{len(error_items)}개")
        print(f"에러: {errors}개")
        print(f"Action 분포: {actions}")

    # --apply: enriched_gemini.json에 반영
    if args.apply and completed:
        _apply_to_enriched(all_pois, completed)


def _save_results(error_items, completed):
    results = []
    for orig_idx, poi in error_items:
        if orig_idx in completed:
            item = {k: v for k, v in completed[orig_idx].items()
                    if not k.startswith("_")}
            results.append(item)
        else:
            results.append(poi)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"→ 결과: {OUTPUT_FILE}")


def _apply_to_enriched(all_pois, completed):
    """recovered 결과를 enriched_gemini.json에 병합."""
    updated = 0
    discarded = 0

    for orig_idx, result in completed.items():
        action = result.get("action", "keep")

        if action == "discard":
            all_pois[orig_idx]["confidence"] = "discard"
            all_pois[orig_idx]["discard_reason"] = result.get("discard_reason", "")
            discarded += 1
        elif action in ("keep", "rename"):
            poi = all_pois[orig_idx]
            poi["description"] = result.get("description", "")
            poi["waypoint_type"] = result.get("waypoint_type", [])
            poi["nearby_landmarks"] = result.get("nearby_landmarks", [])
            poi["confidence"] = result.get("confidence", "low")
            if action == "rename" and result.get("corrected_name"):
                poi["name_correction"] = result["corrected_name"]
            if result.get("_grounding"):
                poi["_grounding"] = result["_grounding"]
            updated += 1

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_pois, f, ensure_ascii=False, indent=2)

    print(f"\n✅ enriched_gemini.json 반영 완료")
    print(f"  업데이트: {updated}개 / discard: {discarded}개")


if __name__ == "__main__":
    main()
