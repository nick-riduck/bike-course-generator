#!/usr/bin/env python3
"""
Step 1: 유사 웨이포인트 병합 판단
- 500m 이내 + 이름 유사도 0.5+ 쌍 추출
- Gemini 3.1 Pro에게 같은 장소인지 판단 + 대표 이름 선정 요청
- 결과를 JSON으로 저장 → 사람이 리뷰 후 적용
"""

import os
import sys
import json
import time
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2
from difflib import SequenceMatcher

import google.generativeai as genai

# --- Config ---
CRAWL_DIR = os.path.join(os.path.dirname(__file__), "..", "KOMOOT_FULL")
OUTPUT_DIR = os.path.dirname(__file__)
CANDIDATES_FILE = os.path.join(OUTPUT_DIR, "merge_candidates.json")
RESULT_FILE = os.path.join(OUTPUT_DIR, "merge_result.json")

DISTANCE_THRESHOLD_M = 500
SIMILARITY_THRESHOLD = 0.5
EXACT_NAME_CLUSTER_RADIUS_M = 100


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def name_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def load_all_waypoints():
    """Load all named waypoints from crawl data."""
    all_wps = []
    for d in sorted(os.listdir(CRAWL_DIR)):
        meta_path = os.path.join(CRAWL_DIR, d, "metadata.json")
        if not os.path.exists(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        for wp in meta.get("waypoints", []):
            name = wp.get("name", "").strip()
            if not name:
                continue
            loc = wp.get("location", {})
            lat, lng = loc.get("lat"), loc.get("lng")
            if not lat or not lng:
                continue
            all_wps.append({
                "name": name,
                "category": str(wp.get("category", "")),
                "lat": lat,
                "lng": lng,
                "has_images": bool(wp.get("images", [])),
                "has_tips": bool(wp.get("tips", [])),
                "tour_id": d,
            })
    return all_wps


def cluster_exact_names(all_wps):
    """Phase 1: Cluster by exact name + 100m radius → unique POIs."""
    name_groups = defaultdict(list)
    for wp in all_wps:
        name_groups[wp["name"]].append(wp)

    pois = []
    for name, wps in name_groups.items():
        used = [False] * len(wps)
        for i, wp in enumerate(wps):
            if used[i]:
                continue
            cluster = [wp]
            used[i] = True
            for j in range(i + 1, len(wps)):
                if used[j]:
                    continue
                if haversine(wp["lat"], wp["lng"], wps[j]["lat"], wps[j]["lng"]) < EXACT_NAME_CLUSTER_RADIUS_M:
                    cluster.append(wps[j])
                    used[j] = True

            tour_ids = list(set(w["tour_id"] for w in cluster))
            pois.append({
                "name": name,
                "category": cluster[0]["category"],
                "lat": sum(w["lat"] for w in cluster) / len(cluster),
                "lng": sum(w["lng"] for w in cluster) / len(cluster),
                "count": len(cluster),
                "tour_count": len(tour_ids),
                "has_images": any(w["has_images"] for w in cluster),
                "has_tips": any(w["has_tips"] for w in cluster),
            })
    return pois


def find_merge_candidates(pois):
    """Phase 2: Find POI pairs within 500m with similar (but not exact) names."""
    candidates = []
    for i in range(len(pois)):
        for j in range(i + 1, len(pois)):
            if pois[i]["name"] == pois[j]["name"]:
                continue  # exact duplicates already handled
            dist = haversine(pois[i]["lat"], pois[i]["lng"], pois[j]["lat"], pois[j]["lng"])
            if dist < DISTANCE_THRESHOLD_M:
                sim = name_similarity(pois[i]["name"], pois[j]["name"])
                if sim >= SIMILARITY_THRESHOLD:
                    candidates.append({
                        "idx": len(candidates),
                        "name1": pois[i]["name"],
                        "name2": pois[j]["name"],
                        "cat1": pois[i]["category"],
                        "cat2": pois[j]["category"],
                        "lat1": pois[i]["lat"],
                        "lng1": pois[i]["lng"],
                        "lat2": pois[j]["lat"],
                        "lng2": pois[j]["lng"],
                        "distance_m": round(dist, 1),
                        "name_similarity": round(sim, 3),
                    })

    candidates.sort(key=lambda x: -x["name_similarity"])
    return candidates


def _parse_json_response(text):
    """Extract JSON object from Gemini response text."""
    import re
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    raise ValueError(f"JSON not found in response: {text[:200]}")


def ask_gemini(candidates):
    """Ask Gemini to judge each pair individually: SAME or DIFF + merged name."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        api_key = input("Enter your Gemini API Key: ").strip()
    if not api_key:
        print("API Key is required.")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-3.1-pro-preview",
        generation_config={
            "temperature": 0.1,
            "max_output_tokens": 1024,
        },
    )

    results = []
    for i, pair in enumerate(candidates):
        prompt = f"""당신은 한국 지리 전문가입니다.
아래 두 웨이포인트가 **같은 물리적 장소**인지 판단하세요.

name1: "{pair['name1']}"
name2: "{pair['name2']}"
카테고리1: {pair['cat1']}
카테고리2: {pair['cat2']}
거리: {pair['distance_m']}m

## 판단 기준
- 같은 시설/지형의 다른 명칭 → SAME (예: "광나루 드론 공원" ↔ "한강 드론 공원")
- 띄어쓰기/약칭 차이 → SAME (예: "무창포해수욕장" ↔ "무창포 해수욕장")
- 역명과 해당 지역명 → SAME (예: "단양역" ↔ "단양")
- 인증센터/스탬프 부스 등 같은 시설의 다른 명칭 → SAME
- 물리적으로 다른 시설/지형 → DIFF (예: "한강철교" ↔ "북한강 철교")
- 같은 지역의 다른 기관 → DIFF (예: "거제소방서" ↔ "거제경찰서")
- 하천/호수/숲 등 다른 자연지형 → DIFF (예: "생태호수" ↔ "생태림")

## SAME인 경우 대표 이름
- 두 이름 중 더 구체적이고 정확한 이름 선택
- 필요시 두 이름을 조합

JSON만 출력:
{{"verdict": "SAME" 또는 "DIFF", "merged_name": "대표이름 또는 null", "reason": "한줄 사유"}}"""

        try:
            response = model.generate_content(prompt)
            result = _parse_json_response(response.text)
            result["idx"] = pair["idx"]
            results.append(result)
            verdict = result.get("verdict", "?")
            merged = result.get("merged_name", "")
            print(f"  [{i+1}/{len(candidates)}] {pair['name1']} ↔ {pair['name2']} → {verdict} | {merged or '-'}")
        except Exception as e:
            print(f"  [{i+1}/{len(candidates)}] ERROR: {e}")
            results.append({"idx": pair["idx"], "verdict": "ERROR", "merged_name": None, "reason": str(e)})

        time.sleep(1)  # rate limit

    return results


def main():
    print("=== 웨이포인트 유사 병합 판단 ===\n")

    # Step 1: Load & cluster
    print("[1/4] 웨이포인트 로딩...")
    all_wps = load_all_waypoints()
    print(f"  이름 있는 WP: {len(all_wps)}개")

    print("[2/4] 정확 이름 클러스터링 (100m)...")
    pois = cluster_exact_names(all_wps)
    print(f"  유니크 POI: {len(pois)}개")

    print("[3/4] 유사 이름 후보 탐색 (500m + 유사도 {SIMILARITY_THRESHOLD}+)...")
    candidates = find_merge_candidates(pois)
    print(f"  병합 후보: {len(candidates)}쌍")

    # Save candidates
    with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"  → {CANDIDATES_FILE} 저장 완료")

    if not candidates:
        print("병합 후보 없음. 종료.")
        return

    # Step 2: Ask Gemini
    print("[4/4] Gemini 판단 요청...")
    results = ask_gemini(candidates)

    # Merge candidates + results by matching idx
    idx_to_candidate = {c["idx"]: c for c in candidates}
    for r in results:
        idx = r["idx"]
        if idx in idx_to_candidate:
            idx_to_candidate[idx]["verdict"] = r["verdict"]
            idx_to_candidate[idx]["merged_name"] = r.get("merged_name")
            idx_to_candidate[idx]["reason"] = r.get("reason", "")

    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"\n  → {RESULT_FILE} 저장 완료")

    # Summary
    same_count = sum(1 for c in candidates if c.get("verdict") == "SAME")
    diff_count = sum(1 for c in candidates if c.get("verdict") == "DIFF")
    print(f"\n=== 결과 요약 ===")
    print(f"  SAME (병합): {same_count}쌍")
    print(f"  DIFF (유지): {diff_count}쌍")
    print(f"\n리뷰 후 merge_result.json을 수정하여 적용하세요.")


if __name__ == "__main__":
    main()
