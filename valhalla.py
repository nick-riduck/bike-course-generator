"""
================================================================================
SHARED MODULE: Valhalla Client & Unified Parser
================================================================================
이 모듈은 'GPX 시뮬레이터'와 '코스 생성기' 프로젝트 간에 공유되는 핵심 로직입니다.
로직 수정 시 반드시 양쪽 프로젝트의 파일을 모두 최신화해야 합니다.

Source Location: bike_course_simulator/src/valhalla_client.py
================================================================================
"""

import os
import math
import httpx
import polyline
from typing import List, Dict, Any, Tuple

# --- Configuration (Environment Variables) ---
VALHALLA_URL = os.environ.get("VALHALLA_URL", "http://localhost:8002")
GRADE_THRESHOLD = float(os.environ.get("SIM_SEGMENT_GRADE_THRESHOLD", 0.005))   # 0.5%
HEADING_THRESHOLD = float(os.environ.get("SIM_SEGMENT_HEADING_THRESHOLD", 10.0)) # 10.0 deg
MAX_LENGTH = float(os.environ.get("SIM_SEGMENT_MAX_LENGTH", 200.0))             # 200m
CHUNK_SIZE = int(os.environ.get("VALHALLA_CHUNK_SIZE", 3000))
MATCH_THRESHOLD = float(os.environ.get("VALHALLA_MATCH_THRESHOLD", 65.0))
FALLBACK_MODE = os.environ.get("VALHALLA_FALLBACK_MODE", "true").lower() == "true"

# --- Constants & Mapping ---
SURFACE_MAP = {
    0: "unknown",
    1: "asphalt",
    2: "concrete",
    3: "wood_metal",
    4: "paving_stones",
    5: "cycleway",
    6: "compacted",
    7: "gravel_dirt"
}

def get_surface_id(edge: Dict[str, Any]) -> int:
    """Valhalla Edge 속성을 기반으로 내부 Surface ID 및 Crr 매핑"""
    surf = str(edge.get("surface", "unknown")).lower()
    use = str(edge.get("use", "road")).lower()
    
    if use in ["cycleway", "bicycle"]: return 5
    if surf in ["wood", "metal"]: return 3
    if "concrete" in surf: return 2
    if surf in ["paving_stones", "sett", "cobblestone:flattened"]: return 4
    if surf in ["compacted", "fine_gravel", "tartan"]: return 6
    if surf in ["gravel", "unpaved", "dirt", "earth", "sand", "cobblestone"]: return 7
    if surf in ["asphalt", "paved", "paved_smooth"]: return 1
    return 0

