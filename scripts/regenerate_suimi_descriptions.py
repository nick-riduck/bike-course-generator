#!/usr/bin/env python3
"""
Suimi 코스 265개 description 재생성 스크립트

원본 description을 살리면서 우리 포맷(중요정보→상세→출처)으로 재구성.
- 원본 description (route_info_gemini_api.md)
- 주변 웨이포인트 검색 (auto_tag_service 로직)
- 코스 통계 (JSON 데이터)
- 출처 링크 (Source/Youtube)

Usage:
    python scripts/regenerate_suimi_descriptions.py                    # 전체 실행
    python scripts/regenerate_suimi_descriptions.py --limit 5          # 5개만 테스트
    python scripts/regenerate_suimi_descriptions.py --workers 20       # 20 스레드
    python scripts/regenerate_suimi_descriptions.py --reset            # 처음부터 다시
    python scripts/regenerate_suimi_descriptions.py --dry-run          # DB 반영 없이 결과만 확인
"""

import os
import sys
import json
import re
import time
import argparse
import signal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

# Backend 모듈 경로
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from google import genai
from google.genai import types

# --- Config ---
SUIMI_DIR = PROJECT_ROOT / "suimi_gpx"
STORAGE_DIR = PROJECT_ROOT / "backend" / "storage" / "routes"
PROGRESS_FILE = PROJECT_ROOT / "scripts" / "output" / "regen_descriptions_progress.jsonl"

MODEL = "gemini-3.1-pro-preview"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 90  # pro는 좀 더 여유

DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "password",
    "dbname": "postgres",
}

