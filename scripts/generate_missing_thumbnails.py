#!/usr/bin/env python3
"""
Backfill thumbnails for routes that have NULL thumbnail_url.

Routes imported via import_suimi_routes.py don't have thumbnails.
This script:
  1. Queries all routes with NULL thumbnail_url
  2. Loads each route's JSON from backend/storage/routes/{uuid}.json
  3. Generates a thumbnail using PIL
  4. Saves to backend/storage/thumbnails/{uuid}.png
  5. Updates routes.thumbnail_url in the DB

Usage:
  python scripts/generate_missing_thumbnails.py
  python scripts/generate_missing_thumbnails.py --limit 10   # test run
  python scripts/generate_missing_thumbnails.py --dry-run    # no DB update
"""

from __future__ import annotations

import sys
import os
import json
import argparse
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    print("ERROR: Pillow not installed. pip install Pillow")
    sys.exit(1)

LOCAL_ROUTES_DIR    = PROJECT_ROOT / "backend" / "storage" / "routes"
LOCAL_THUMBNAIL_DIR = PROJECT_ROOT / "backend" / "storage" / "thumbnails"

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "127.0.0.1"),
    "port":     os.getenv("DB_PORT", "5432"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "dbname":   os.getenv("DB_NAME", "postgres"),
}


def extract_latlons(data: dict) -> tuple[List[float], List[float]]:
    """JSON 데이터에서 (lats, lons) 추출. v1.0 및 editor_state 포맷 모두 지원."""
    # v1.0 columnar format
    if "points" in data and isinstance(data["points"].get("lat"), list):
        return data["points"]["lat"], data["points"]["lon"]

    # editor_state format
    if "editor_state" in data and data["editor_state"]:
        lats, lons = [], []
        for sec in data["editor_state"].get("sections", []):
            for seg in sec.get("segments", []):
                for coord in seg.get("geometry", {}).get("coordinates", []):
                    lons.append(coord[0])
                    lats.append(coord[1])
        if lats:
            return lats, lons

    return [], []


def generate_thumbnail(lats: List[float], lons: List[float], route_uuid: str) -> Optional[str]:
    """PIL 썸네일 생성 → backend/storage/thumbnails/{uuid}.png 저장 → URL 반환."""
    if len(lats) < 2:
        return None
    try:
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        step = max(1, len(lats) // 500)
        s_lats = lats[::step]
        s_lons = lons[::step]
        if s_lats[-1] != lats[-1]:
            s_lats.append(lats[-1])
            s_lons.append(lons[-1])

        W, H, padding = 600, 240, 40
        img = Image.new('RGB', (W, H), color='#111827')
        draw = ImageDraw.Draw(img)

        lat_range = max(max_lat - min_lat, 0.0001)
        lon_range = max(max_lon - min_lon, 0.0001)
        scale = min((W - 2 * padding) / lon_range, (H - 2 * padding) / lat_range)
        off_x = (W - lon_range * scale) / 2
        off_y = (H - lat_range * scale) / 2

        pts = [(off_x + (lon - min_lon) * scale,
                off_y + (max_lat - lat) * scale)
               for lat, lon in zip(s_lats, s_lons)]

        draw.line(pts, fill='#2a9e92', width=5, joint='curve')
        r = 5
        draw.ellipse((pts[0][0]-r,  pts[0][1]-r,  pts[0][0]+r,  pts[0][1]+r),  fill='#10B981', outline='white', width=1)
        draw.ellipse((pts[-1][0]-r, pts[-1][1]-r, pts[-1][0]+r, pts[-1][1]+r), fill='#EF4444', outline='white', width=1)

        LOCAL_THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        img.save(str(LOCAL_THUMBNAIL_DIR / f"{route_uuid}.png"), format='PNG')
        return f"/api/thumbnails/{route_uuid}.png"
    except Exception as e:
        print(f"  [WARN] PIL error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Backfill missing thumbnails")
    parser.add_argument("--limit",   type=int, default=0,     help="Process at most N routes (0 = all)")
    parser.add_argument("--dry-run", action="store_true",      help="Generate thumbnails but skip DB update")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur  = conn.cursor()

    query = "SELECT id, uuid, title FROM routes WHERE thumbnail_url IS NULL AND status != 'DELETED' ORDER BY id"
    if args.limit:
        query += f" LIMIT {args.limit}"
    cur.execute(query)
    rows = cur.fetchall()

    print(f"Found {len(rows)} routes without thumbnails")
    ok = skip = fail = 0

    for row in rows:
        route_id   = row['id']
        route_uuid = row['uuid']
        title      = row['title']

        json_path = LOCAL_ROUTES_DIR / f"{route_uuid}.json"
        if not json_path.exists():
            print(f"  [{route_id}] SKIP — JSON not found: {json_path.name}")
            skip += 1
            continue

        try:
            data = json.loads(json_path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"  [{route_id}] SKIP — JSON parse error: {e}")
            skip += 1
            continue

        lats, lons = extract_latlons(data)
        if not lats:
            print(f"  [{route_id}] SKIP — no coordinates found ({title[:40]})")
            skip += 1
            continue

        thumb_url = generate_thumbnail(lats, lons, route_uuid)
        if not thumb_url:
            print(f"  [{route_id}] FAIL — thumbnail generation error ({title[:40]})")
            fail += 1
            continue

        if not args.dry_run:
            cur.execute(
                "UPDATE routes SET thumbnail_url = %s WHERE id = %s",
                (thumb_url, route_id)
            )
            conn.commit()

        print(f"  [{route_id}] OK — {title[:50]}")
        ok += 1

    conn.close()
    print(f"\nDone: {ok} generated, {skip} skipped, {fail} failed")
    if args.dry_run:
        print("(dry-run: DB not updated)")


if __name__ == "__main__":
    main()
