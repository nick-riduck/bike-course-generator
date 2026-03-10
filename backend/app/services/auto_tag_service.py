"""
자동 태그/설명 생성 서비스

코스 데이터(경로, 통계, 주변 POI)를 분석하여 Gemini로 태그와 설명을 자동 생성.
- 태그: 기존 DB 태그 중 매칭 + 신규 태그 제안
- 설명: 라이더 관점의 코스 소개문
"""

import os
import json
from google import genai
from google.genai import types

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _extract_route_context(full_data: dict, nearby_waypoints: list[dict]) -> dict:
    """코스 데이터에서 Gemini 프롬프트용 컨텍스트 추출."""
    stats = full_data.get("stats", {})
    points = full_data.get("points", {})
    segments = full_data.get("segments", {})

    lats = points.get("lat", [])
    lons = points.get("lon", [])
    eles = points.get("ele", [])
    grades = segments.get("avg_grade", [])
    surfs = segments.get("surf_id", [])

    surface_map = full_data.get("meta", {}).get("surface_map", {})

    # 노면 분포
    surf_dist = {}
    seg_lengths = segments.get("length", [])
    for i, sid in enumerate(surfs):
        name = surface_map.get(str(sid), "unknown")
        surf_dist[name] = surf_dist.get(name, 0) + (seg_lengths[i] if i < len(seg_lengths) else 0)
    total_len = sum(surf_dist.values()) or 1
    surf_pct = {k: round(v / total_len * 100, 1) for k, v in surf_dist.items() if v > 0}

    # 고도 프로파일 요약
    ele_min = min(eles) if eles else 0
    ele_max = max(eles) if eles else 0

    # 경사도 분포
    steep_segments = sum(1 for g in grades if abs(g) > 0.08)
    flat_segments = sum(1 for g in grades if abs(g) < 0.02)
    total_segs = len(grades) or 1

    # 시작/끝점
    start = {"lat": lats[0], "lon": lons[0]} if lats else None
    end = {"lat": lats[-1], "lon": lons[-1]} if lats else None

    distance_km = round(stats.get("distance", 0) / 1000, 1)
    elevation_gain = stats.get("ascent", 0)
    flat_pct = round(flat_segments / total_segs * 100, 1)
    steep_pct = round(steep_segments / total_segs * 100, 1)

    # 코스 성격 판단 (획득고도/km 기준)
    gain_per_km = elevation_gain / distance_km if distance_km > 0 else 0
    if gain_per_km < 5:
        course_type = "평지 코스"
    elif gain_per_km < 12:
        course_type = "완만한 업다운 코스"
    elif gain_per_km < 18:
        course_type = "힐리한 코스"
    else:
        course_type = "본격 클라이밍 코스"

    # 난이도 판단 (거리 점수 + 고도 점수 합산)
    # 거리 점수: 0~30km=1, 30~60=2, 60~100=3, 100+=4
    if distance_km < 30: dist_score = 1
    elif distance_km < 60: dist_score = 2
    elif distance_km < 100: dist_score = 3
    else: dist_score = 4

    # 고도 점수: gain_per_km 기준 0~5=0, 5~12=1, 12~18=2, 18+=3
    if gain_per_km < 5: climb_score = 0
    elif gain_per_km < 12: climb_score = 1
    elif gain_per_km < 18: climb_score = 2
    else: climb_score = 3

    total_score = dist_score + climb_score  # 1~7
    if total_score <= 2:
        difficulty = "초급"
    elif total_score <= 4:
        difficulty = "중급"
    elif total_score <= 5:
        difficulty = "중상급"
    else:
        difficulty = "상급"

    # 순환 여부
    if start and end:
        from math import radians, sin, cos, atan2, sqrt
        dlat = radians(end["lat"] - start["lat"])
        dlon = radians(end["lon"] - start["lon"])
        a = sin(dlat/2)**2 + cos(radians(start["lat"])) * cos(radians(end["lat"])) * sin(dlon/2)**2
        start_end_dist_km = 6371 * 2 * atan2(sqrt(a), sqrt(1-a))
        is_loop = start_end_dist_km < distance_km * 0.1  # 총 거리의 10% 이내면 순환
    else:
        is_loop = False

    return {
        "distance_km": distance_km,
        "elevation_gain_m": elevation_gain,
        "elevation_loss_m": stats.get("descent", 0),
        "ele_min_m": round(ele_min, 1),
        "ele_max_m": round(ele_max, 1),
        "surface_pct": surf_pct,
        "steep_pct": steep_pct,
        "flat_pct": flat_pct,
        "start": start,
        "end": end,
        "course_type": course_type,
        "difficulty": difficulty,
        "is_loop": is_loop,
        "nearby_pois": [
            {
                "name": w["name"],
                "type": w["type"],
                "distance_m": w.get("distance_m", 0),
                "dist_from_start_m": w.get("dist_from_start_m", 0),
                "priority": w.get("priority", "route")
            }
            for w in nearby_waypoints[:20]
        ],
    }


