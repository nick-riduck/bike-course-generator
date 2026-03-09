#!/usr/bin/env python3
"""
Step 3: Gemini 모델을 활용한 이상한 POI 이름 교정 (멀티스레딩 지원)
이전 단계에서 수집된 description, waypoint_type, nearby_landmarks 등을 종합하여
어색하거나 기계적인 POI 이름을 직관적이고 간결하게 수정합니다.

Usage:
    python fix_poi_names_mt.py                    # 전체 실행 (자동 resume)
    python fix_poi_names_mt.py --limit 10         # 10개만 테스트
    python fix_poi_names_mt.py --workers 5        # 동시 5개 스레드로 처리
    python fix_poi_names_mt.py --only-suspicious  # 이름이 이상해 보이는 것만 필터링하여 실행

Output: final_pois_with_fixed_names.json (최종), fixed_names_progress.jsonl (중간 저장)
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
OUTPUT_FILE = SCRIPT_DIR / "final_pois_with_fixed_names.json"
PROGRESS_FILE = SCRIPT_DIR / "fixed_names_progress.jsonl"

# 이름 교정 작업은 텍스트 추론 위주이므로 빠르고 저렴한 2.5-flash나 3.1-flash-lite가 효율적일 수 있습니다.
# (물론 3.1-pro-preview로 변경하셔도 됩니다.)
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview" 
QPS_DELAY = 1.0
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30  # seconds

PROMPT_TEMPLATE = """당신은 한국 자전거 라이딩 전문가이자 지도 데이터 에디터입니다.
아래는 자전거 경로 안내 앱에서 수집 및 1차 보강된 POI(관심 지점) 데이터입니다.

초기 수집된 이름이 기계적이거나(예: "waypoint 1", "알 수 없는 길"),
오타가 있거나, 불필요하게 긴 수식어가 붙은 경우가 있습니다.
제공된 주소, 설명, 타입, 랜드마크 정보를 종합하여
자전거 라이더가 지도에서 보았을 때 직관적으로 식별할 수 있는 **정확하고 깔끔한 고유 명칭**으로 교정해주세요.

(만약 현재 이름이 이미 적절하고 식별하기 좋다면 굳이 바꾸지 말고 그대로 유지하세요.)

## POI 정보
- 현재 이름: {name}
- 주소: {address}
- POI 타입: {types}
- 보강된 설명: {description}
- 주변 랜드마크: {landmarks}