class ValhallaClient:
    def __init__(self, url: str = VALHALLA_URL):
        self.url = url
        self.timeout = 60.0 

    def get_standard_course(self, shape_points: List[Dict[str, float]]) -> Dict[str, Any]:
        """Valhalla API를 호출하여 표준 JSON(v1.0) 데이터를 생성"""
        
        # [Step 0] Smart Gap Filling & Upsampling
        processed_input = self._fill_gaps_with_routing(shape_points, gap_threshold=500.0)
        processed_input = self._upsample_points(processed_input, max_interval=50.0)
        
        total_points = len(processed_input)
        if total_points <= CHUNK_SIZE:
            return self._request_and_parse(processed_input)
            
        print(f"Input points {total_points} > {CHUNK_SIZE}, splitting into chunks...")
        
        OVERLAP = 200 
        merged_edges = []
        merged_shape = [] # [[lat,lon], ...]
        
        current_idx = 0
        while current_idx < total_points:
            end_idx = min(current_idx + CHUNK_SIZE, total_points)
            req_start = max(0, current_idx - OVERLAP)
            req_end = end_idx
            
            chunk_input = processed_input[req_start : req_end]
            result = self._request_raw_data_no_ele(chunk_input)
            
            edges = result["edges"]
            shape = result["shape_points"]
            
            # --- Geometric Stitching Logic ---
            if current_idx == 0:
                merged_edges.extend(edges)
                merged_shape.extend(shape)
            else:
                if not merged_shape:
                    merged_shape.extend(shape)
                    merged_edges.extend(edges)
                else:
                    last_pt = merged_shape[-1]
                    best_idx = 0
                    min_dist = float('inf')
                    search_limit = min(len(shape), OVERLAP * 2) 
                    
                    for k in range(search_limit):
                        curr_pt = shape[k]
                        d = (last_pt[0] - curr_pt[0])**2 + (last_pt[1] - curr_pt[1])**2
                        if d < min_dist:
                            min_dist = d
                            best_idx = k
                    
                    shape_to_append = shape[best_idx:]
                    if len(shape_to_append) > 1:
                        shape_to_append = shape_to_append[1:]
                        best_idx += 1
                    
                    prev_shape_len = len(merged_shape)
                    merged_shape.extend(shape_to_append)
                    
                    for edge in edges:
                        start_i = edge.get("begin_shape_index", 0)
                        end_i = edge.get("end_shape_index", 0)
                        if end_i < best_idx: continue
                        
                        new_start_i = max(start_i, best_idx)
                        mapped_start = prev_shape_len + (new_start_i - best_idx)
                        mapped_end = prev_shape_len + (end_i - best_idx)
                        
                        edge["begin_shape_index"] = mapped_start
                        edge["end_shape_index"] = mapped_end
                        merged_edges.append(edge)

            current_idx += CHUNK_SIZE - OVERLAP 
            if req_end == total_points: break

        print(f"Fetching bulk elevations for {len(merged_shape)} points...")
        final_elevations = self._get_bulk_elevations(merged_shape)
        return self._parse_to_standard_format({"edges": merged_edges}, merged_shape, final_elevations)

    def _get_bulk_elevations(self, shape: List[Tuple[float, float]]) -> List[float]:
        H_CHUNK = 4000
        all_heights = []
        for i in range(0, len(shape), H_CHUNK):
            chunk = shape[i : i + H_CHUNK]
            payload = {"shape": [{"lat": l, "lon": r} for l, r in chunk], "range": False}
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(f"{self.url}/height", json=payload)
                    resp.raise_for_status()
                    heights = resp.json().get("height", [0.0]*len(chunk))
                    all_heights.extend([h if h is not None else 0.0 for h in heights])
            except Exception as e:
                print(f"  Warning: Elevation fetch failed for chunk {i}: {e}")
                all_heights.extend([0.0]*len(chunk))
        return all_heights

    def _fill_gaps_with_routing(self, points: List[Dict[str, float]], gap_threshold=500.0) -> List[Dict[str, float]]:
        if not points or len(points) < 2: return points
        filled_points = [points[0]]
        for i in range(1, len(points)):
            prev, curr = filled_points[-1], points[i]
            dist = self._haversine(prev['lat'], prev['lon'], curr['lat'], curr['lon'])
            if dist > gap_threshold:
                try:
                    route_shape = self._get_route_shape(prev, curr)
                    if len(route_shape) > 2:
                        for pt in route_shape[1:-1]:
                            filled_points.append({"lat": pt[0], "lon": pt[1]})
                except: pass
            filled_points.append(curr)
        return filled_points

    def _get_route_shape(self, start_pt, end_pt) -> List[Tuple[float, float]]:
        payload = {
            "locations": [{"lat": start_pt['lat'], "lon": start_pt['lon']}, {"lat": end_pt['lat'], "lon": end_pt['lon']}],
            "costing": "bicycle"
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.url}/route", json=payload)
            resp.raise_for_status()
            shape_str = resp.json().get("trip", {}).get("legs", [{}])[0].get("shape", "")
            return polyline.decode(shape_str, 6) if shape_str else []

    def _upsample_points(self, points: List[Dict[str, float]], max_interval=30.0) -> List[Dict[str, float]]:
        if not points: return []
        upsampled = [points[0]]
        for i in range(1, len(points)):
            prev, curr = upsampled[-1], points[i]
            d = self._haversine(prev['lat'], prev['lon'], curr['lat'], curr['lon'])
            if d > max_interval:
                count = int(d / max_interval)
                for k in range(1, count + 1):
                    frac = k / (count + 1)
                    upsampled.append({
                        "lat": prev['lat'] + (curr['lat'] - prev['lat']) * frac,
                        "lon": prev['lon'] + (curr['lon'] - prev['lon']) * frac
                    })
            upsampled.append(curr)
        return upsampled

    def _request_raw_data_no_ele(self, shape_points):
        """
        스마트 폴백 전략:
        1. 우선 'bicycle' 모드로 시도 (자전거 최적화)
        2. 결과 포인트 비율이 70% 미만이면 매칭 실패로 간주하고 'auto' 모드로 재시도 (남산 등 데이터 누락 구간 구제)
        """
        
        # --- 1차 시도: Bicycle (기본값) ---
        trace_payload = {
            "shape": shape_points,
            "costing": "bicycle",
            "shape_match": "map_snap",
            "trace_options": {
                "search_radius": 100,
                "gps_accuracy": 100.0,
                "breakage_distance": 500,
                "turn_penalty_factor": 500
            }, 
            "filters": {
                "attributes": [
                    "edge.use", "edge.surface", "edge.begin_shape_index", "edge.end_shape_index", "shape", 
                    "matched.point", "matched.edge_index", "matched.type", "matched.distance_from_trace_point"
                ],
                "action": "include"
            }
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.url}/trace_attributes", json=trace_payload)
                resp.raise_for_status()
                data = resp.json()
                raw_shape = polyline.decode(data.get("shape", ""), 6)
                
                # --- 실패 감지 로직 (통합 지표: 유효 매칭 비율) ---
                # matched_points 정보 활용 (각 입력 포인트가 어디에 매칭되었는지 확인)
                matched_points = data.get("matched_points", [])
                
                valid_count = 0
                total_input = len(shape_points)
                matched_points = data.get("matched_points", [])
                # if matched_points:
                #     print(f"    [Valhalla] DEBUG: First matched point keys: {list(matched_points[0].keys())}")
                
                # 유효 포인트 판별 로직
                for mp in matched_points:
                    if mp.get("type") == "matched":
                        # API가 제공하는 distance_from_trace_point 사용 (단위: 미터)
                        dist = mp.get("distance_from_trace_point", 0.0)
                        if dist < 100.0: # 100m 이내 오차만 인정
                            valid_count += 1
                
                # 개수 불일치 시 로그 출력
                # if len(matched_points) != total_input:
                #     print(f"    [Valhalla] Note: Match count mismatch ({len(matched_points)} vs {total_input})")
                
                ratio = (valid_count / total_input) * 100 if total_input > 0 else 0
                print(f"    [Valhalla] Try 1 (Bicycle): Input {total_input} -> Valid {valid_count} ({ratio:.1f}%)")
                
                # --- 검증 및 폴백 판단 ---
                if not FALLBACK_MODE or ratio >= MATCH_THRESHOLD:
                    return {
                        "edges": data.get("edges", []),
                        "matched_points": matched_points,
                        "shape_points": raw_shape
                    }
                else:
                    print(f"    [Valhalla] Low valid match ratio ({ratio:.1f}% < {MATCH_THRESHOLD}%). Fallback to 'auto' mode...")
                    
        except Exception as e:
            print(f"    [Valhalla] Try 1 (Bicycle) Failed: {e}. Fallback to 'auto' mode...")

        # --- 2차 시도: Auto (폴백) ---
        # costing만 auto로 변경하여 재시도
        trace_payload["costing"] = "auto"
        # auto 모드에서는 오차 허용을 좀 더 줄여도 됨 (도로는 정확하므로)
        # 하지만 일관성을 위해 유지하거나, 필요 시 조정 가능. 일단 유지.
        
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.url}/trace_attributes", json=trace_payload)
            resp.raise_for_status()
            data = resp.json()
            raw_shape = polyline.decode(data.get("shape", ""), 6)
            
            print(f"    [Valhalla] Try 2 (Auto): Input {len(shape_points)} -> Output {len(raw_shape)}")
            
            return {
                "edges": data.get("edges", []),
                "matched_points": data.get("matched_points", []),
                "shape_points": raw_shape
            }

    def _request_and_parse(self, shape_points):
        raw = self._request_raw_data_no_ele(shape_points)
        elevations = self._get_bulk_elevations(raw["shape_points"])
        return self._parse_to_standard_format({"edges": raw["edges"]}, raw["shape_points"], elevations)

    def _parse_to_standard_format(self, data: Dict[str, Any], raw_shape: List[Tuple[float, float]], elevations: List[float]) -> Dict[str, Any]:
        smoothed_ele = self._smooth_elevation(elevations, window_size=21)
        edges = data.get("edges", [])
        resampled_points = self._enrich_points_and_resample(raw_shape, smoothed_ele, edges)
        final_points = self._filter_outliers_post_resample(resampled_points, max_grade=0.20)
        segments = self._generate_segments(final_points)
        total_dist = final_points[-1][3] if final_points else 0
        ascent = sum(max(0, final_points[i][2] - final_points[i-1][2]) for i in range(1, len(final_points)))

        return {
            "version": "1.0",
            "meta": {"creator": "Riduck Unified Parser", "surface_map": SURFACE_MAP},
            "stats": {
                "distance": round(total_dist, 1),
                "ascent": round(ascent, 1),
                "points_count": len(final_points),
                "segments_count": len(segments["p_start"])
            },
            "points": {
                "lat": [p[0] for p in final_points],
                "lon": [p[1] for p in final_points],
                "ele": [p[2] for p in final_points],
                "dist": [p[3] for p in final_points],
                "grade": [p[4] for p in final_points],
                "surf": [p[5] for p in final_points]
            },
            "segments": segments,
            "control_points": []
        }

    def _filter_outliers_post_resample(self, points: List[List[float]], max_grade=0.20) -> List[List[float]]:
        count = len(points)
        new_points = [list(p) for p in points]
        for _pass in range(2):
            i = 1
            while i < count:
                d = new_points[i][3] - new_points[i-1][3]
                if d < 1.0: 
                    i += 1
                    continue
                current_ele, prev_ele = new_points[i][2], new_points[i-1][2]
                grade = abs((current_ele - prev_ele) / d)
                if grade > max_grade:
                    s_idx, e_idx = max(0, i - 3), min(count - 1, i + 3)
                    start_h, end_h = new_points[s_idx][2], new_points[e_idx][2]
                    h_diff = end_h - start_h
                    total_d = new_points[e_idx][3] - new_points[s_idx][3]
                    if total_d > 0:
                        for k in range(s_idx + 1, e_idx + 1):
                            dist_from_s = new_points[k][3] - new_points[s_idx][3]
                            new_ele = start_h + (h_diff * (dist_from_s / total_d))
                            new_points[k][2] = new_ele
                            if k > 0:
                                d_k = new_points[k][3] - new_points[k-1][3]
                                if d_k > 0: new_points[k][4] = (new_points[k][2] - new_points[k-1][2]) / d_k
                    i = e_idx + 1
                else:
                    new_points[i][4] = (current_ele - prev_ele) / d
                    i += 1
        return new_points

    def _smooth_elevation(self, data: List[float], window_size: int = 21) -> List[float]:
        if not data or len(data) < window_size: return data
        pad = window_size // 2
        padded = [data[0]] * pad + data + [data[-1]] * pad
        return [sum(padded[i : i + window_size]) / window_size for i in range(len(data))]

    def _enrich_points_and_resample(self, shape, elevations, edges) -> List[List[float]]:
        surf_id_map = {}
        for edge in edges:
            sid = get_surface_id(edge)
            for i in range(edge.get("begin_shape_index", 0), edge.get("end_shape_index", 0) + 1):
                surf_id_map[i] = sid
        resampled = []
        resampled.append([shape[0][0], shape[0][1], elevations[0], 0.0, 0.0, surf_id_map.get(0, 1)])
        cum_dist, seg_dist, MIN_INTERVAL = 0.0, 0.0, 10.0
        for i in range(1, len(shape)):
            d = self._haversine(shape[i-1][0], shape[i-1][1], shape[i][0], shape[i][1])
            cum_dist += d
            seg_dist += d
            if seg_dist >= MIN_INTERVAL or i == len(shape) - 1:
                grade = (elevations[i] - resampled[-1][2]) / seg_dist if seg_dist > 0 else 0
                resampled.append([shape[i][0], shape[i][1], elevations[i], cum_dist, grade, surf_id_map.get(i, 1)])
                seg_dist = 0.0
        return resampled

    def _generate_segments(self, points: List[List[float]]) -> Dict[str, List[Any]]:
        segs = {"p_start": [], "p_end": [], "length": [], "avg_grade": [], "surf_id": [], "avg_head": []}
        if not points: return segs
        start_idx = 0
        ref_surf, ref_grade = points[0][5], points[0][4]
        ref_head = self._calculate_bearing(points[0][0], points[0][1], points[1][0], points[1][1]) if len(points) > 1 else 0
        for i in range(1, len(points)):
            curr, start_pt = points[i], points[start_idx]
            seg_len = curr[3] - start_pt[3]
            if seg_len < 1.0: continue
            curr_head = self._calculate_bearing(points[i-1][0], points[i-1][1], curr[0], curr[1])
            head_diff = abs(curr_head - ref_head)
            if head_diff > 180: head_diff = 360 - head_diff
            is_last = (i == len(points) - 1)
            if (curr[5] != ref_surf) or (abs(curr[4] - ref_grade) > GRADE_THRESHOLD) or (head_diff > HEADING_THRESHOLD) or (seg_len >= MAX_LENGTH) or is_last:
                segs["p_start"].append(start_idx)
                segs["p_end"].append(i)
                segs["length"].append(round(seg_len, 2))
                segs["avg_grade"].append(round((curr[2] - start_pt[2]) / seg_len if seg_len > 0 else 0, 5))
                segs["surf_id"].append(ref_surf)
                segs["avg_head"].append(round(ref_head, 1))
                start_idx, ref_surf, ref_grade = i, curr[5], curr[4]
                if not is_last: ref_head = self._calculate_bearing(curr[0], curr[1], points[i+1][0], points[i+1][1])
        return segs

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def _calculate_bearing(self, lat1, lon1, lat2, lon2) -> float:
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        return (math.degrees(math.atan2(y, x)) + 360) % 360
