#!/usr/bin/env python3
"""
Komoot 이미지를 backend/storage/waypoints/로 복사하고 DB etc.image_urls 업데이트.

이미지 경로: waypoints/{image_id}.jpg
DB etc.image_urls: ["waypoints/12345.jpg", ...]

Usage:
    python crawl_data/refine/copy_waypoint_images.py
    python crawl_data/refine/copy_waypoint_images.py --dry-run  # 미리보기만
"""

import json
import os
import shutil
import argparse
from pathlib import Path
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "backend" / ".env")

CRAWL_DIR = Path(__file__).parent.parent / "KOMOOT_FULL"
STORAGE_DIR = Path(__file__).parent.parent.parent / "backend" / "storage" / "waypoints"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

MAX_IMAGES_PER_POI = 5


def build_image_map() -> dict[str, list[tuple[str, int]]]:
    """name → [(source_path, image_id)] 매핑 구축."""
    name_to_images = defaultdict(list)
    seen_ids = set()

    for d in sorted(os.listdir(CRAWL_DIR)):
        meta_path = CRAWL_DIR / d / "metadata.json"
        if not meta_path.exists():
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        for wp in meta.get("waypoints", []):
            name = wp.get("name", "").strip()
            if not name:
                continue
            for img in wp.get("images", []):
                img_id = img.get("id")
                if img_id and img_id not in seen_ids:
                    img_file = CRAWL_DIR / d / "images" / f"wp_{img_id}.jpg"
                    if img_file.exists():
                        name_to_images[name].append((str(img_file), img_id))
                        seen_ids.add(img_id)

    return dict(name_to_images)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("이미지 매핑 구축 중...")
    image_map = build_image_map()

    # final_pois_with_fixed_names.json에서 DB이름 → 원본이름 매핑
    final_path = Path(__file__).parent / "final_pois_with_fixed_names.json"
    if not final_path.exists():
        final_path = Path(__file__).parent / "enriched_gemini.json"
    with open(final_path, encoding="utf-8") as f:
        enriched = json.load(f)

    # DB name (final_name > name_correction > name) → original name 매핑
    db_name_to_original = {}
    for poi in enriched:
        original = poi["name"]
        db_name = poi.get("final_name") or poi.get("name_correction") or original
        db_name_to_original[db_name] = original

    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT id, name, etc FROM waypoints")
    waypoints = cur.fetchall()
    print(f"Waypoints: {len(waypoints)}개")

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    copied = 0
    updated = 0

    for wp in waypoints:
        # DB name → 원본 Komoot name으로 이미지 검색
        original_name = db_name_to_original.get(wp["name"], wp["name"])
        images = image_map.get(original_name, [])[:MAX_IMAGES_PER_POI]
        if not images:
            continue

        local_paths = []
        for src_path, img_id in images:
            dest = STORAGE_DIR / f"{img_id}.jpg"
            rel_path = f"waypoints/{img_id}.jpg"
            local_paths.append(rel_path)

            if not args.dry_run and not dest.exists():
                shutil.copy2(src_path, dest)
                copied += 1

        # DB etc 업데이트
        etc = wp["etc"] if isinstance(wp["etc"], dict) else {}
        etc["image_urls"] = local_paths

        if not args.dry_run:
            cur.execute(
                "UPDATE waypoints SET etc = %s::jsonb WHERE id = %s",
                (json.dumps(etc, ensure_ascii=False), wp["id"]),
            )
            updated += 1

    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}결과:")
    print(f"  이미지 복사: {copied}장 → {STORAGE_DIR}")
    print(f"  DB 업데이트: {updated}개 waypoints")


if __name__ == "__main__":
    main()