# Graceful shutdown
_shutdown = False
def _signal_handler(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n⚠️  종료 요청 수신. 현재 작업 완료 후 안전하게 종료합니다...")

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ============================================================
# route_info_gemini_api.md 파싱
# ============================================================

def parse_route_info_md(md_path: Path) -> dict:
    """route_info_gemini_api.md에서 원본 description, source, youtube 추출."""
    if not md_path.exists():
        return {"description": "", "supplies": "", "source": "", "youtube": "", "tags": []}

    text = md_path.read_text(encoding="utf-8")

    # Description
    dm = re.search(r'##\s+Description\s*\n(.*?)(?=\n##|\n---|\Z)', text, re.DOTALL)
    description = dm.group(1).strip() if dm else ""

    # Supplies & Amenities
    sm = re.search(r'##\s+Supplies[^\n]*\n(.*?)(?=\n##|\n---|\Z)', text, re.DOTALL)
    supplies = sm.group(1).strip() if sm else ""

    # Source URL
    src = re.search(r'\*\*Source\*\*:\s*\[([^\]]+)\]', text)
    source = src.group(1).strip() if src else ""

    # Youtube URL
    yt = re.search(r'\*\*Youtube\*\*:\s*\[([^\]]+)\]', text)
    youtube = yt.group(1).strip() if yt else ""

    # Tags
    tm = re.search(r'\*\*Tags\*\*:\s*(.+)', text)
    tags = [t.lstrip('#').strip() for t in re.findall(r'#[\w가-힣]+', tm.group(1))] if tm else []

    return {
        "description": description,
        "supplies": supplies,
        "source": source,
        "youtube": youtube,
        "tags": tags,
    }


# ============================================================
# DB에서 route 정보 + 웨이포인트 검색
# ============================================================

def get_db_connection():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def get_suimi_routes(conn) -> list[dict]:
    """DB에서 suimi 코스 목록 조회 (title + uuid + data_file_path)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, uuid, title, data_file_path, description,
               distance, elevation_gain
        FROM routes
        WHERE user_id = 100000000
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]


def get_waypoints_along_route(conn, route_line_wkt: str, radius_m: int = 500) -> list[dict]:
    """경로 선을 따라 웨이포인트 검색."""
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
        {"name": r["name"], "type": r["type"], "description": r["description"],
         "distance_m": round(r["distance_m"]),
         "dist_from_start_m": round(r["dist_from_start_m"]) if r["dist_from_start_m"] else 0}
        for r in rows
    ]


def build_route_line_wkt(full_data: dict) -> str | None:
    """JSON 데이터에서 LineString WKT 생성."""
    lats = full_data.get("points", {}).get("lat", [])
    lons = full_data.get("points", {}).get("lon", [])
    if len(lats) < 2:
        return None
    step = max(1, len(lats) // 200)
    coords = []
    for i in range(0, len(lats), step):
        coords.append(f"{lons[i]} {lats[i]}")
    if (len(lats) - 1) % step != 0:
        coords.append(f"{lons[-1]} {lats[-1]}")
    return f"LINESTRING({', '.join(coords)})"


# ============================================================
# Gemini 프롬프트
# ============================================================

REGEN_PROMPT = """당신은 자전거 코스 분석 전문가입니다.
기존 코스 설명을 우리 서비스 포맷에 맞게 재구성해주세요.

## 원본 코스 설명
{original_description}

## 원본 보급/편의 정보
{original_supplies}

## 코스 통계
- 거리: {distance_km}km
- 획득고도: {elevation_gain}m
- 코스 형태: {course_type}

## 경로 주변 웨이포인트 (DB 검색 결과)
{waypoints_text}

## 작성 규칙

마크다운 형식으로 아래 순서대로 작성하세요.

**파트 1: 중요 정보 ("#### **중요 정보**" 헤딩)**
- 마크다운 리스트(- )로 작성
- 각 항목에 가능하면 "약 X.Xkm 지점" 위치 정보 포함
- 항목:
  - 보급 및 편의시설: 편의점, 카페, 식당 등
  - 주차 및 화장실: 출발지/경유지 인근
  - 주의 및 위험구간: 차량 통행량, 노면, 급경사 등
- 원본 보급 정보와 웨이포인트 데이터를 종합하여 작성
- 데이터에 근거한 항목만. 없으면 해당 항목 생략.

**파트 2: 상세 ("#### **상세**" 헤딩)**
- 원본 설명의 내용(고개 이름, 경유지, 코스 특징 등)을 최대한 살릴 것
- 2~4문장의 간결한 서술형
- 통계 수치 단순 나열 금지. 라이더 관점의 느낌 전달
- 원본에 있는 고유명사(고개, 마을, 도로 등)는 반드시 포함

**전체 규칙:**
- 과장 금지. 원본 + 데이터 기반으로 정확하게.
- 출처 링크는 넣지 마세요 (별도 처리)

## 응답 형식 (JSON만, 다른 텍스트 없이)
```json
{{
  "description": "재구성된 설명 (마크다운)",
  "title": "코스 제목 (20자 이내, 원본 제목 참고하되 개선)"
}}
```"""


def build_waypoints_text(waypoints: list[dict]) -> str:
    if not waypoints:
        return "(검색된 웨이포인트 없음)"

    lines = []
    for w in waypoints[:20]:
        types_str = ', '.join(w['type']) if isinstance(w['type'], list) else w['type']
        km = w['dist_from_start_m'] / 1000.0
        km_str = f"약 {km:.1f}km 지점" if km >= 0.1 else "출발 직후"
        lines.append(f"- {w['name']} ({types_str} / {km_str})")
    return "\n".join(lines)


def append_source_links(description: str, source: str, youtube: str) -> str:
    """description 끝에 출처 링크 추가."""
    links = []
    if source:
        links.append(f"- **Source**: [{source}]({source})")
    if youtube:
        links.append(f"- **Youtube**: [{youtube}]({youtube})")

    if links:
        description = description.rstrip() + "\n\n#### **출처**\n" + "\n".join(links)
    return description


# ============================================================
# Gemini 호출
# ============================================================

def regenerate_single(client, route_info: dict, waypoints: list[dict],
                      route_db: dict) -> dict:
    """단일 코스 description 재생성."""
    distance_km = round(route_db["distance"] / 1000, 1)
    elevation_gain = route_db["elevation_gain"]

    # 순환 여부 간단 판단
    course_type = f"{'순환형' if '순환' in route_info.get('description', '') else '편도형'}"

    prompt = REGEN_PROMPT.format(
        original_description=route_info["description"] or "(없음)",
        original_supplies=route_info["supplies"] or "(없음)",
        distance_km=distance_km,
        elevation_gain=elevation_gain,
        course_type=course_type,
        waypoints_text=build_waypoints_text(waypoints),
    )

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT * 1000),
                ),
            )
            result = json.loads(response.text)
            return result
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep((2 ** attempt) * 2)

    raise last_error


# ============================================================
# Progress 관리
# ============================================================

def load_completed(progress_file: Path) -> dict[int, dict]:
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
                route_id = item.get("route_id")
                if route_id is not None:
                    completed[route_id] = item
            except json.JSONDecodeError:
                continue
    return completed


def append_progress(result: dict, progress_file: Path):
    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


# ============================================================
# 폴더명 ↔ route 매칭
# ============================================================

def build_folder_map() -> dict[str, Path]:
    """suimi_gpx 폴더명 → 폴더 경로 매핑."""
    folder_map = {}
    for d in SUIMI_DIR.iterdir():
        if d.is_dir():
            folder_map[d.name] = d
    return folder_map


def match_route_to_folder(route_title: str, folder_map: dict[str, Path]) -> Path | None:
    """route title로 suimi_gpx 폴더 매칭."""
    # 정확히 일치
    if route_title in folder_map:
        return folder_map[route_title]

    # 폴더명이 title에 포함되거나 반대
    for fname, fpath in folder_map.items():
        if fname in route_title or route_title in fname:
            return fpath

    return None


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Suimi 코스 description 재생성")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="DB 반영 없이 결과만 확인")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "AIzaSyAZunIBnGhBa491-I9RWiaOCTq1eVQWh0I")
    client = genai.Client(api_key=api_key)

    # DB 연결
    conn = get_db_connection()
    print("DB 연결 완료")

    # suimi 코스 목록
    routes = get_suimi_routes(conn)
    print(f"suimi 코스: {len(routes)}개")

    # 폴더 매핑
    folder_map = build_folder_map()
    print(f"suimi_gpx 폴더: {len(folder_map)}개")

    # Progress
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("⚠️  Progress 초기화")

    completed = load_completed(PROGRESS_FILE)
    print(f"완료된 항목: {len(completed)}개")

    # 작업 목록 구성
    work_items = []
    unmatched = []
    for route in routes:
        if route["id"] in completed:
            continue
        folder = match_route_to_folder(route["title"], folder_map)
        if folder is None:
            unmatched.append(route["title"])
            continue

        md_path = folder / "route_info_gemini_api.md"
        if not md_path.exists():
            md_path = folder / "route_info.md"

        work_items.append({"route": route, "folder": folder, "md_path": md_path})

    if unmatched:
        print(f"⚠️  매칭 실패: {len(unmatched)}개")
        for t in unmatched[:5]:
            print(f"  - {t}")

    if args.limit > 0:
        work_items = work_items[:args.limit]

    print(f"처리 대상: {len(work_items)}개")
    print(f"모델: {MODEL} / workers: {args.workers}")
    print()

    if not work_items:
        print("처리할 항목 없음")
        conn.close()
        return

    # 사전에 웨이포인트 검색 (메인 스레드, DB 연결 공유 불가하므로)
    print("웨이포인트 검색 중...")
    for item in tqdm(work_items, desc="웨이포인트 검색"):
        route = item["route"]
        json_path = STORAGE_DIR / f"{route['uuid']}.json"
        if not json_path.exists():
            item["waypoints"] = []
            item["full_data"] = None
            continue

        with open(json_path, encoding="utf-8") as f:
            full_data = json.load(f)
        item["full_data"] = full_data

        wkt = build_route_line_wkt(full_data)
        if wkt:
            item["waypoints"] = get_waypoints_along_route(conn, wkt, radius_m=500)
        else:
            item["waypoints"] = []

    # route_info 파싱
    for item in work_items:
        item["route_info"] = parse_route_info_md(item["md_path"])

    print(f"\n웨이포인트 검색 완료. Gemini 재생성 시작...")

    # Gemini 호출 (멀티스레드)
    errors = 0
    pbar = tqdm(total=len(work_items), desc="재생성", unit="route")

    def process_item(item):
        if _shutdown:
            return None
        route = item["route"]
        route_info = item["route_info"]
        waypoints = item["waypoints"]

        try:
            result = regenerate_single(client, route_info, waypoints, route)
            description = result.get("description", "").strip()
            title = result.get("title", route["title"]).strip()

            # 출처 링크 추가
            description = append_source_links(
                description,
                route_info.get("source", ""),
                route_info.get("youtube", ""),
            )

            return {
                "route_id": route["id"],
                "uuid": str(route["uuid"]),
                "title": title,
                "original_title": route["title"],
                "description": description,
                "status": "ok",
            }
        except Exception as e:
            return {
                "route_id": route["id"],
                "uuid": str(route["uuid"]),
                "title": route["title"],
                "original_title": route["title"],
                "description": route.get("description", ""),
                "status": "error",
                "error": str(e),
            }

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_item, item): item for item in work_items}

        for future in as_completed(futures):
            if _shutdown:
                continue

            result = future.result()
            if result is None:
                continue

            append_progress(result, PROGRESS_FILE)
            completed[result["route_id"]] = result

            if result["status"] == "error":
                errors += 1
                pbar.set_postfix_str(f"ERROR: {result.get('error', '')[:30]}")
            else:
                pbar.set_postfix_str(f"{result['title'][:20]}")

            pbar.update(1)

    pbar.close()

    # DB 반영
    if not args.dry_run and not _shutdown:
        print("\nDB 반영 중...")
        cur = conn.cursor()
        updated = 0
        for rid, item in completed.items():
            if item["status"] != "ok":
                continue
            cur.execute(
                "UPDATE routes SET description = %s WHERE id = %s",
                (item["description"], rid)
            )
            updated += 1
        conn.commit()
        cur.close()
        print(f"DB 업데이트: {updated}개")
    elif args.dry_run:
        print("\n[DRY-RUN] DB 반영 생략")
        # 결과 JSON 파일로 저장
        output_path = PROJECT_ROOT / "scripts" / "output" / "regen_descriptions_preview.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        preview_data = [
            {k: v for k, v in item.items()}
            for item in completed.values()
        ]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(preview_data, f, ensure_ascii=False, indent=2)
        print(f"결과 저장: {output_path}")

    conn.close()

    # Summary
    ok_count = sum(1 for v in completed.values() if v["status"] == "ok")
    print(f"\n=== {'중단' if _shutdown else '완료'} ===")
    print(f"성공: {ok_count} / 에러: {errors} / 전체: {len(work_items)}")


if __name__ == "__main__":
    main()
