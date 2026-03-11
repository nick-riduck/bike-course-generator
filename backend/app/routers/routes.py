import os
import json
import uuid
import tempfile
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Header, Depends, UploadFile, File
from app.core.database import get_db_conn
from app.core.storage import save_to_storage
from app.core.security import get_current_user
from app.core.config import VALHALLA_URL, STORAGE_TYPE, STORAGE_BASE_DIR, GCS_BUCKET_NAME
from app.models.route import RouteCreateRequest
from app.models.common import Location
from app.services.image_service import generate_thumbnail
from app.services.embedding_service import get_embedding
from app.services.auto_tag_service import generate_tags_and_description
from google.cloud import storage

from valhalla import ValhallaClient
from gpx_loader import GpxLoader, TcxLoader

router = APIRouter(prefix="/api/routes", tags=["routes"])
valhalla_client = ValhallaClient(VALHALLA_URL)

@router.post("")
async def create_route(route: RouteCreateRequest, authorization: str = Header(None)):
    user_id = await get_current_user(authorization)
    
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        # 1. Permission Check if Overwrite
        if route.is_overwrite and route.route_id:
            cur.execute("SELECT user_id, uuid FROM routes WHERE id = %s", (route.route_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(status_code=404, detail="Route not found")
            if row['user_id'] != user_id: raise HTTPException(status_code=403, detail="Not authorized to overwrite")
            route_uuid = str(row['uuid'])
        else:
            route_uuid = str(uuid.uuid4())

        # 2. Logic to Generate or Use Full Data
        final_full_data = route.full_data
        
        # If Editor State is provided, we REGENERATE full_data using ValhallaClient
        if route.editor_state and route.editor_state.get('sections'):
            print(f"Regenerating route data for {route.title} using ValhallaClient...")
            
            # Extract all coordinates from sections
            all_points = []
            sections = route.editor_state['sections']
            for section in sections:
                for segment in section.get('segments', []):
                    coords = segment.get('geometry', {}).get('coordinates', [])
                    for i, coord in enumerate(coords):
                        if len(all_points) > 0:
                            last_pt = all_points[-1]
                            if abs(last_pt['lon'] - coord[0]) < 1e-6 and abs(last_pt['lat'] - coord[1]) < 1e-6:
                                continue
                        all_points.append({"lat": coord[1], "lon": coord[0]})
            
            if len(all_points) > 1:
                final_full_data = valhalla_client.get_standard_course(all_points)
                final_full_data['editor_state'] = route.editor_state
            else:
                print("Warning: Not enough points to generate course.")

        if not final_full_data:
             raise HTTPException(status_code=400, detail="No route data provided and could not regenerate.")

        # Recalculate Summary Path & Stats from Final Data
        generated_points = final_full_data.get('points', {})
        lats = generated_points.get('lat', [])
        lons = generated_points.get('lon', [])
        
        step = max(1, len(lats) // 100)
        summary_locs = []
        for i in range(0, len(lats), step):
            summary_locs.append(Location(lat=lats[i], lon=lons[i]))
        if len(lats) > 0 and (len(lats)-1) % step != 0:
            summary_locs.append(Location(lat=lats[-1], lon=lons[-1]))
            
        final_distance = final_full_data.get('stats', {}).get('distance', 0)
        final_elevation = final_full_data.get('stats', {}).get('ascent', 0)

        # 3. Save JSON Data via Abstracted Storage
        json_content = json.dumps(final_full_data, ensure_ascii=False).encode('utf-8')
        final_data_path = save_to_storage(json_content, "routes", f"{route_uuid}.json")

        # 4. Geometry Preparation
        points_str = ", ".join([f"{p.lon} {p.lat}" for p in summary_locs])
        wkt = f"LINESTRING({points_str})"
        start_wkt = f"POINT({summary_locs[0].lon} {summary_locs[0].lat})"

        # Generate Thumbnail
        thumbnail_url = generate_thumbnail(summary_locs, route_uuid)

        if route.is_overwrite and route.route_id:
            # UPDATE existing route
            cur.execute(
                """
                UPDATE routes SET
                    title = %s, description = %s, status = %s, 
                    summary_path = ST_GeomFromText(%s, 4326), 
                    start_point = ST_GeomFromText(%s, 4326),
                    distance = %s, elevation_gain = %s, data_file_path = %s,
                    thumbnail_url = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s RETURNING id, route_num
                """,
                (route.title, route.description, route.status, wkt, start_wkt, final_distance, final_elevation, final_data_path, thumbnail_url, route.route_id)
            )
            saved_route = cur.fetchone()
        else:
            # INSERT new route
            cur.execute(
                """
                INSERT INTO routes (
                    uuid, user_id, parent_route_id, title, description, status, 
                    summary_path, start_point, distance, elevation_gain, data_file_path, thumbnail_url
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326), %s, %s, %s, %s
                ) RETURNING id, route_num
                """,
                (route_uuid, user_id, route.parent_route_id, route.title, route.description, route.status, wkt, start_wkt, final_distance, final_elevation, final_data_path, thumbnail_url)
            )
            saved_route = cur.fetchone()

        target_id = saved_route['id']

        # 5. Handle Tags
        if route.tags is not None:
            cur.execute("DELETE FROM route_tags WHERE route_id = %s", (target_id,))
            for tag_name in route.tags:
                tag_name = tag_name.strip().lower()
                if not tag_name: continue
                # Check if tag exists
                cur.execute("SELECT id, embedding FROM tags WHERE slug = %s", (tag_name,))
                existing = cur.fetchone()
                if existing:
                    tag_id = existing['id']
                    # Backfill embedding if missing
                    if existing['embedding'] is None:
                        try:
                            emb = get_embedding(tag_name)
                            cur.execute("UPDATE tags SET embedding = %s::halfvec WHERE id = %s", (str(emb), tag_id))
                        except Exception as emb_err:
                            print(f"Embedding backfill error for '{tag_name}': {emb_err}")
                else:
                    # Create new tag with embedding
                    try:
                        emb = get_embedding(tag_name)
                        cur.execute(
                            "INSERT INTO tags (names, slug, embedding) VALUES (%s, %s, %s::halfvec) RETURNING id",
                            (json.dumps({"ko": tag_name, "en": tag_name}), tag_name, str(emb)),
                        )
                    except Exception as emb_err:
                        print(f"Embedding generation error for '{tag_name}': {emb_err}")
                        cur.execute(
                            "INSERT INTO tags (names, slug) VALUES (%s, %s) ON CONFLICT (slug) DO UPDATE SET slug=EXCLUDED.slug RETURNING id",
                            (json.dumps({"ko": tag_name, "en": tag_name}), tag_name),
                        )
                    tag_id = cur.fetchone()['id']
                cur.execute("INSERT INTO route_tags (route_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (target_id, tag_id))

        # 6. Initialize Stats if New
        if not (route.is_overwrite and route.route_id):
            cur.execute("INSERT INTO route_stats (route_id) VALUES (%s) ON CONFLICT DO NOTHING", (target_id,))

        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "route_id": saved_route['id'],
            "route_num": saved_route['route_num'],
            "uuid": route_uuid,
            "thumbnail_url": thumbnail_url
        }
    except Exception as e:
        print(f"Save Route Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tags")
async def get_tags():
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT t.slug, t.names, COUNT(rt.route_id) as count
            FROM tags t
            INNER JOIN route_tags rt ON rt.tag_id = t.id
            INNER JOIN routes r ON r.id = rt.route_id AND r.status = 'PUBLIC'
            GROUP BY t.id, t.slug, t.names
            ORDER BY count DESC
        """)
        rows = cur.fetchall()
        return [
            {
                "slug": row["slug"],
                "name": row["names"].get("ko", row["slug"]) if isinstance(row["names"], dict) else row["slug"],
                "count": row["count"]
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Tags Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/tags/search")
async def search_tags(q: str = ""):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        q = q.strip()
        if not q:
            # Return popular tags when no query
            cur.execute("""
                SELECT t.slug, t.names, COUNT(rt.route_id) as count
                FROM tags t
                INNER JOIN route_tags rt ON rt.tag_id = t.id
                INNER JOIN routes r ON r.id = rt.route_id AND r.status = 'PUBLIC'
                GROUP BY t.id, t.slug, t.names
                ORDER BY count DESC
                LIMIT 15
            """)
            rows = cur.fetchall()
            return [
                {
                    "slug": row["slug"],
                    "name": row["names"].get("ko", row["slug"]) if isinstance(row["names"], dict) else row["slug"],
                    "count": row["count"],
                    "similarity": None,
                }
                for row in rows
            ]

        # 1. Text matching (LIKE)
        cur.execute("""
            SELECT t.id, t.slug, t.names, COUNT(rt.route_id) as count
            FROM tags t
            LEFT JOIN route_tags rt ON rt.tag_id = t.id
            LEFT JOIN routes r ON r.id = rt.route_id AND r.status = 'PUBLIC'
            WHERE t.slug LIKE %s
            GROUP BY t.id, t.slug, t.names
            ORDER BY count DESC
            LIMIT 10
        """, (f"%{q}%",))
        text_rows = cur.fetchall()

        # 2. Semantic search via embedding
        semantic_rows = []
        try:
            query_embedding = get_embedding(q)
            cur.execute("""
                SELECT t.id, t.slug, t.names, COUNT(rt.route_id) as count,
                       1 - (t.embedding <=> %s::halfvec) as similarity
                FROM tags t
                LEFT JOIN route_tags rt ON rt.tag_id = t.id
                LEFT JOIN routes r ON r.id = rt.route_id AND r.status = 'PUBLIC'
                WHERE t.embedding IS NOT NULL
                GROUP BY t.id, t.slug, t.names, t.embedding
                ORDER BY t.embedding <=> %s::halfvec
                LIMIT 10
            """, (str(query_embedding), str(query_embedding)))
            semantic_rows = cur.fetchall()
        except Exception as emb_err:
            print(f"Embedding search fallback: {emb_err}")

        # 3. Merge results (text matches first, then semantic, deduplicated)
        results = []
        seen_ids = set()

        for row in text_rows:
            seen_ids.add(row["id"])
            sim = None
            for sr in semantic_rows:
                if sr["id"] == row["id"]:
                    sim = round(float(sr["similarity"]), 4) if sr["similarity"] else None
                    break
            results.append({
                "slug": row["slug"],
                "name": row["names"].get("ko", row["slug"]) if isinstance(row["names"], dict) else row["slug"],
                "count": row["count"],
                "similarity": sim,
            })

        for row in semantic_rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                results.append({
                    "slug": row["slug"],
                    "name": row["names"].get("ko", row["slug"]) if isinstance(row["names"], dict) else row["slug"],
                    "count": row["count"],
                    "similarity": round(float(row["similarity"]), 4) if row["similarity"] else None,
                })

        return results

    except Exception as e:
        print(f"Tag Search Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/nearby")
async def get_nearby_routes(
    lat: float,
    lon: float,
    radius: float = 5.0, # km
    limit: int = 7,
    min_distance: Optional[int] = None,  # km
    max_distance: Optional[int] = None,  # km
    min_elevation: Optional[int] = None, # m
    max_elevation: Optional[int] = None, # m
    tags: Optional[str] = None           # comma-separated slugs
):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        radius_meters = radius * 1000

        # =====================================================================
        # [GIS 공간 쿼리 패턴] Hybrid Query Pattern - 반드시 이 방식을 사용할 것
        # =====================================================================
        # DB 컬럼은 GEOMETRY(4326) 타입으로 저장됨 (docs/db/02_routes_and_segments.md)
        #
        # ❌ 잘못된 방식 - 런타임 캐스팅만 사용:
        #    ST_DWithin(summary_path::geography, center::geography, radius_m)
        #    → GIST 인덱스를 전혀 사용하지 못함 → 풀스캔 → ~558ms (benchmark 실측)
        #
        # ✅ 올바른 방식 - Hybrid 2단계 필터:
        #    Step 1 (Coarse): ST_DWithin(geom_col, center_geom, radius_deg)
        #                     GEOMETRY degree 단위 비교 → GIST 인덱스 활용 → ~0.63ms
        #    Step 2 (Precise): ST_DWithin(geom_col::geography, center_geog, radius_m)
        #                      GEOGRAPHY meter 단위 정밀 검증 → ~1.2ms 최종
        #
        # radius_deg: 미터 반경을 degree로 변환 (1도 ≈ 111km), 15% 버퍼로 Step1 누락 방지
        # =====================================================================
        radius_deg = (radius_meters / 1000) / 111.0 * 1.15

        # Build dynamic filters
        # SQL 파라미터 순서: CTE(4) → spatial(6) → tag_join params → extra_where params → limit
        extra_where = ""
        where_params = []

        if min_distance is not None:
            extra_where += " AND r.distance >= %s"
            where_params.append(min_distance * 1000)  # km → m
        if max_distance is not None:
            extra_where += " AND r.distance <= %s"
            where_params.append(max_distance * 1000)
        if min_elevation is not None:
            extra_where += " AND r.elevation_gain >= %s"
            where_params.append(min_elevation)
        if max_elevation is not None:
            extra_where += " AND r.elevation_gain <= %s"
            where_params.append(max_elevation)

        tag_join = ""
        tag_params = []
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                placeholders = ", ".join(["%s"] * len(tag_list))
                tag_join = f"""
                    INNER JOIN route_tags rt_filter ON rt_filter.route_id = r.id
                    INNER JOIN tags t_filter ON t_filter.id = rt_filter.tag_id
                        AND t_filter.slug IN ({placeholders})
                """
                tag_params = tag_list

        # 순서 맞춰서 조립: CTE → tag JOIN → spatial WHERE → extra filters → limit
        all_params = [lon, lat, lon, lat]
        all_params.extend(tag_params)
        all_params.extend([radius_deg, radius_meters,
                           radius_deg, radius_meters, radius_deg, radius_meters])
        all_params.extend(where_params)
        all_params.append(limit)

        query = f"""
            WITH center AS (
                SELECT
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326) AS geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography AS geog
            )
            SELECT
                r.id, r.title, r.distance, r.elevation_gain,
                ST_AsGeoJSON(r.summary_path) as geojson,
                r.thumbnail_url,
                COALESCE(rs.download_count, 0) as download_count
            FROM center c
            CROSS JOIN routes r
            LEFT JOIN route_stats rs ON rs.route_id = r.id
            {tag_join}
            WHERE r.status = 'PUBLIC'
            -- [Step1] GEOMETRY bbox: GIST 인덱스로 후보군 빠르게 추출
            AND ST_DWithin(r.summary_path, c.geom, %s)
            -- [Step2] GEOGRAPHY exact: 정확한 meter 단위로 정밀 필터
            AND ST_DWithin(r.summary_path::geography, c.geog, %s)
            -- Loop 코스 (시작~끝 500m 이내): Step1/2 통과 시 자동 포함
            -- Linear 코스 (시작 또는 끝점이 반경 내에 있어야 함)
            AND (
                ST_Distance(r.start_point::geography, ST_EndPoint(r.summary_path)::geography) < 500
                OR (
                    ST_DWithin(r.start_point, c.geom, %s)
                    AND ST_DWithin(r.start_point::geography, c.geog, %s)
                )
                OR (
                    ST_DWithin(ST_EndPoint(r.summary_path), c.geom, %s)
                    AND ST_DWithin(ST_EndPoint(r.summary_path)::geography, c.geog, %s)
                )
            )
            {extra_where}
            ORDER BY download_count DESC, r.created_at DESC
            LIMIT %s
        """
        cur.execute(query, all_params)
        rows = cur.fetchall()

        # Power zone colors (Z1 gray → Z7 purple)
        ZONE_COLORS = ['#9CA3AF', '#3B82F6', '#22C55E', '#EAB308', '#F97316', '#EF4444', '#A855F7']

        features = []
        for idx, row in enumerate(rows):
            features.append({
                "type": "Feature",
                "geometry": json.loads(row['geojson']) if row['geojson'] else None,
                "properties": {
                    "id": row['id'],
                    "title": row['title'],
                    "distance": row['distance'],
                    "elevation_gain": row['elevation_gain'],
                    "thumbnail_url": row['thumbnail_url'],
                    "zone_color": ZONE_COLORS[idx % 7]
                }
            })
            
        return {"type": "FeatureCollection", "features": features}

    except Exception as e:
        print(f"Nearby Routes Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("")
async def search_routes(
    authorization: str = Header(None),
    scope: str = "my",  # 'my', 'public'
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    sort: str = 'latest',
    order: str = 'desc',  # 'asc' or 'desc'
    min_distance: Optional[int] = None,  # km
    max_distance: Optional[int] = None,  # km
    min_elevation: Optional[int] = None, # m
    max_elevation: Optional[int] = None, # m
    tags: Optional[str] = None           # comma-separated slugs
):
    user_id = None
    if authorization:
        try:
            user_id = await get_current_user(authorization)
        except:
            pass

    conn = get_db_conn()
    cur = conn.cursor()

    try:
        where_clauses = ["r.status != 'DELETED'"]
        params = []

        if scope == 'my':
            if not user_id:
                raise HTTPException(status_code=401, detail="Login required for my routes")
            where_clauses.append("r.user_id = %s")
            params.append(user_id)
        elif scope == 'public':
            where_clauses.append("r.status = 'PUBLIC'")
        
        if q:
            where_clauses.append("(r.title ILIKE %s OR r.description ILIKE %s)")
            search_term = f"%{q}%"
            params.extend([search_term, search_term])

        if min_distance is not None:
            where_clauses.append("r.distance >= %s")
            params.append(min_distance * 1000)
        if max_distance is not None:
            where_clauses.append("r.distance <= %s")
            params.append(max_distance * 1000)
        if min_elevation is not None:
            where_clauses.append("r.elevation_gain >= %s")
            params.append(min_elevation)
        if max_elevation is not None:
            where_clauses.append("r.elevation_gain <= %s")
            params.append(max_elevation)

        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                placeholders = ", ".join(["%s"] * len(tag_list))
                where_clauses.append(f"""
                    EXISTS (
                        SELECT 1 FROM route_tags rt_f
                        INNER JOIN tags t_f ON t_f.id = rt_f.tag_id
                        WHERE rt_f.route_id = r.id AND t_f.slug IN ({placeholders})
                    )""")
                params.extend(tag_list)

        where_str = " AND ".join(where_clauses)
        
        direction = "ASC" if order == 'asc' else "DESC"
        if sort == 'updated':
            order_by = f"r.updated_at {direction}, r.id DESC"
        elif sort == 'popular':
            order_by = f"download_count {direction}, r.created_at DESC, r.id DESC"
        elif sort == 'distance':
            order_by = f"r.distance {direction}, r.id DESC"
        elif sort == 'elevation':
            order_by = f"r.elevation_gain {direction}, r.id DESC"
        else: # latest default
            order_by = f"r.created_at {direction}, r.id DESC"

        query = f"""
            WITH paged_routes AS (
                SELECT 
                    r.id, r.route_num, r.uuid, r.title, r.distance, r.elevation_gain, 
                    r.created_at, r.updated_at, r.thumbnail_url, r.status, r.user_id,
                    u.username as author_name, u.profile_image_url as author_image, u.email as author_email,
                    COALESCE(rs.view_count, 0) as view_count,
                    COALESCE(rs.download_count, 0) as download_count
                FROM routes r
                LEFT JOIN users u ON r.user_id = u.id
                LEFT JOIN route_stats rs ON r.id = rs.route_id
                WHERE {where_str}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            )
            SELECT 
                pr.*,
                COALESCE(ARRAY_AGG(t.slug) FILTER (WHERE t.slug IS NOT NULL), '{{}}') as tags
            FROM paged_routes pr
            LEFT JOIN route_tags rt ON pr.id = rt.route_id
            LEFT JOIN tags t ON rt.tag_id = t.id
            GROUP BY 
                pr.id, pr.route_num, pr.uuid, pr.title, pr.distance, pr.elevation_gain, 
                pr.created_at, pr.updated_at, pr.thumbnail_url, pr.status, pr.user_id,
                pr.author_name, pr.author_image, pr.author_email, pr.view_count, pr.download_count
            ORDER BY {order_by.replace('r.', 'pr.').replace('download_count', 'pr.download_count')}
        """
        params.append(limit)
        params.append((page - 1) * limit)

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        
        routes = []
        for row in rows:
            author_name = row['author_name'] or "알 수 없음"

            routes.append({
                "id": row['id'],
                "route_num": row['route_num'],
                "uuid": row['uuid'],
                "title": row['title'],
                "distance": row['distance'],
                "elevation_gain": row['elevation_gain'],
                "created_at": row['created_at'],
                "updated_at": row['updated_at'],
                "thumbnail_url": row['thumbnail_url'],
                "status": row['status'],
                "user_id": row['user_id'],
                "author_name": author_name,
                "author_image": row['author_image'],
                "tags": row['tags'],
                "view_count": row['view_count'],
                "download_count": row['download_count']
            })
            
        return {"routes": routes, "page": page, "limit": limit, "sort": sort}

    except Exception as e:
        print(f"Search Routes Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{route_id}")
async def delete_route(route_id: int, authorization: str = Header(None)):
    user_id = await get_current_user(authorization)
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM routes WHERE id = %s", (route_id,))
        row = cur.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Route not found")
        if row['user_id'] != user_id: raise HTTPException(status_code=403, detail="Not authorized to delete this route")
        cur.execute("UPDATE routes SET status = 'DELETED', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (route_id,))
        conn.commit()
        return {"status": "success"}
    finally:
        cur.close()
        conn.close()

@router.get("/{route_id}")
async def get_route_detail(route_id: str, authorization: str = Header(None)):
    user_id = None
    if authorization:
        try:
            user_id = await get_current_user(authorization)
        except:
            pass

    # Determine if route_id is UUID or integer
    is_uuid = False
    try:
        uuid.UUID(route_id)
        is_uuid = True
    except ValueError:
        pass

    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        if is_uuid:
            where_clause = "r.uuid = %s"
            param = route_id
        else:
            where_clause = "r.id = %s"
            param = int(route_id)

        cur.execute(
            f"""
            SELECT r.id, r.route_num, r.uuid, r.user_id, r.title, r.description, r.status, r.data_file_path,
                   r.distance, r.elevation_gain, r.created_at, r.updated_at,
                   u.username as author_name, u.email as author_email,
                   u.profile_image_url as author_image
            FROM routes r
            LEFT JOIN users u ON r.user_id = u.id
            WHERE {where_clause} AND r.status != 'DELETED'
            """,
            (param,)
        )
        row = cur.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Route not found")

        # Access control
        is_owner = row['user_id'] == user_id
        if not is_owner:
            if row['status'] == 'PRIVATE':
                raise HTTPException(status_code=403, detail="Forbidden: Private route")
            if row['status'] == 'LINK_ONLY' and not is_uuid:
                raise HTTPException(status_code=403, detail="Forbidden: This route is only accessible via share link")
        
        db_id = row['id']
        cur.execute("UPDATE route_stats SET view_count = view_count + 1, updated_at = CURRENT_TIMESTAMP WHERE route_id = %s", (db_id,))
        file_rel_path = row['data_file_path']
        conn.commit()

        full_data = {}
        if STORAGE_TYPE == "GCS":
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob_path = file_rel_path if not file_rel_path.startswith("/") else file_rel_path[1:]
            blob = bucket.blob(blob_path)
            if not blob.exists(): raise HTTPException(status_code=404, detail="Route data file missing in GCS")
            json_content = blob.download_as_string()
            full_data = json.loads(json_content)
        else:
            file_path = os.path.join(STORAGE_BASE_DIR, file_rel_path)
            if not os.path.exists(file_path):
                 if os.path.exists(file_rel_path): file_path = file_rel_path
                 else: raise HTTPException(status_code=404, detail=f"Route data file missing: {file_rel_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                full_data = json.load(f)

        cur.execute("""
            SELECT t.slug FROM tags t
            JOIN route_tags rt ON t.id = rt.tag_id
            WHERE rt.route_id = %s
        """, (db_id,))
        tags = [r['slug'] for r in cur.fetchall()]

        cur.execute("SELECT view_count, download_count FROM route_stats WHERE route_id = %s", (db_id,))
        stats = cur.fetchone()

        author_name = row['author_name'] or "알 수 없음"

        full_data.update({
            "route_id": row['id'],
            "route_num": row['route_num'],
            "uuid": str(row['uuid']),
            "owner_id": row['user_id'],
            "author_name": author_name,
            "author_image": row['author_image'],
            "title": row['title'],
            "description": row['description'],
            "status": row['status'],
            "distance": row['distance'],
            "elevation_gain": row['elevation_gain'],
            "created_at": row['created_at'].isoformat() if row['created_at'] else None,
            "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None,
            "tags": tags,
            "stats": {
                "views": stats['view_count'] if stats else 0,
                "downloads": stats['download_count'] if stats else 0
            }
        })
        return full_data
    finally:
        if conn: conn.close()

@router.post("/{route_id}/download")
async def increment_download_count(route_id: int):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM routes WHERE id = %s", (route_id,))
        if not cur.fetchone(): raise HTTPException(status_code=404, detail="Route not found")
        cur.execute(
            """
            INSERT INTO route_stats (route_id, download_count) VALUES (%s, 1)
            ON CONFLICT (route_id) DO UPDATE 
            SET download_count = route_stats.download_count + 1, updated_at = CURRENT_TIMESTAMP
            """,
            (route_id,)
        )
        conn.commit()
        return {"status": "success"}
    finally:
        cur.close()
        conn.close()

@router.post("/import")
async def import_gpx(file: UploadFile = File(...)):
    try:
        content = await file.read()
        suffix = os.path.splitext(file.filename)[1].lower()
        if suffix not in [".gpx", ".tcx"]:
            if b"<TrainingCenterDatabase" in content: suffix = ".tcx"
            else: suffix = ".gpx"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        loader = TcxLoader(tmp_path) if suffix == ".tcx" else GpxLoader(tmp_path)
        loader.load()
        os.unlink(tmp_path)
        
        if not loader.points: raise HTTPException(status_code=400, detail=f"Invalid {suffix[1:].upper()} file: No track points found.")
        return loader.process_with_valhalla(valhalla_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-tag")
async def generate_auto_tag_and_desc(route: RouteCreateRequest, authorization: str = Header(None)):
    """Generate AI tags and description"""
    # Just need full_data
    full_data = route.full_data
    if not full_data and route.editor_state and route.editor_state.get('sections'):
        all_points = []
        for section in route.editor_state['sections']:
            for segment in section.get('segments', []):
                coords = segment.get('geometry', {}).get('coordinates', [])
                for coord in coords:
                    all_points.append({"lat": coord[1], "lon": coord[0]})
        if len(all_points) > 1:
            full_data = valhalla_client.get_standard_course(all_points)
            full_data['editor_state'] = route.editor_state
    
    if not full_data:
        return {"tags": [], "description": ""}

    conn = get_db_conn()
    try:
        result = generate_tags_and_description(conn, full_data)
        return result
    except Exception as e:
        print(f"Auto-tag generation error: {e}")
        return {"tags": [], "description": ""}
    finally:
        conn.close()
