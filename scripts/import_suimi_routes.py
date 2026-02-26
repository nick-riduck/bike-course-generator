#!/usr/bin/env python3
"""
Import Suimi GPX Routes to PostgreSQL  [Step 1/2: 로컬 처리]
=============================================================
suimi_gpx/ 폴더 내 GPX 파일들을 파싱하여:
  1. Riduck v1.0 JSON 파일 → backend/storage/routes/{uuid}.json
  2. PostgreSQL INSERT SQL → scripts/output/import_suimi_YYYYMMDD.sql

data_file_path 는 항상 "routes/{uuid}.json" 포맷.
  로컬: backend STORAGE_TYPE=LOCAL  → backend/storage/routes/{uuid}.json
  운영: backend STORAGE_TYPE=GCS    → GCS bucket의 routes/{uuid}.json

== 처리 경로 ==
[기본] Valhalla 경로 (/api/routes/import 와 동일):
  GpxLoader.load() → get_standard_course() → surf + DEM고도 + grade + segments

[폴백] --no-valhalla:
  GPS 고도 스무딩, surf=0(unknown), 빠른 테스트용

== 운영 배포는 scripts/deploy_production.py 참조 ==
  Step 2: JSON → GCS 업로드 + 운영 DB SQL 실행

== Usage ==
  python scripts/import_suimi_routes.py                       # Valhalla 사용
  python scripts/import_suimi_routes.py --no-valhalla         # 폴백
  python scripts/import_suimi_routes.py --no-valhalla --limit 5  # 테스트
"""

from __future__ import annotations

import sys
import os
import re
import json
import uuid
import math
import argparse
from pathlib import Path
from datetime import date
from typing import List, Dict, Any, Optional, Tuple

# ============================================================
# Backend 모듈 경로 추가
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from gpx_loader import GpxLoader, TrackPoint  # noqa: E402

# ============================================================
# 경로 / 상수
# ============================================================
SUIMI_GPX_DIR  = PROJECT_ROOT / "suimi_gpx"
LOCAL_JSON_DIR = PROJECT_ROOT / "backend" / "storage" / "routes"
SQL_OUTPUT_DIR = Path(__file__).parent / "output"

ADMIN_EMAIL = "nick@riduck.com"

# summary_path LINESTRING 최대 포인트 수 (공간 쿼리용)
SUMMARY_MAX_POINTS = 200

# no-valhalla 폴백용 세그먼트 상수 (valhalla.py 동일)
_GRADE_THRESH   = 0.005   # 0.5%
_HEADING_THRESH = 10.0    # deg
_MAX_SEG_LEN    = 200.0   # m

# ============================================================
# 수학 유틸리티 (no-valhalla 폴백용, valhalla.py에서 포팅)
# ============================================================

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _smooth_elevation(data: List[float], window: int = 11) -> List[float]:
    """이동 평균 스무딩 (valhalla._smooth_elevation 동일)."""
    if not data or len(data) < window:
        return data
    pad    = window // 2
    padded = [data[0]] * pad + data + [data[-1]] * pad
    return [sum(padded[i:i + window]) / window for i in range(len(data))]


# ============================================================
# No-Valhalla 폴백 처리
# ============================================================

