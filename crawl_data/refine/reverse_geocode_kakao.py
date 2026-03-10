#!/usr/bin/env python3
"""
Kakao Reverse Geocoding: 좌표 → 주소 변환.
unique_pois.json의 모든 POI에 대해 도로명주소/지번주소를 확보.

Usage:
    KAKAO_REST_API_KEY=xxx python reverse_geocode_kakao.py

Output: unique_pois_with_address.json
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
INPUT_FILE = SCRIPT_DIR / "unique_pois.json"
OUTPUT_FILE = SCRIPT_DIR / "unique_pois_with_address.json"

KAKAO_API_URL = "https://dapi.kakao.com/v2/local/geo/coord2address.json"
QPS_DELAY = 0.05  # 20 QPS (쿼터 여유)
SAVE_EVERY = 100


def reverse_geocode(lat, lng, api_key):
    """좌표 → 주소 (Kakao)."""
    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"x": lng, "y": lat}
    resp = requests.get(KAKAO_API_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    docs = data.get("documents", [])
    if not docs:
        return {"road_address": "", "address": ""}

    doc = docs[0]
    road = doc.get("road_address")
    addr = doc.get("address", {})

    return {
        "road_address": road.get("address_name", "") if road else "",
        "address": addr.get("address_name", "") if addr else "",
    }


def main():
    api_key = os.environ.get("KAKAO_REST_API_KEY")
    if not api_key:
        print("ERROR: KAKAO_REST_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        pois = json.load(f)
    print(f"입력: {len(pois)}개 POI")

    # Resume support: 이미 처리된 결과가 있으면 로드
    results = []
    start_idx = 0
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            results = json.load(f)
        if len(results) < len(pois):
            start_idx = len(results)
            print(f"이전 진행 복원: {start_idx}개 완료")
        else:
            print(f"이미 완료됨: {len(results)}개")
            return

    errors = 0
    for i in range(start_idx, len(pois)):
        poi = pois[i]
        try:
            addr = reverse_geocode(poi["lat"], poi["lng"], api_key)
            poi_with_addr = {**poi, **addr}
            results.append(poi_with_addr)

            display_addr = addr["road_address"] or addr["address"] or "(없음)"
            print(f"  [{i+1}/{len(pois)}] {poi['name'][:25]:25s} → {display_addr}")

        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{len(pois)}] {poi['name'][:25]:25s} → ERROR: {e}")
            results.append({**poi, "road_address": "", "address": ""})

        if len(results) % SAVE_EVERY == 0:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  --- 중간 저장: {len(results)}개 ---")

        time.sleep(QPS_DELAY)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    has_road = sum(1 for r in results if r.get("road_address"))
    has_addr = sum(1 for r in results if r.get("address"))
    print(f"\n=== 완료 ===")
    print(f"총: {len(results)}개, 에러: {errors}개")
    print(f"도로명주소: {has_road}개, 지번주소: {has_addr}개")
    print(f"→ {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