def _build_prompt(context: dict, existing_tags: list[str]) -> str:
    """Gemini 프롬프트 생성."""
    pois_text = ""
    if context["nearby_pois"]:
        groups = {"start": [], "control_point": [], "route": [], "end": []}
        for p in context["nearby_pois"]:
            groups[p.get("priority", "route")].append(p)

        pois_lines = []
        labels = [
            ("start", "🚩 출발지 인근 (가장 중요)"),
            ("control_point", "📍 사용자 지정 경유지 인근 (매우 중요, 필수 경유)"),
            ("route", "🛣️ 경로상 주변 (참고, 지나가는 길)"),
            ("end", "🏁 도착지 인근 (가장 중요)")
        ]

        for key, label in labels:
            if groups[key]:
                pois_lines.append(f"{label}:")
                # 코스 진행 순서(거리)로 정렬
                sorted_pois = sorted(groups[key], key=lambda x: x['dist_from_start_m'])
                for p in sorted_pois:
                    types_str = ', '.join(p['type']) if isinstance(p['type'], list) else p['type']
                    dist = p['distance_m']
                    if dist <= 50:
                        dist_str = "인접"
                    elif dist <= 200:
                        dist_str = "인근"
                    else:
                        dist_str = "주변"
                    
                    km_from_start = p['dist_from_start_m'] / 1000.0
                    if km_from_start < 0.1:
                        km_str = "출발 직후"
                    else:
                        km_str = f"약 {km_from_start:.1f}km 지점"

                    pois_lines.append(f"  - {p['name']} ({types_str} / {km_str}, 코스에서 {dist_str})")

        pois_text = "주변 웨이포인트(주요 지점) - 코스 진행 순서 및 중요도별:\n" + "\n".join(pois_lines)

    return f"""당신은 자전거 코스 분석 전문가입니다. 아래 코스 데이터를 분석하여 태그와 설명을 생성하세요.

## 코스 데이터
- 거리: {context['distance_km']}km
- 획득고도: {context['elevation_gain_m']}m / 하강고도: {context['elevation_loss_m']}m
- 최저고도: {context['ele_min_m']}m / 최고고도: {context['ele_max_m']}m
- 노면: {json.dumps(context['surface_pct'], ensure_ascii=False)}
- 급경사 구간: {context['steep_pct']}% / 평지 구간: {context['flat_pct']}%
- 시작점: {context['start']}
- 종료점: {context['end']}

## 코스 성격 (사전 분석 결과, 설명에 반영할 것)
- 코스 유형: {context['course_type']}
- 난이도: {context['difficulty']}
- 코스 형태: {'순환형 (출발지 ≈ 도착지)' if context['is_loop'] else '편도형'}
{pois_text}

## 기존 태그 목록 (우선 이 중에서 선택)
{', '.join(existing_tags[:100])}

## 요구사항

### 1. 태그 (tags)
- 기존 태그 중 이 코스에 해당하는 것을 모두 선택
- 기존에 없지만 필요한 태그는 신규로 제안 (한글, 2~4자)
- 지역명, 코스 특성, 난이도, 풍경, 노면 등 다양한 관점
- 최소 3개, 최대 10개

### 2. 설명 (description)
- 마크다운 형식으로, 아래 두 파트를 순서대로 작성하세요.

**파트 1: 중요 정보 (맨 위에 "#### **중요 정보**" 헤딩으로 배치)**
- 마크다운 리스트(- )로 작성
- 각 항목에 가능하면 "약 X.Xkm 지점" 위치 정보를 포함
- 항목:
  - 보급 및 편의시설: 편의점, 카페, 식당 등 (웨이포인트 기반)
  - 주차 및 화장실: 출발지/경유지 인근 주차장, 화장실
  - 주의 및 위험구간: 차량 통행량, 노면 불량, 급경사 등
- 데이터에 근거한 항목만 작성. 없으면 해당 항목 생략.

**파트 2: 상세 ("#### **상세**" 헤딩으로 배치)**
- 2~4문장의 간결한 서술형
- 출발→경유→도착 흐름으로 코스의 성격, 지형, 노면, 풍경을 자연스럽게 묘사
- 통계 수치 단순 나열 금지. 라이더 관점에서 어떤 느낌의 코스인지 전달

**전체 규칙:**
- 과장 금지. 데이터 기반으로 정확하게.
- 웨이포인트(출발지/도착지/경유지 인근 POI)를 자연스럽게 언급.

### 3. 제목 (title)
- 짧고 임팩트 있는 코스 제목 (20자 이내)
- 핵심 지역명 + 코스 특징을 조합 (예: "한강 야경 라이딩", "북한산 힐클라임")
- 이모지 사용하지 않기

## 응답 형식 (JSON만, 다른 텍스트 없이)
```json
{{
  "tags": ["태그1", "태그2", ...],
  "description": "코스 설명 텍스트",
  "title": "코스 제목"
}}
```"""


