#!/usr/bin/env python3
"""
Google Geocoding API로 좌표 → 주소 역지오코딩.

Usage:
    GOOGLE_MAPS_API_KEY=xxx python reverse_geocode.py

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

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
QPS_DELAY = 0.1  # 10 QPS
SAVE_EVERY = 100


def reverse_geocode(lat, lng, api_key):
    """좌표 → 주소 (Google Geocoding API)."""
    params = {
        "latlng": f"{lat},{lng}",
        "language": "ko",
        "key": api_key,
    }
    resp = requests.get(GEOCODE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        return {"address": "", "address_detail": {}}

    # 첫 번째 결과 = 가장 구체적인 주소
    result = data["results"][0]
    formatted = result.get("formatted_address", "")

    # 컴포넌트에서 구조화된 정보 추출
    components = {}
    for comp in result.get("address_components", []):
        for t in comp["types"]:
            components[t] = comp["long_name"]

    return {
        "address": formatted,
        "address_detail": {
            "sido": components.get("administrative_area_level_1", ""),
            "sigungu": components.get("sublocality_level_1", "")
                       or components.get("locality", ""),
            "dong": components.get("sublocality_level_2", ""),
        },
    }


def main():
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_MAPS_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        pois = json.load(f)
    print(f"입력: {len(pois)}개 POI")

    # Resume support
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

            display = addr["address"] or "(없음)"
            print(f"  [{i+1}/{len(pois)}] {poi['name'][:25]:25s} → {display}")

        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{len(pois)}] {poi['name'][:25]:25s} → ERROR: {e}")
            results.append({**poi, "address": "", "address_detail": {}})

        if len(results) % SAVE_EVERY == 0:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  --- 중간 저장: {len(results)}개 ---")

        time.sleep(QPS_DELAY)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    has_addr = sum(1 for r in results if r.get("address"))
    print(f"\n=== 완료 ===")
    print(f"총: {len(results)}개, 에러: {errors}개")
    print(f"주소 있음: {has_addr}개 ({has_addr/len(results)*100:.1f}%)")
    print(f"→ {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
