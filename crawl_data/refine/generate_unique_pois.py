#!/usr/bin/env python3
"""
Phase 1 클러스터링 + Phase 2 Gemini 병합 결과를 적용하여
최종 unique_pois.json을 생성한다.
"""

import os
import json
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2

CRAWL_DIR = os.path.join(os.path.dirname(__file__), "..", "KOMOOT_FULL")
OUTPUT_DIR = os.path.dirname(__file__)
MERGE_RESULT_FILE = os.path.join(OUTPUT_DIR, "merge_result_gemini.json")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "unique_pois.json")

EXACT_NAME_CLUSTER_RADIUS_M = 100


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def load_all_waypoints():
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
    """Phase 1: exact name + 100m → unique POIs."""
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
            categories = list(set(w["category"] for w in cluster))
            pois.append({
                "name": name,
                "category": categories[0] if len(categories) == 1 else categories,
                "lat": round(sum(w["lat"] for w in cluster) / len(cluster), 6),
                "lng": round(sum(w["lng"] for w in cluster) / len(cluster), 6),
                "count": len(cluster),
                "tour_count": len(tour_ids),
                "has_images": any(w["has_images"] for w in cluster),
                "has_tips": any(w["has_tips"] for w in cluster),
            })
    return pois


def apply_phase2_merges(pois):
    """Phase 2 Gemini 결과 적용: merged=true인 쌍의 name2를 name1으로 병합."""
    with open(MERGE_RESULT_FILE, encoding="utf-8") as f:
        merges = json.load(f)

    # merged=true or merged="true" 처리
    same_pairs = [m for m in merges if str(m.get("merged")).lower() == "true"]

    # name → POI index lookup
    name_to_idx = {}
    for i, poi in enumerate(pois):
        name_to_idx.setdefault(poi["name"], []).append(i)

    # 병합 대상 추적: 어떤 이름이 어떤 대표 이름으로 병합되는지
    # Union-Find 방식으로 처리 (체인 병합 대응)
    rename_map = {}  # original_name → merged_name

    for pair in same_pairs:
        name1 = pair["name1"]
        name2 = pair["name2"]
        merged_name = pair.get("merged_name") or name1

        # name1, name2 모두 이미 rename된 경우 추적
        while name1 in rename_map:
            name1 = rename_map[name1]
        while name2 in rename_map:
            name2 = rename_map[name2]

        # 둘 다 같은 이름이면 스킵
        if name1 == name2:
            continue

        # name2를 merged_name으로 rename
        rename_map[name2] = merged_name
        if name1 != merged_name:
            rename_map[name1] = merged_name

    # 실제 적용: POI 리스트에서 병합
    merged_indices = set()
    for pair in same_pairs:
        name1 = pair["name1"]
        name2 = pair["name2"]
        merged_name = pair.get("merged_name") or name1

        # name2에 해당하는 POI 찾기
        idxs2 = name_to_idx.get(name2, [])
        idxs1 = name_to_idx.get(name1, [])

        if not idxs2 or not idxs1:
            continue

        # name2의 POI들을 name1 POI로 흡수
        primary = pois[idxs1[0]]
        for idx2 in idxs2:
            secondary = pois[idx2]
            # 좌표가 가까운지 확인 (500m 이내)
            dist = haversine(primary["lat"], primary["lng"], secondary["lat"], secondary["lng"])
            if dist < 600:  # merge_result의 거리 기준보다 약간 여유
                primary["count"] = primary.get("count", 1) + secondary.get("count", 1)
                primary["tour_count"] = primary.get("tour_count", 1) + secondary.get("tour_count", 1)
                primary["has_images"] = primary["has_images"] or secondary["has_images"]
                primary["has_tips"] = primary["has_tips"] or secondary["has_tips"]
                merged_indices.add(idx2)

        # 대표 이름 적용
        primary["name"] = merged_name

    # 병합된 POI 제거
    result = [poi for i, poi in enumerate(pois) if i not in merged_indices]
    return result, len(merged_indices)


def main():
    print("=== unique_pois.json 생성 ===\n")

    print("[1/3] 웨이포인트 로딩...")
    all_wps = load_all_waypoints()
    print(f"  이름 있는 WP: {len(all_wps)}개")

    print("[2/3] Phase 1: 정확 이름 클러스터링 (100m)...")
    pois = cluster_exact_names(all_wps)
    print(f"  유니크 POI: {len(pois)}개")

    print("[3/3] Phase 2: Gemini 병합 결과 적용...")
    pois, merged_count = apply_phase2_merges(pois)
    print(f"  병합 제거: {merged_count}개")
    print(f"  최종 POI: {len(pois)}개")

    # tour_count 기준 내림차순 정렬
    pois.sort(key=lambda x: (-x["tour_count"], -x["count"], x["name"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(pois, f, ensure_ascii=False, indent=2)
    print(f"\n→ {OUTPUT_FILE} 저장 완료")


if __name__ == "__main__":
    main()