def _get_waypoints_along_route(conn, route_line_wkt: str, radius_m: int = 500) -> list[dict]:
    """경로 선(LineString)을 따라 radius_m 이내의 waypoints 검색 및 코스 상 위치 계산."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, type::text[], description,
               ST_Distance(
                   location::geography,
                   ST_GeomFromText(%s, 4326)::geography
               ) as distance_m,
               (ST_LineLocatePoint(
                   ST_GeomFromText(%s, 4326),
                   location::geometry
               ) * ST_Length(ST_GeomFromText(%s, 4326)::geography)) as dist_from_start_m
        FROM waypoints
        WHERE ST_DWithin(
            location::geography,
            ST_GeomFromText(%s, 4326)::geography,
            %s
        )
        ORDER BY distance_m
    """, (route_line_wkt, route_line_wkt, route_line_wkt, route_line_wkt, radius_m))
    rows = cur.fetchall()
    cur.close()
    return [
        {"id": r["id"], "name": r["name"], "type": r["type"],
         "description": r["description"], "distance_m": round(r["distance_m"]),
         "dist_from_start_m": round(r["dist_from_start_m"]) if r["dist_from_start_m"] is not None else 0,
         "priority": "route"}
        for r in rows
    ]


def _get_waypoints_near_control_points(conn, control_points: list[dict], route_line_wkt: str | None = None, radius_m: int = 200) -> list[dict]:
    """사용자가 직접 찍은 포인트(control points) 인근 waypoints 검색. 코스 상 위치 계산 포함."""
    if not control_points:
        return []

    results = []
    seen_ids = set()
    cur = conn.cursor()

    for cp in control_points:
        lat, lon = cp["lat"], cp["lon"]
        if route_line_wkt:
            cur.execute("""
                SELECT id, name, type::text[], description,
                       ST_Distance(
                           location::geography,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                       ) as distance_m,
                       (ST_LineLocatePoint(
                           ST_GeomFromText(%s, 4326),
                           location::geometry
                       ) * ST_Length(ST_GeomFromText(%s, 4326)::geography)) as dist_from_start_m
                FROM waypoints
                WHERE ST_DWithin(
                    location::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY distance_m
            """, (lon, lat, route_line_wkt, route_line_wkt, lon, lat, radius_m))
        else:
            cur.execute("""
                SELECT id, name, type::text[], description,
                       ST_Distance(
                           location::geography,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                       ) as distance_m,
                       0 as dist_from_start_m
                FROM waypoints
                WHERE ST_DWithin(
                    location::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY distance_m
            """, (lon, lat, lon, lat, radius_m))

        for r in cur.fetchall():
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                results.append({
                    "id": r["id"], "name": r["name"], "type": r["type"],
                    "description": r["description"], "distance_m": round(r["distance_m"]),
                    "dist_from_start_m": round(r["dist_from_start_m"]) if r["dist_from_start_m"] is not None else 0,
                    "priority": "control_point"
                })

    cur.close()
    return results


