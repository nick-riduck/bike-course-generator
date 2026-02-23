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
        # Add extra points at sharp turns (U-turns) to prevent map-matching errors (e.g. detours)
        processed_input = self._densify_at_turns(processed_input, turn_degree=80.0, step=5.0)
        processed_input = self._upsample_points(processed_input, max_interval=30.0)
        
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

    def _densify_at_turns(self, points: List[Dict[str, float]], turn_degree=80.0, step=5.0) -> List[Dict[str, float]]:
        """Identify sharp turns and add extra points to aid map matching."""
        if len(points) < 3: return points
        
        n = len(points)
        densify_flags = [False] * (n - 1)
        
        for i in range(1, n - 1):
            prev, curr, next_pt = points[i-1], points[i], points[i+1]
            b1 = self._calculate_bearing(prev['lat'], prev['lon'], curr['lat'], curr['lon'])
            b2 = self._calculate_bearing(curr['lat'], curr['lon'], next_pt['lat'], next_pt['lon'])
            diff = abs(b1 - b2)
            if diff > 180: diff = 360 - diff
            
            if diff > turn_degree:
                # Mark incoming segment
                densify_flags[i-1] = True
                
                # Mark outgoing segments up to 100m
                accumulated_dist = 0.0
                for k in range(i, n - 1):
                    densify_flags[k] = True
                    # Calculate distance for this segment
                    p_start, p_end = points[k], points[k+1]
                    accumulated_dist += self._haversine(p_start['lat'], p_start['lon'], p_end['lat'], p_end['lon'])
                    
                    if accumulated_dist >= 100.0:
                        break
                
        new_points = [points[0]]
        for i in range(n - 1):
            start, end = points[i], points[i+1]
            
            if densify_flags[i]:
                dist = self._haversine(start['lat'], start['lon'], end['lat'], end['lon'])
                if dist > step:
                    count = int(dist / step)
                    for k in range(1, count + 1):
                        frac = k / (count + 1)
                        lat = start['lat'] + (end['lat'] - start['lat']) * frac
                        lon = start['lon'] + (end['lon'] - start['lon']) * frac
                        new_points.append({"lat": lat, "lon": lon})
            
            new_points.append(end)
            
        return new_points

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
        스마트 폴백 & 국소 이탈 복구 전략 (경쟁 모드):
        1. 1차 시도: 'bicycle' 모드 실행.
        2. 이탈 구간 감지 및 국소 경쟁(Repair vs Auto) 실행.
        3. 각 구간별로 더 원본에 가까운 경로를 선택하여 봉합.
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
                
                # --- 국소 경쟁 수술 (Repair) ---
                # 이탈 구간에 대해 Strict(자전거) vs Auto(차) 경쟁 붙임
                repaired_data = self._repair_segments(data, shape_points)
                
                raw_shape = polyline.decode(repaired_data.get("shape", ""), 6)
                
                # 매칭률 계산 (로그용)
                matched_points = repaired_data.get("matched_points", [])
                valid_count = 0
                for mp in matched_points:
                    if mp.get("type") == "matched" and mp.get("distance_from_trace_point", 0.0) < 100.0:
                        valid_count += 1
                
                ratio = (valid_count / len(shape_points)) * 100 if shape_points else 0
                print(f"    [Valhalla] Result: Input {len(shape_points)} -> Valid {valid_count} ({ratio:.1f}%)")
                
                return {
                    "edges": repaired_data.get("edges", []),
                    "matched_points": matched_points,
                    "shape_points": raw_shape
                }
                    
        except Exception as e:
            print(f"    [Valhalla] Try 1 (Bicycle) Failed: {e}. Fallback to 'auto' mode...")

        # --- 2차 시도: Auto (전체 폴백) ---
        trace_payload["costing"] = "auto"
        
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

    def _repair_segments(self, data: Dict[str, Any], original_input: List[Dict[str, float]]) -> Dict[str, Any]:
        """
        이탈 구간에 대해 Strict(자전거 매칭) vs Auto(자동차 라우팅) vs Original(원본) 경쟁.
        Auto의 경우 단순 매칭 대신 '라우팅(Route)'을 사용하여 연결성을 보장합니다.
        """
        matched_points = data.get("matched_points", [])
        if not matched_points: return data

        deviations = self._detect_deviations(matched_points, threshold=100.0)
        if not deviations:
            return data

        print(f"    [Valhalla] Detected {len(deviations)} deviation segments. Starting competitive repair...")

        new_edges = []
        new_shape = []
        last_input_idx = 0
        
        # 커트라인 (50m)
        MAX_ALLOWED_DIST = 50.0 
        
        for dev_start, dev_end in deviations:
            # 1. 정상 구간 복사
            if dev_start > last_input_idx:
                good_subset = original_input[last_input_idx : dev_start]
                good_res = self._trace_subset(good_subset, mode="bicycle", strict=False)
                self._append_result(new_edges, new_shape, good_res)
                
            # 2. 이탈 구간 경쟁
            bad_subset = original_input[dev_start : dev_end + 1]
            if not bad_subset:
                last_input_idx = dev_end + 1
                continue

            # 후보 1: Strict Bicycle (Map Matching)
            strict_res = self._trace_subset(bad_subset, mode="bicycle", strict=True)
            strict_shape = strict_res.get("shape", [])
            dist_strict = self._calculate_mean_distance(bad_subset, strict_shape)
            
            # 후보 2: Auto Routing (Point-to-Point Route)
            # 시작점과 끝점을 잇는 경로를 찾음
            start_pt = bad_subset[0]
            end_pt = bad_subset[-1]
            auto_shape = self._get_route_shape(start_pt, end_pt, costing="auto")
            
            if len(auto_shape) < 2: 
                dist_auto = float('inf')
            else:
                dist_auto = self._calculate_mean_distance(bad_subset, auto_shape)
            
            # 우승자 선발
            winner_res = None
            winner_name = "Original"
            
            # 원본 (Default)
            fallback_shape = [[p['lat'], p['lon']] for p in bad_subset]
            winner_res = {
                "edges": [{
                    "begin_shape_index": 0, "end_shape_index": len(fallback_shape)-1,
                    "use": "road", "surface": "unknown"
                }],
                "shape": fallback_shape
            }

            best_api_dist = min(dist_strict, dist_auto)
            
            if best_api_dist < MAX_ALLOWED_DIST:
                if dist_strict <= dist_auto:
                    winner_res = strict_res
                    winner_name = "Strict"
                else:
                    winner_res = {
                        "edges": [{
                            "begin_shape_index": 0, "end_shape_index": len(auto_shape)-1,
                            "use": "road", "surface": "paved_smooth"
                        }],
                        "shape": auto_shape
                    }
                    winner_name = "Auto(Route)"
            
            print(f"      dev[{dev_start}~{dev_end}, len={len(bad_subset)}]: Strict={dist_strict:.1f}m, Auto={dist_auto:.1f}m -> Winner: {winner_name}")
            
            self._append_result(new_edges, new_shape, winner_res)
            last_input_idx = dev_end + 1
            
        # 3. 마지막 구간 복사
        if last_input_idx < len(original_input):
            good_subset = original_input[last_input_idx:]
            good_res = self._trace_subset(good_subset, mode="bicycle", strict=False)
            self._append_result(new_edges, new_shape, good_res)
            
        return {
            "edges": new_edges,
            "shape": polyline.encode(new_shape, 6),
            "matched_points": [{"type": "matched", "distance_from_trace_point": 0.0}] * len(original_input)
        }

    def _get_route_shape(self, start_pt, end_pt, costing="bicycle") -> List[Tuple[float, float]]:
        payload = {
            "locations": [{"lat": start_pt['lat'], "lon": start_pt['lon']}, {"lat": end_pt['lat'], "lon": end_pt['lon']}],
            "costing": costing
        }
        with httpx.Client(timeout=10.0) as client:
            try:
                resp = client.post(f"{self.url}/route", json=payload)
                resp.raise_for_status()
                shape_str = resp.json().get("trip", {}).get("legs", [{}])[0].get("shape", "")
                return polyline.decode(shape_str, 6) if shape_str else []
            except:
                return []

    def _trace_subset(self, points, mode="bicycle", strict=False):
        """부분 경로에 대해 trace_attributes 호출"""
        if not points: return {"edges": [], "shape": []}
        
        # 파라미터 설정
        options = {
            "search_radius": 20 if strict else 100,
            "gps_accuracy": 5.0 if strict else 100.0,
            "breakage_distance": 200 if strict else 500,
            "turn_penalty_factor": 0 if strict else 500
        }
        
        # auto 모드일 때는 strict 옵션 무시하고 기본값 사용
        if mode == "auto":
            options = {
                "search_radius": 50, 
                "gps_accuracy": 20.0,
                "breakage_distance": 1000,
                "turn_penalty_factor": 100
            }

        payload = {
            "shape": points,
            "costing": mode,
            "shape_match": "map_snap",
            "trace_options": options,
            "filters": {"attributes": ["edge.use", "edge.surface", "edge.begin_shape_index", "edge.end_shape_index", "shape"], "action": "include"}
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{self.url}/trace_attributes", json=payload)
                resp.raise_for_status()
                d = resp.json()
                shp = polyline.decode(d.get("shape", ""), 6)
                return {"edges": d.get("edges", []), "shape": shp}
        except:
            return {"edges": [], "shape": []}

    def _calculate_mean_distance(self, original_points, result_shape):
        """원본 포인트들과 결과 경로 간의 평균 거리를 계산합니다."""
        if not result_shape: return float('inf')
        
        total_dist = 0.0
        ref_points = result_shape
        if len(ref_points) > 500:
            step = len(ref_points) // 200
            ref_points = ref_points[::step]
            
        for pt in original_points:
            lat, lon = pt['lat'], pt['lon']
            min_d = float('inf')
            for r_pt in ref_points:
                d = (lat - r_pt[0])**2 + (lon - r_pt[1])**2
                if d < min_d: min_d = d
            total_dist += math.sqrt(min_d)
            
        mean_deg = total_dist / len(original_points)
        mean_meter = mean_deg * 111000
        return mean_meter


    def _append_result(self, target_edges, target_shape, result):
        """결과(Edge, Shape)를 타겟 리스트에 이어 붙임 (인덱스 보정 포함)"""
        edges = result.get("edges", [])
        shape = result.get("shape", [])
        if not shape: return
        
        # Shape 이어 붙이기
        # 연결 부위 중복 제거 (이전 끝점과 현재 시작점이 같으면 제거)
        start_offset = 0
        if target_shape and shape:
            last = target_shape[-1]
            curr = shape[0]
            # 거리가 매우 가까우면 중복으로 간주
            if (last[0]-curr[0])**2 + (last[1]-curr[1])**2 < 1e-10:
                start_offset = 1
        
        current_base_idx = len(target_shape)
        
        # Shape 추가
        points_to_add = shape[start_offset:]
        target_shape.extend(points_to_add)
        
        # Edge 추가 (인덱스 보정)
        # start_offset만큼 shape 앞부분이 잘렸으므로, edge 인덱스도 당겨야 함
        # 하지만 edge가 0번 인덱스를 참조하고 있었다면? -> 복잡함.
        # 단순화를 위해: 추가된 shape에 맞춰 edge 인덱스를 재할당.
        
        for edge in edges:
            # 원본 shape 내에서의 인덱스
            old_start = edge.get("begin_shape_index", 0)
            old_end = edge.get("end_shape_index", 0)
            
            # 잘린 앞부분(start_offset) 반영
            if old_end < start_offset: continue # 이 엣지는 통째로 날아감
            
            new_start = max(0, old_start - start_offset)
            new_end = max(0, old_end - start_offset)
            
            # 전체 리스트 기준 인덱스로 변환
            edge["begin_shape_index"] = current_base_idx + new_start
            edge["end_shape_index"] = current_base_idx + new_end
            target_edges.append(edge)

    def _detect_deviations(self, matched_points, threshold=100.0) -> List[Tuple[int, int]]:
        """
        matched_points를 분석하여 이탈 구간(Start Idx, End Idx) 리스트 반환.
        """
        deviations = []
        n = len(matched_points)
        if n == 0: return []
        
        in_deviation = False
        start_idx = -1
        
        for i, mp in enumerate(matched_points):
            is_bad = False
            if mp.get("type") == "unmatched":
                is_bad = True
            else:
                dist = mp.get("distance_from_trace_point", 0.0)
                if dist > threshold:
                    is_bad = True
            
            if is_bad:
                if not in_deviation:
                    in_deviation = True
                    start_idx = i
            else:
                if in_deviation:
                    in_deviation = False
                    # 구간 종료 (i-1)
                    # 너무 짧은 이탈(1~2포인트)은 무시? -> 아니오, 짧아도 100m 튀면 잡아야 함.
                    deviations.append((start_idx, i - 1))
        
        if in_deviation:
            deviations.append((start_idx, n - 1))
            
        return deviations

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