def _build_fallback_points(
    track_points: List[TrackPoint],
) -> Tuple[List[List[float]], float, float]:
    """
    TrackPoint → (enriched_pts, ascent_m, descent_m)

    포인트 포맷: [lat, lon, ele, cum_dist, grade, surf_id]
    surf_id = 0 (unknown) 고정 — 노면 정보는 Valhalla 없이 취득 불가.

    ascent/descent:
      valhalla._filter_outliers_post_resample 은 10m 리샘플 후 포인트에 적용하는 로직.
      raw GPX 포인트(1~5m 간격)에 적용하면 GPS 고도 노이즈(±5m)가 20%+ grade로
      잡혀 모든 고도 변화가 평탄화(ascent=0)되는 부작용이 발생.
      → ascent/descent 는 grade 필터 이전 스무딩 배열에서 직접 계산.
    """
    if not track_points:
        return [], 0.0, 0.0

    eles = _smooth_elevation([p.ele for p in track_points], window=11)

    # ascent/descent: 스무딩 후, grade 필터 전
    ascent = descent = 0.0
    for i in range(1, len(eles)):
        diff = eles[i] - eles[i - 1]
        if diff > 0:
            ascent  += diff
        else:
            descent += abs(diff)

    # enriched 포인트
    pts: List[List[float]] = [
        [tp.lat, tp.lon, eles[i], tp.distance_from_start, 0.0, 0]
        for i, tp in enumerate(track_points)
    ]

    # grade 계산
    for i in range(1, len(pts)):
        d = pts[i][3] - pts[i - 1][3]
        if d > 0:
            pts[i][4] = (pts[i][2] - pts[i - 1][2]) / d

    # grade 이상치 보정 (grade 배열 전용, ascent 계산에 무관)
    pts = _filter_outlier_grades(pts, max_grade=0.20)

    return pts, round(ascent), round(descent)


def _filter_outlier_grades(pts: List[List[float]], max_grade: float = 0.20) -> List[List[float]]:
    """valhalla._filter_outliers_post_resample 동일 로직."""
    count = len(pts)
    pts   = [list(p) for p in pts]
    for _ in range(2):
        i = 1
        while i < count:
            d = pts[i][3] - pts[i - 1][3]
            if d < 1.0:
                i += 1
                continue
            if abs((pts[i][2] - pts[i - 1][2]) / d) > max_grade:
                s, e    = max(0, i - 3), min(count - 1, i + 3)
                h_diff  = pts[e][2] - pts[s][2]
                total_d = pts[e][3] - pts[s][3]
                if total_d > 0:
                    for k in range(s + 1, e + 1):
                        frac      = (pts[k][3] - pts[s][3]) / total_d
                        pts[k][2] = pts[s][2] + h_diff * frac
                        if k > 0:
                            dk = pts[k][3] - pts[k - 1][3]
                            if dk > 0:
                                pts[k][4] = (pts[k][2] - pts[k - 1][2]) / dk
                i = e + 1
            else:
                pts[i][4] = (pts[i][2] - pts[i - 1][2]) / d
                i += 1
    return pts


def _generate_segments(pts: List[List[float]]) -> Dict[str, List[Any]]:
    """valhalla._generate_segments 동일 로직."""
    segs: Dict[str, List[Any]] = {
        "p_start": [], "p_end": [], "length": [],
        "avg_grade": [], "surf_id": [], "avg_head": []
    }
    if len(pts) < 2:
        return segs

    start_idx = 0
    ref_surf  = pts[0][5]
    ref_grade = pts[0][4]
    ref_head  = _bearing(pts[0][0], pts[0][1], pts[1][0], pts[1][1])

    for i in range(1, len(pts)):
        curr    = pts[i]
        start_p = pts[start_idx]
        seg_len = curr[3] - start_p[3]
        if seg_len < 1.0:
            continue

        curr_head = _bearing(pts[i - 1][0], pts[i - 1][1], curr[0], curr[1])
        head_diff = abs(curr_head - ref_head)
        if head_diff > 180:
            head_diff = 360 - head_diff

        is_last = (i == len(pts) - 1)
        if (
            curr[5] != ref_surf
            or abs(curr[4] - ref_grade) > _GRADE_THRESH
            or head_diff > _HEADING_THRESH
            or seg_len >= _MAX_SEG_LEN
            or is_last
        ):
            segs["p_start"].append(start_idx)
            segs["p_end"].append(i)
            segs["length"].append(round(seg_len, 2))
            segs["avg_grade"].append(
                round((curr[2] - start_p[2]) / seg_len if seg_len > 0 else 0, 5)
            )
            segs["surf_id"].append(ref_surf)
            segs["avg_head"].append(round(ref_head, 1))

            start_idx = i
            ref_surf  = curr[5]
            ref_grade = curr[4]
            if not is_last:
                ref_head = _bearing(curr[0], curr[1], pts[i + 1][0], pts[i + 1][1])

    return segs