def _extract_control_points(full_data: dict) -> list[dict]:
    """editor_state에서 사용자가 직접 찍은 포인트 추출."""
    editor_state = full_data.get("editor_state", {})
    sections = editor_state.get("sections", [])
    points = []
    for section in sections:
        for pt in section.get("points", []):
            lat = pt.get("lat")
            lon = pt.get("lng") or pt.get("lon")
            if lat and lon:
                points.append({"lat": lat, "lon": lon, "name": pt.get("name", "")})
    return points


def _build_route_line_wkt(full_data: dict) -> str | None:
    """full_data의 points에서 간소화된 LineString WKT 생성."""
    lats = full_data.get("points", {}).get("lat", [])
    lons = full_data.get("points", {}).get("lon", [])
    if len(lats) < 2:
        return None
    # 포인트가 많으면 샘플링 (PostGIS 쿼리 성능)
    step = max(1, len(lats) // 200)
    coords = []
    for i in range(0, len(lats), step):
        coords.append(f"{lons[i]} {lats[i]}")
    if (len(lats) - 1) % step != 0:
        coords.append(f"{lons[-1]} {lats[-1]}")
    return f"LINESTRING({', '.join(coords)})"


def get_existing_tags(conn) -> list[str]:
    """DB에 있는 모든 태그 slug 목록."""
    cur = conn.cursor()
    cur.execute("SELECT slug FROM tags ORDER BY id")
    tags = [r["slug"] for r in cur.fetchall()]
    cur.close()
    return tags


def generate_tags_and_description(conn, full_data: dict) -> dict:
    """
    코스 데이터로 태그와 설명 자동 생성.

    웨이포인트 검색 전략:
    1. 출발지/도착지 인근 200m 웨이포인트 (가장 높은 우선순위)
    2. 사용자 지정 control points 인근 200m 웨이포인트 (높은 우선순위)
    3. 경로 선(LineString)을 따라 500m 이내 웨이포인트
    4. 합쳐서 중복 제거, 우선순위 순 정렬

    Returns:
        {"tags": ["태그1", ...], "description": "코스 설명"}
    """
    lats = full_data.get("points", {}).get("lat", [])
    lons = full_data.get("points", {}).get("lon", [])
    if not lats:
        return {"tags": [], "description": ""}

    route_wkt = _build_route_line_wkt(full_data)

    # 1. 출발지 / 도착지 인근 웨이포인트 (200m)
    start_point = [{"lat": lats[0], "lon": lons[0]}]
    end_point = [{"lat": lats[-1], "lon": lons[-1]}]
    
    start_pois = _get_waypoints_near_control_points(conn, start_point, route_wkt, radius_m=200)
    for p in start_pois: p["priority"] = "start"
    
    end_pois = _get_waypoints_near_control_points(conn, end_point, route_wkt, radius_m=200)
    for p in end_pois: p["priority"] = "end"

    # 2. Control points 인근 웨이포인트 (200m)
    control_points = _extract_control_points(full_data)
    cp_pois = _get_waypoints_near_control_points(conn, control_points, route_wkt, radius_m=200)
    for p in cp_pois: p["priority"] = "control_point"

    # 3. 경로 선 따라 웨이포인트 검색 (500m)
    route_pois = _get_waypoints_along_route(conn, route_wkt, radius_m=500) if route_wkt else []
    for p in route_pois: p["priority"] = "route"

    # 4. 합치기: start/end -> control_point -> route 우선, 중복 제거
    seen_ids = set()
    merged = []
    
    for wp in start_pois + end_pois + cp_pois + route_pois:
        if wp["id"] not in seen_ids:
            seen_ids.add(wp["id"])
            merged.append(wp)

    existing_tags = get_existing_tags(conn)
    context = _extract_route_context(full_data, merged)
    prompt = _build_prompt(context, existing_tags)

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    try:
        result = json.loads(response.text)
        tags = [t.strip().lower() for t in result.get("tags", []) if t.strip()]
        description = result.get("description", "").strip()
        title = result.get("title", "").strip()
        return {"tags": tags, "description": description, "title": title}
    except (json.JSONDecodeError, AttributeError):
        return {"tags": [], "description": "", "title": ""}