## 출력 (JSON만 출력, markdown 코드블록 없이 순수 JSON만)
{{
  "corrected_name": "수정된 직관적인 이름 (변경 불필요 시 기존 이름)",
  "reason": "수정(또는 유지)한 이유 짧게 1줄"
}}
"""

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
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"JSON not found in response: {text[:200]}")

def build_prompt(poi):
    name = poi.get("name", "")
    address = poi.get("address") or "알 수 없음"
    types = ", ".join(poi.get("waypoint_type", []))
    description = poi.get("description", "")
    landmarks = ", ".join(poi.get("nearby_landmarks", []))

    return PROMPT_TEMPLATE.format(
        name=name, address=address, types=types,
        description=description, landmarks=landmarks
    )

def fix_name_single(client, model, poi):
    prompt = build_prompt(poi)
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2, # 보수적이고 일관된 추론
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT * 1000),
                ),
            )
            result = parse_json_response(response.text)
            
            # 기본값 설정
            result.setdefault("corrected_name", poi["name"])
            result.setdefault("reason", "")
            return result

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = (2 ** attempt) * 2
                time.sleep(wait)

    raise last_error

def load_completed_indices(progress_file: Path) -> dict[int, dict]:
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
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")

def is_suspicious_name(name: str) -> bool:
    """이름이 이상한지 휴리스틱으로 검사"""
    name_lower = name.lower()
    suspicious_keywords = ["waypoint", "알 수 없는", "도로", "street", "road", "구간", "지점", "unnamed"]
    
    if len(name) <= 1 or len(name) > 20: # 너무 짧거나 긴 경우
        return True
    if any(keyword in name_lower for keyword in suspicious_keywords):
        return True
    if re.search(r'\d{3,}', name): # 숫자가 3연속 이상 포함된 경우 (예: 국도 번호가 아닌 임의의 좌표값 등)
        return True
        
    return False

def main():
    print("작업시작: 이름 교정", flush=True)
    parser = argparse.ArgumentParser(description="Fix weird POI names using Gemini")
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to process (0=all)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reset", action="store_true", help="처음부터 다시 (progress 삭제)")
    parser.add_argument("--workers", type=int, default=1, help="동시 처리 수 (default: 1)")
    parser.add_argument("--only-suspicious", action="store_true", help="이상한 이름으로 의심되는 항목만 처리")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    if not INPUT_FILE.exists():
        print(f"ERROR: 입력 파일이 없습니다. 먼저 enrich_with_gemini_mt.py를 완료하세요: {INPUT_FILE}")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        pois = json.load(f)
    print(f"입력: {len(pois)}개 POI")

    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("⚠️  Progress 초기화")

    completed = load_completed_indices(PROGRESS_FILE)
    print(f"완료된 항목: {len(completed)}개")

    # Determine work
    todo_indices = []
    for i, poi in enumerate(pois):
        if i in completed:
            continue
        
        # only-suspicious 옵션이 켜져있으면, 기존 단계에서 name_correction을 제안했거나 휴리스틱에 걸리는 경우만 처리
        if args.only_suspicious:
            has_gemini_correction = bool(poi.get("name_correction"))
            if not has_gemini_correction and not is_suspicious_name(poi.get("name", "")):
                # 문제 없다고 판단되면 원본 그대로 저장
                item = {**poi, "final_name": poi.get("name"), "_index": i}
                completed[i] = item
                append_progress(item, PROGRESS_FILE)
                continue
                
        todo_indices.append(i)

    if args.limit > 0:
        todo_indices = todo_indices[:args.limit]

    if not todo_indices:
        print("처리할 POI가 없습니다.")
        if completed:
            _finalize(pois, completed)
        return

    print(f"처리 대상: {len(todo_indices)}개 (전체 {len(pois)}개 중)")
    print(f"모델: {args.model} / workers: {args.workers}")
    print()

    client = genai.Client(api_key=api_key)
    errors = 0
    pbar = tqdm(total=len(todo_indices), desc="이름 교정", unit="poi", initial=0)

    def process_item(i):
        if _shutdown:
            return i, None, None
        poi = pois[i]
        try:
            result = fix_name_single(client, args.model, poi)
            
            # 최종 이름 결정 (수정본이 있으면 수정본, 아니면 원본)
            final_name = result.get("corrected_name") or poi["name"]
            
            enriched = {
                **poi,
                "final_name": final_name,
                "name_change_reason": result.get("reason", ""),
                "_index": i
            }
            return i, enriched, None
        except Exception as e:
            enriched = {
                **poi,
                "final_name": poi["name"], # 에러 발생 시 원본 이름 유지
                "name_change_reason": f"Error: {e}",
                "_error": str(e),
                "_index": i,
            }
            return i, enriched, e

    workers = max(1, args.workers)
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_item, i): i for i in todo_indices}
        
        for future in as_completed(futures):
            if _shutdown:
                continue

            i, enriched, error = future.result()
            if enriched is None:
                continue

            append_progress(enriched, PROGRESS_FILE)
            completed[i] = enriched

            orig_name = pois[i]['name']
            new_name = enriched['final_name']
            
            if error:
                errors += 1
                pbar.set_postfix_str(f"{orig_name[:10]} | ERROR")
            else:
                status = "🔄 변경" if orig_name != new_name else "✅ 유지"
                pbar.set_postfix_str(f"{orig_name[:8]} -> {new_name[:8]} | {status}")

            pbar.update(1)
            
            if workers == 1:
                time.sleep(QPS_DELAY)

    if _shutdown:
        print(f"\n안전 종료: {len(completed)}개 저장됨")

    pbar.close()

    if not _shutdown:
        _finalize(pois, completed)

    print(f"\n=== {'중단' if _shutdown else '완료'} ===")
    print(f"저장: {len(completed)}/{len(pois)}개")
    print(f"에러: {errors}개")
    
    # 변경 통계
    changed = sum(1 for r in completed.values() if r.get("final_name") and r["final_name"] != r.get("name"))
    print(f"이름이 변경된 항목: {changed}개")


def _finalize(pois, completed):
    results = []
    for i in range(len(pois)):
        if i in completed:
            item = {k: v for k, v in completed[i].items() if k not in ["_index", "_error"]}
            
            # 이전 단계의 name_correction 필드는 중복되므로 정리
            if "name_correction" in item:
                del item["name_correction"]
                
            results.append(item)
        else:
            # 안전망: 처리되지 않은 항목은 원본 이름 그대로
            item = {**pois[i], "final_name": pois[i]["name"]}
            results.append(item)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n→ 최종 파일: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
