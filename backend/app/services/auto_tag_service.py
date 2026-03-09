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
        _client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
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

    return {
        "distance_km": round(stats.get("distance", 0) / 1000, 1),
        "elevation_gain_m": stats.get("ascent", 0),
        "elevation_loss_m": stats.get("descent", 0),
        "ele_min_m": round(ele_min, 1),
        "ele_max_m": round(ele_max, 1),
        "surface_pct": surf_pct,
        "steep_pct": round(steep_segments / total_segs * 100, 1),
        "flat_pct": round(flat_segments / total_segs * 100, 1),
        "start": start,
        "end": end,
        "nearby_pois": [
            {"name": w["name"], "type": w["type"], "distance_m": w.get("distance_m", 0)}
            for w in nearby_waypoints[:15]
        ],
    }


def _build_prompt(context: dict, existing_tags: list[str]) -> str:
    """Gemini 프롬프트 생성."""
    pois_text = ""
    if context["nearby_pois"]:
        pois_lines = []
        for p in context["nearby_pois"]:
            pois_lines.append(f"  - {p['name']} ({', '.join(p['type']) if isinstance(p['type'], list) else p['type']}, {p['distance_m']}m)")
        pois_text = "주변 POI:\n" + "\n".join(pois_lines)

    return f"""당신은 자전거 코스 분석 전문가입니다. 아래 코스 데이터를 분석하여 태그와 설명을 생성하세요.

## 코스 데이터
- 거리: {context['distance_km']}km
- 획득고도: {context['elevation_gain_m']}m / 하강고도: {context['elevation_loss_m']}m
- 최저고도: {context['ele_min_m']}m / 최고고도: {context['ele_max_m']}m
- 노면: {json.dumps(context['surface_pct'], ensure_ascii=False)}
- 급경사 구간: {context['steep_pct']}% / 평지 구간: {context['flat_pct']}%
- 시작점: {context['start']}
- 종료점: {context['end']}
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
- 단순 통계 나열을 피하고, 출발지에서 목적지로 향하는 여정처럼 생동감 있게 묘사하세요.
- 전체를 다음 3가지 섹션으로 나누어 작성하세요:
  1) 코스 요약: 전체적인 코스의 성격과 주요 경유지 요약 (자연스러운 서술형)
  2) 구간별 특징: 업힐, 다운힐, 평지, 노면 상태, 주변 풍경(벚꽃, 단풍 등 POI에서 유추) 등 상세 묘사 (자연스러운 서술형)
  3) 라이딩 팁: 다음 항목들을 마크다운 리스트 형식(- )으로 작성하세요.
     - 보급 및 편의시설: (식당, 편의점, 카페 등 주변 POI 기반)
     - 주차 및 화장실: (출발지/경유지 주차장 및 화장실 정보)
     - 주의 및 위험구간: (차량 통행량, 노면 불량, 급경사 등 주의사항)
- 주변 POI(특히 편의점, 화장실, 주차장, 명소)를 자연스럽게 언급하세요.
- 과장하지 말고 데이터 기반으로 정확하게 작성하되, 실제 라이더가 작성한 꿀팁 리뷰처럼 상세하게 작성하세요.

## 응답 형식 (JSON만, 다른 텍스트 없이)
```json
{{
  "tags": ["태그1", "태그2", ...],
  "description": "코스 설명 텍스트"
}}
```"""


def _get_waypoints_along_route(conn, route_line_wkt: str, radius_m: int = 500) -> list[dict]:
    """경로 선(LineString)을 따라 radius_m 이내의 waypoints 검색."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, type::text[], description,
               ST_Distance(
                   location::geography,
                   ST_GeomFromText(%s, 4326)::geography
               ) as distance_m
        FROM waypoints
        WHERE ST_DWithin(
            location::geography,
            ST_GeomFromText(%s, 4326)::geography,
            %s
        )
        ORDER BY distance_m
    """, (route_line_wkt, route_line_wkt, radius_m))
    rows = cur.fetchall()
    cur.close()
    return [
        {"id": r["id"], "name": r["name"], "type": r["type"],
         "description": r["description"], "distance_m": round(r["distance_m"]),
         "priority": "route"}
        for r in rows
    ]


def _get_waypoints_near_control_points(conn, control_points: list[dict], radius_m: int = 200) -> list[dict]:
    """사용자가 직접 찍은 포인트(control points) 인근 waypoints 검색. 우선순위 높음."""
    if not control_points:
        return []

    results = []
    seen_ids = set()
    cur = conn.cursor()

    for cp in control_points:
        lat, lon = cp["lat"], cp["lon"]
        cur.execute("""
            SELECT id, name, type::text[], description,
                   ST_Distance(
                       location::geography,
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                   ) as distance_m
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

    POI 검색 전략:
    1. 경로 선(LineString)을 따라 500m 이내 waypoints
    2. 사용자 지정 control points 인근 200m waypoints (우선순위 높음)
    3. 합쳐서 중복 제거, control_point 우선 정렬

    Returns:
        {"tags": ["태그1", ...], "description": "코스 설명"}
    """
    lats = full_data.get("points", {}).get("lat", [])
    if not lats:
        return {"tags": [], "description": ""}

    # 1. 경로 선 따라 POI 검색 (500m)
    route_wkt = _build_route_line_wkt(full_data)
    route_pois = _get_waypoints_along_route(conn, route_wkt, radius_m=500) if route_wkt else []

    # 2. Control points 인근 POI 검색 (200m, 우선순위 높음)
    control_points = _extract_control_points(full_data)
    cp_pois = _get_waypoints_near_control_points(conn, control_points, radius_m=200)

    # 3. 합치기: control_point 우선, 중복 제거
    seen_ids = set()
    merged = []
    for wp in cp_pois:
        seen_ids.add(wp["id"])
        merged.append(wp)
    for wp in route_pois:
        if wp["id"] not in seen_ids:
            seen_ids.add(wp["id"])
            merged.append(wp)

    existing_tags = get_existing_tags(conn)
    context = _extract_route_context(full_data, merged)
    prompt = _build_prompt(context, existing_tags)

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
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
        return {"tags": tags, "description": description}
    except (json.JSONDecodeError, AttributeError):
        return {"tags": [], "description": ""}