def _build_fallback_json(
    pts: List[List[float]],
    segs: Dict,
    ascent_m: float,
    descent_m: float,
) -> Dict:
    """No-Valhalla 폴백용 v1.0 JSON 생성."""
    return {
        "version": "1.0",
        "meta": {
            "creator": "Riduck Suimi Importer (no-valhalla)",
            "surface_map": {
                "0": "unknown",    "1": "asphalt",       "2": "concrete",
                "3": "wood_metal", "4": "paving_stones",  "5": "cycleway",
                "6": "compacted",  "7": "gravel_dirt"
            },
            "note": "surf=0 고정. 노면 정보는 Valhalla 없이 취득 불가."
        },
        "stats": {
            "distance":       round(pts[-1][3], 1) if pts else 0.0,
            "ascent":         ascent_m,
            "descent":        descent_m,
            "points_count":   len(pts),
            "segments_count": len(segs.get("p_start", [])),
        },
        "points": {
            "lat":   [round(p[0], 7) for p in pts],
            "lon":   [round(p[1], 7) for p in pts],
            "ele":   [round(p[2], 1) for p in pts],
            "dist":  [round(p[3], 1) for p in pts],
            "grade": [round(p[4], 5) for p in pts],
            "surf":  [0 for _ in pts],
        },
        "segments":      segs,
        "editor_state":  None,
        "control_points": [],
    }


# ============================================================
# PostGIS WKT
# ============================================================

def _linestring_wkt(lats: List[float], lons: List[float], max_pts: int = SUMMARY_MAX_POINTS) -> str:
    """summary_path 용 WKT. WKT 좌표 순서: lon lat."""
    n = len(lats)
    if n > max_pts:
        step    = n / max_pts
        indices = [int(i * step) for i in range(max_pts)]
        indices[-1] = n - 1
        lats = [lats[i] for i in indices]
        lons = [lons[i] for i in indices]
    coords = ", ".join(f"{lon:.6f} {lat:.6f}" for lat, lon in zip(lats, lons))
    return f"LINESTRING({coords})"


def _point_wkt(lat: float, lon: float) -> str:
    """start_point 용 WKT. WKT 좌표 순서: lon lat."""
    return f"POINT({lon:.6f} {lat:.6f})"


# ============================================================
# route_info_gemini_api.md 파싱
# ============================================================

def _parse_route_info(md_path: Path) -> Dict[str, Any]:
    if not md_path.exists():
        return {"title": md_path.parent.name, "description": "",
                "tags": [], "status": "PUBLIC", "is_verified": False}

    text = md_path.read_text(encoding="utf-8")

    # Title: ## Database Info > **Title** 우선, 없으면 # 헤더
    m = re.search(r'\*\*Title\*\*:\s*(.+)', text)
    title = m.group(1).strip() if m else (
        re.search(r'^#\s+(.+)$', text, re.MULTILINE).group(1).strip()
        if re.search(r'^#\s+(.+)$', text, re.MULTILINE) else md_path.parent.name
    )

    # Description (+ Supplies 섹션 병합)
    dm = re.search(r'##\s+Description\s*\n(.*?)(?=\n##|\n---|\Z)', text, re.DOTALL)
    description = dm.group(1).strip() if dm else ""
    sm = re.search(r'##\s+Supplies[^\n]*\n(.*?)(?=\n##|\n---|\Z)', text, re.DOTALL)
    if sm and sm.group(1).strip():
        description = (description + "\n\n" + sm.group(1).strip()).strip()

    # Tags: **Tags**: #태그1 #태그2
    tm = re.search(r'\*\*Tags\*\*:\s*(.+)', text)
    tags = [t.lstrip('#').strip() for t in re.findall(r'#[\w가-힣]+', tm.group(1))] if tm else []

    # Status
    stm = re.search(r'\*\*Status\*\*:\s*(\w+)', text)
    status = stm.group(1).strip().upper() if stm else "PUBLIC"
    if status not in ("PUBLIC", "PRIVATE", "LINK_ONLY"):
        status = "PUBLIC"

    # Is Verified
    vm = re.search(r'\*\*Is Verified\*\*:\s*(\w+)', text)
    is_verified = vm.group(1).strip().upper() == "TRUE" if vm else False

    return {"title": title, "description": description,
            "tags": tags, "status": status, "is_verified": is_verified}


# ============================================================
# SQL 유틸리티
# ============================================================

def _esc(s: str) -> str:
    return s.replace("'", "''")

def _slug(tag: str) -> str:
    return tag.strip().lower()


# ============================================================
# JSON 파일 저장 & GCS 업로드
# ============================================================

def _save_json(route_json: Dict, route_uuid: str) -> Path:
    LOCAL_JSON_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_JSON_DIR / f"{route_uuid}.json"
    path.write_text(json.dumps(route_json, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


# ============================================================
# 핵심 GPX 처리 파이프라인
# ============================================================

def _process_gpx(
    gpx_path:        Path,
    route_info:      Dict[str, Any],
    is_multi:        bool,
    valhalla_client: Any,   # ValhallaClient | None
) -> Optional[Dict[str, Any]]:
    """GPX 파일 1개 처리 → 라우트 메타데이터 dict 반환. 실패 시 None."""
    print(f"  [{gpx_path.name}]", end=" ", flush=True)

    # 1. GPX 파싱 (기존 GpxLoader 재사용)
    try:
        loader = GpxLoader(str(gpx_path))
        loader.load()
    except Exception as e:
        print(f"ERROR (GPX 파싱): {e}")
        return None

    if len(loader.points) < 2:
        print(f"SKIP (포인트 {len(loader.points)}개)")
        return None

    # 2. 포인트 처리 ─ Valhalla 경로 vs 폴백
    route_json: Dict
    lats: List[float]
    lons: List[float]
    distance_m: int
    ascent_m: int

    if valhalla_client is not None:
        # ── Valhalla 경로 (/api/routes/import 와 동일) ──────────────────
        shape_points = [{"lat": p.lat, "lon": p.lon} for p in loader.points]
        try:
            standard_data = valhalla_client.get_standard_course(shape_points)
        except Exception as e:
            print(f"ERROR (Valhalla): {e}")
            return None

        # get_standard_course() 결과가 곧 v1.0 JSON (surf, DEM고도, grade 모두 포함)
        standard_data.setdefault("editor_state", None)
        standard_data.setdefault("control_points", [])
        route_json  = standard_data
        lats        = standard_data["points"]["lat"]
        lons        = standard_data["points"]["lon"]
        stats       = standard_data["stats"]
        distance_m  = int(stats["distance"])
        ascent_m    = int(stats["ascent"])
        mode_label  = "valhalla"

    else:
        # ── No-Valhalla 폴백 ─────────────────────────────────────────────
        pts, asc, desc = _build_fallback_points(loader.points)
        if len(pts) < 2:
            print("SKIP (폴백 처리 후 포인트 부족)")
            return None
        segs        = _generate_segments(pts)
        route_json  = _build_fallback_json(pts, segs, asc, desc)
        lats        = [p[0] for p in pts]
        lons        = [p[1] for p in pts]
        distance_m  = int(route_json["stats"]["distance"])
        ascent_m    = asc
        mode_label  = "no-valhalla(surf=0)"

    # 3. JSON 저장
    route_uuid     = str(uuid.uuid4())
    local_json_path = _save_json(route_json, route_uuid)

    data_file_path = f"routes/{route_uuid}.json"

    # 5. 제목 결정 (멀티 GPX 폴더는 파일명으로 구분)
    title = gpx_path.stem if is_multi else route_info.get("title", gpx_path.parent.name)

    n_pts  = len(lats)
    n_segs = len(route_json.get("segments", {}).get("p_start", []))
    print(
        f"OK [{mode_label}] "
        f"dist={distance_m}m ascent={ascent_m}m pts={n_pts} segs={n_segs}"
    )

    return {
        "uuid":             route_uuid,
        "title":            title,
        "description":      route_info.get("description", ""),
        "status":           route_info.get("status", "PUBLIC"),
        "is_verified":      route_info.get("is_verified", False),
        "data_file_path":   data_file_path,
        "summary_path_wkt": _linestring_wkt(lats, lons),
        "start_point_wkt":  _point_wkt(lats[0], lons[0]),
        "distance_m":       distance_m,
        "elevation_gain_m": ascent_m,
        "tags":             route_info.get("tags", []),
    }


# ============================================================
# SQL 생성
# ============================================================

def _generate_sql(
    routes:        List[Dict[str, Any]],
    all_tags:      Dict[str, str],
    output_path:   Path,
    used_valhalla: bool,
) -> None:
    lines: List[str] = []

    lines += [
        "-- ================================================================",
        "-- Suimi GPX Route Import Script  [Step 1/2: 로컬 처리 결과]",
        f"-- Generated  : {date.today().isoformat()}",
        f"-- Valhalla   : {'yes (surf/DEM 포함)' if used_valhalla else 'no (surf=0, GPS 고도)'}",
        f"-- Routes     : {len(routes)}",
        f"-- Tags       : {len(all_tags)}",
        f"-- Admin      : {ADMIN_EMAIL}",
        "-- ================================================================",
        "--",
        "-- [로컬 실행]",
        "--   psql -h localhost -U USER -d DB -f this_file.sql",
        "--",
        "-- [운영 배포] scripts/deploy_production.py 참조",
        "--   Step 1: JSON → GCS 업로드",
        "--   Step 2: SQL → 운영 VM psql 실행",
        "--",
        "-- 전제 조건:",
        "--   1. CREATE EXTENSION IF NOT EXISTS postgis;",
        f"--   2. users 테이블에 email='{ADMIN_EMAIL}' 계정 존재",
        "--   3. routes / route_stats / tags / route_tags 테이블 생성 완료",
        "--",
    ]

    lines += ["", "BEGIN;", ""]

    # 관리자 계정 확인
    lines += [
        "DO $$",
        "BEGIN",
        f"  IF NOT EXISTS (SELECT 1 FROM users WHERE email = '{ADMIN_EMAIL}') THEN",
        f"    RAISE EXCEPTION 'User {ADMIN_EMAIL} not found.';",
        "  END IF;",
        "END $$;",
        "",
    ]

    # Tags
    if all_tags:
        lines += [
            "-- ================================================================",
            "-- Tags  (slug 기준, 중복 무시)",
            "-- ================================================================",
        ]
        for slug, name in sorted(all_tags.items()):
            lines.append(
                f"INSERT INTO tags (names, slug, type) "
                f"VALUES ('{{\"ko\": \"{_esc(name)}\"}}'::jsonb, '{_esc(slug)}', 'GENERAL') "
                f"ON CONFLICT (slug) DO NOTHING;"
            )
        lines.append("")

    # Routes
    lines += [
        "-- ================================================================",
        "-- Routes  (uuid 기준, 중복 무시)",
        "-- ================================================================",
        "",
    ]

    for r in routes:
        slp = _esc(r["summary_path_wkt"])
        stp = _esc(r["start_point_wkt"])

        lines += [
            f"-- {r['title']}",
            "INSERT INTO routes",
            "  (uuid, user_id, title, description, status, is_verified,",
            "   data_file_path, summary_path, start_point, distance, elevation_gain)",
            "SELECT",
            f"  '{r['uuid']}',",
            f"  id,",
            f"  '{_esc(r['title'])}',",
            f"  '{_esc(r['description'])}',",
            f"  '{r['status']}',",
            f"  {'TRUE' if r['is_verified'] else 'FALSE'},",
            f"  '{_esc(r['data_file_path'])}',",
            f"  ST_GeomFromText('{slp}', 4326),",
            f"  ST_GeomFromText('{stp}', 4326),",
            f"  {r['distance_m']},",
            f"  {r['elevation_gain_m']}",
            f"FROM users WHERE email = '{ADMIN_EMAIL}'",
            "ON CONFLICT (uuid) DO NOTHING;",
            "",
            f"INSERT INTO route_stats (route_id)",
            f"SELECT id FROM routes WHERE uuid = '{r['uuid']}'",
            "ON CONFLICT (route_id) DO NOTHING;",
            "",
        ]

        if r["tags"]:
            slugs = ", ".join(f"'{_esc(_slug(t))}'" for t in r["tags"])
            lines += [
                "INSERT INTO route_tags (route_id, tag_id)",
                "SELECT r.id, t.id FROM routes r CROSS JOIN tags t",
                f"WHERE  r.uuid = '{r['uuid']}' AND t.slug IN ({slugs})",
                "ON CONFLICT DO NOTHING;",
                "",
            ]

    lines += ["COMMIT;", ""]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSQL 저장: {output_path}")


# ============================================================
# 메인
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="suimi_gpx/ → Riduck v1.0 JSON + PostgreSQL SQL 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--valhalla-url", default="http://localhost:8002",
                        help="Valhalla 서버 URL (기본: http://localhost:8002)")
    parser.add_argument("--no-valhalla", action="store_true",
                        help="Valhalla 없이 GPS 고도만 사용 (surf=0, 빠른 테스트용)")
    parser.add_argument("--limit", type=int, default=0,
                        help="처리할 폴더 수 제한 (0=전체)")
    args = parser.parse_args()

    if not SUIMI_GPX_DIR.exists():
        print(f"ERROR: {SUIMI_GPX_DIR} 없음"); sys.exit(1)

    # Valhalla 클라이언트 초기화
    valhalla_client = None
    if not args.no_valhalla:
        try:
            from valhalla import ValhallaClient  # noqa: E402
            valhalla_client = ValhallaClient(url=args.valhalla_url)
            print(f"Valhalla: {args.valhalla_url}")
        except Exception as e:
            print(f"Valhalla 로드 실패: {e}")
            print("Valhalla 없이 진행하려면 --no-valhalla 플래그를 사용하세요.")
            sys.exit(1)
    else:
        print("모드: no-valhalla (surf=0, GPS 고도)")

    folders = sorted(d for d in SUIMI_GPX_DIR.iterdir() if d.is_dir())
    if args.limit:
        folders = folders[:args.limit]

    print(f"처리 폴더: {len(folders)}개")
    print(f"JSON 저장: {LOCAL_JSON_DIR}")
    print()

    all_routes: List[Dict[str, Any]] = []
    all_tags:   Dict[str, str]       = {}
    errors:     List[str]            = []

    for folder in folders:
        info_path = folder / "route_info_gemini_api.md"
        if not info_path.exists():
            info_path = folder / "route_info.md"
        route_info = _parse_route_info(info_path)

        gpx_files = sorted(folder.glob("*.gpx"))
        if not gpx_files:
            print(f"[SKIP] {folder.name}  (GPX 없음)")
            continue

        is_multi = len(gpx_files) > 1
        print(f"[{folder.name}]  ({len(gpx_files)}개)")

        for gpx_path in gpx_files:
            result = _process_gpx(
                gpx_path        = gpx_path,
                route_info      = route_info,
                is_multi        = is_multi,
                valhalla_client = valhalla_client,
            )
            if result is None:
                errors.append(str(gpx_path.relative_to(PROJECT_ROOT)))
                continue

            for tag in result["tags"]:
                all_tags[_slug(tag)] = tag
            all_routes.append(result)

    # SQL 생성
    sql_name = f"import_suimi_{date.today().strftime('%Y%m%d')}.sql"
    _generate_sql(
        routes        = all_routes,
        all_tags      = all_tags,
        output_path   = SQL_OUTPUT_DIR / sql_name,
        used_valhalla = valhalla_client is not None,
    )

    print()
    print("=" * 60)
    print(f"완료!")
    print(f"  성공   : {len(all_routes)}개 루트")
    print(f"  태그   : {len(all_tags)}개")
    print(f"  JSON   : {LOCAL_JSON_DIR}")
    print(f"  SQL    : {SQL_OUTPUT_DIR / sql_name}")
    if errors:
        print(f"  실패 ({len(errors)}개):")
        for e in errors:
            print(f"    - {e}")
    print("=" * 60)


if __name__ == "__main__":
    main()
