from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import polyline
import copy
import os
import json
import uuid
import io
from PIL import Image, ImageDraw
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
import firebase_admin
from firebase_admin import auth, credentials
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from google.cloud import storage

from valhalla import ValhallaClient

# .env 로드
load_dotenv()

# Storage Configuration
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "LOCAL") # 'LOCAL' or 'GCS'
STORAGE_BASE_DIR = os.getenv("STORAGE_BASE_DIR", "storage")

# Initialize Valhalla Client
valhalla_client = ValhallaClient(os.getenv("VALHALLA_URL", "http://localhost:8002"))

# Firebase 초기화
try:
    firebase_admin.initialize_app()
    print("Firebase Admin Initialized")
except Exception as e:
    print(f"Firebase Init Warning: {e}")

app = FastAPI()

# DB 연결 설정
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"), # Use standard 5432 for VM
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "dbname": os.getenv("DB_NAME", "postgres")
}

def get_db_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

@app.get("/api/thumbnails/{filename}")
async def get_thumbnail_proxy(filename: str):
    """
    Proxy endpoint to serve thumbnails from GCS or Local storage.
    Ensures images are visible even if GCS bucket is private.
    """
    if STORAGE_TYPE == "GCS":
        try:
            bucket_name = os.getenv("GCS_BUCKET_NAME", "riduck-course-data")
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(f"thumbnails/{filename}")
            
            if not blob.exists():
                raise HTTPException(status_code=404, detail="Thumbnail not found in GCS")
            
            content = blob.download_as_bytes()
            return Response(content=content, media_type="image/png")
        except Exception as e:
            print(f"GCS Proxy Error: {e}")
            raise HTTPException(status_code=500, detail="Error fetching image from GCS")
    
    else: # LOCAL
        file_path = os.path.join(STORAGE_BASE_DIR, "thumbnails", filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Thumbnail not found locally")
        
        with open(file_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type="image/png")

def save_to_storage(content: bytes, folder: str, filename: str):
    """
    Abstracted file saving logic. Supports LOCAL and GCS.
    Returns the relative path or URL for DB storage.
    """
    if STORAGE_TYPE == "LOCAL":
        full_dir = os.path.join(STORAGE_BASE_DIR, folder)
        os.makedirs(full_dir, exist_ok=True)
        file_path = os.path.join(full_dir, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        # For local, we store the relative path from base storage dir
        return os.path.join(folder, filename)
    
    elif STORAGE_TYPE == "GCS":
        try:
            bucket_name = os.getenv("GCS_BUCKET_NAME", "riduck-course-data")
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(f"{folder}/{filename}")
            
            content_type = "application/octet-stream"
            if filename.endswith(".png"):
                content_type = "image/png"
            elif filename.endswith(".json"):
                content_type = "application/json"
            
            blob.upload_from_string(content, content_type=content_type)
            
            # Use relative proxy path for thumbnails so they are served via /api/thumbnails
            if folder == "thumbnails":
                return f"/api/thumbnails/{filename}"
            
            # For JSON, return GCS identifier or relative path
            return f"{folder}/{filename}"
        except Exception as e:
            print(f"GCS Upload Error: {e}")
            raise e
    
    return None

def generate_thumbnail(locations: List, route_uuid: str):
    if not locations: return None
    
    # 1. Calculate Bounding Box from FULL data
    lats_all = [loc.lat for loc in locations]
    lons_all = [loc.lon for loc in locations]
    min_lat, max_lat = min(lats_all), max(lats_all)
    min_lon, max_lon = min(lons_all), max(lons_all)
    
    # 2. Downsample for drawing
    step = max(1, len(locations) // 500)
    sampled = locations[::step]
    if len(sampled) > 0 and sampled[-1] != locations[-1]:
        sampled.append(locations[-1])
    
    # 3. Setup Image (Ratio ~2.5:1 to match UI)
    W, H = 600, 240
    padding = 40 
    img = Image.new('RGB', (W, H), color='#111827')
    draw = ImageDraw.Draw(img)
    
    # 4. Calculate Range and Scale
    lat_range = max_lat - min_lat
    lon_range = max_lon - min_lon
    
    if lat_range < 0.00001: lat_range = 0.0001
    if lon_range < 0.00001: lon_range = 0.0001
    
    # Fit inside (W-2*padding, H-2*padding)
    scale_x = (W - 2 * padding) / lon_range
    scale_y = (H - 2 * padding) / lat_range
    scale = min(scale_x, scale_y)
    
    # Centering offsets
    off_x = (W - lon_range * scale) / 2
    off_y = (H - lat_range * scale) / 2
    
    # 5. Transform Points
    points = []
    for loc in sampled:
        x = off_x + (loc.lon - min_lon) * scale
        y = off_y + (max_lat - loc.lat) * scale # Flip Y (max_lat is top)
        points.append((x, y))
        
    # 6. Draw
    if len(points) > 1:
        draw.line(points, fill='#2a9e92', width=5, joint='curve')
        
        # Start/End Markers
        r = 5
        # Start (Green)
        sx, sy = points[0]
        draw.ellipse((sx-r, sy-r, sx+r, sy+r), fill='#10B981', outline='white', width=1)
        # End (Red)
        ex, ey = points[-1]
        draw.ellipse((ex-r, ey-r, ex+r, ey+r), fill='#EF4444', outline='white', width=1)

    # 7. Save
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()
    
    save_to_storage(img_bytes, "thumbnails", f"{route_uuid}.png")
    return f"/api/thumbnails/{route_uuid}.png"

class LoginRequest(BaseModel):
    id_token: str

class Location(BaseModel):
    lat: float
    lon: float

class RouteCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[str] = "PUBLIC"
    tags: Optional[List[str]] = []
    is_overwrite: Optional[bool] = False
    route_id: Optional[int] = None
    parent_route_id: Optional[int] = None
    summary_path: Optional[List[Location]] = None
    distance: Optional[int] = 0
    elevation_gain: Optional[int] = 0
    data_file_path: Optional[str] = ""
    full_data: Optional[dict] = None
    editor_state: Optional[dict] = None

@app.post("/api/auth/login")
async def login(request: LoginRequest):
    try:
        decoded_token = auth.verify_id_token(request.id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', 'Anonymous Rider')
        picture = decoded_token.get('picture')

        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT user_id FROM auth_mapping_temp WHERE provider = 'FIREBASE' AND provider_uid = %s",
            (uid,)
        )
        row = cur.fetchone()

        if row:
            user_id = row['user_id']
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
        else:
            cur.execute("SELECT COALESCE(MIN(riduck_id), 0) as min_id FROM users WHERE riduck_id < 0")
            min_id = cur.fetchone()['min_id']
            temp_riduck_id = min_id - 1

            cur.execute(
                """
                INSERT INTO users (riduck_id, username, email, profile_image_url) 
                VALUES (%s, %s, %s, %s) RETURNING *
                """,
                (temp_riduck_id, name, email, picture)
            )
            user = cur.fetchone()
            user_id = user['id']

            cur.execute(
                "INSERT INTO auth_mapping_temp (provider, provider_uid, user_id) VALUES ('FIREBASE', %s, %s)",
                (uid, user_id)
            )
            conn.commit()

        cur.close()
        conn.close()

        return {
            "status": "success",
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "profile_image_url": user['profile_image_url']
            }
        }

    except Exception as e:
        print(f"Login Error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid authentication: {str(e)}")

# Dependency to get current user from Firebase Token
async def get_current_user(authorization: str = None): # Header: Authorization
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(" ")[1]
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id FROM auth_mapping_temp WHERE provider = 'FIREBASE' AND provider_uid = %s",
            (uid,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=401, detail="User not found")
            
        return row['user_id']
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/api/routes")
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
                    # geometry.coordinates is usually [[lon, lat], [lon, lat], ...]
                    coords = segment.get('geometry', {}).get('coordinates', [])
                    for i, coord in enumerate(coords):
                        # Avoid duplicating connection points (end of seg1 == start of seg2)
                        # Logic: Always add first point if it's the very first point
                        # Else, if it matches the last added point, skip it?
                        # ValhallaClient expects a clean list of points to stitch?
                        # Actually ValhallaClient.get_standard_course expects SHAPE POINTS (input for map matching)
                        # But wait, we already have the geometry from frontend (which might be from Valhalla route API).
                        # The ValhallaClient.get_standard_course takes `shape_points` and does map matching again to get attributes.
                        # So we just feed the raw line coordinates.
                        
                        if len(all_points) > 0:
                            last_pt = all_points[-1]
                            # Check minimal distance to avoid 0-length segments which might confuse Valhalla
                            # But simple exact duplicate check is enough for connection points
                            if abs(last_pt['lon'] - coord[0]) < 1e-6 and abs(last_pt['lat'] - coord[1]) < 1e-6:
                                continue
                        
                        all_points.append({"lat": coord[1], "lon": coord[0]})
            
            # Call Valhalla Client
            if len(all_points) > 1:
                final_full_data = valhalla_client.get_standard_course(all_points)
                # Inject Editor State back
                final_full_data['editor_state'] = route.editor_state
            else:
                print("Warning: Not enough points to generate course.")

        if not final_full_data:
             raise HTTPException(status_code=400, detail="No route data provided and could not regenerate.")

        # Recalculate Summary Path & Stats from Final Data
        # Ensure we use the Generated Data for DB consistency
        generated_points = final_full_data.get('points', {})
        lats = generated_points.get('lat', [])
        lons = generated_points.get('lon', [])
        
        # Summary Path (Downsample ~100 points for DB geometry)
        step = max(1, len(lats) // 100)
        summary_locs = []
        for i in range(0, len(lats), step):
            summary_locs.append(Location(lat=lats[i], lon=lons[i]))
        if len(lats) > 0 and (len(lats)-1) % step != 0: # Ensure last point
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
            # INSERT new route (or Fork)
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
            # Clear existing tags for this route if any
            cur.execute("DELETE FROM route_tags WHERE route_id = %s", (target_id,))
            
            for tag_name in route.tags:
                tag_name = tag_name.strip().lower()
                if not tag_name: continue
                
                # Get or Create Tag
                cur.execute("INSERT INTO tags (names, slug) VALUES (%s, %s) ON CONFLICT (slug) DO UPDATE SET slug=EXCLUDED.slug RETURNING id", 
                            (json.dumps({"ko": tag_name, "en": tag_name}), tag_name))
                tag_id = cur.fetchone()['id']
                
                # Link Tag to Route
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/routes")
async def search_routes(
    authorization: str = Header(None),
    scope: str = "my",  # 'my', 'public'
    q: Optional[str] = None
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
        # Base Query
        query = """
            SELECT 
                r.id, r.route_num, r.uuid, r.title, r.distance, r.elevation_gain, 
                r.created_at, r.updated_at, r.thumbnail_url, r.status,
                u.username as author_name, u.profile_image_url as author_image,
                COALESCE(ARRAY_AGG(t.slug) FILTER (WHERE t.slug IS NOT NULL), '{}') as tags
            FROM routes r
            LEFT JOIN users u ON r.user_id = u.id
            LEFT JOIN route_tags rt ON r.id = rt.route_id
            LEFT JOIN tags t ON rt.tag_id = t.id
            WHERE 1=1
        """
        params = []

        # Scope Filtering
        if scope == 'my':
            if not user_id:
                raise HTTPException(status_code=401, detail="Login required for my routes")
            query += " AND r.user_id = %s"
            params.append(user_id)
        elif scope == 'public':
            query += " AND r.status = 'PUBLIC'"
        
        # Text Search
        if q:
            query += " AND (r.title ILIKE %s OR r.description ILIKE %s)"
            search_term = f"%{q}%"
            params.append(search_term)
            params.append(search_term)

        query += " GROUP BY r.id, u.id ORDER BY r.updated_at DESC LIMIT 50"

        cur.execute(query, tuple(params))
        routes = cur.fetchall()
        
        return {"routes": routes}
    except Exception as e:
        print(f"Search Routes Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/api/routes/{route_id}")
async def get_route_detail(route_id: int, authorization: str = Header(None)):
    user_id = None
    if authorization:
        try:
            user_id = await get_current_user(authorization)
        except HTTPException:
            pass # Invalid token, treat as anonymous
    
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        
        cur.execute(
            "SELECT id, user_id, title, description, status, data_file_path FROM routes WHERE id = %s",
            (route_id,)
        )
        row = cur.fetchone()
        
        if not row:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Route not found")
        
        # Access Control: Owner OR Public
        if row['user_id'] != user_id and row['status'] != 'PUBLIC':
            cur.close()
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden: Private route")
        
        # Increment View Count
        cur.execute("UPDATE route_stats SET view_count = view_count + 1, updated_at = CURRENT_TIMESTAMP WHERE route_id = %s", (route_id,))
            
        file_rel_path = row['data_file_path']
        conn.commit()
        cur.close()
        conn.close()
        
        # Resolve full path for reading
        file_path = os.path.join(STORAGE_BASE_DIR, file_rel_path)
        
        if not os.path.exists(file_path):
             # Fallback check (if relative path in DB includes 'storage/')
             if os.path.exists(file_rel_path):
                 file_path = file_rel_path
             else:
                 raise HTTPException(status_code=404, detail=f"Route data file missing: {file_rel_path}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            full_data = json.load(f)
            
        # Re-fetch tags and stats
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.slug FROM tags t 
            JOIN route_tags rt ON t.id = rt.tag_id 
            WHERE rt.route_id = %s
        """, (route_id,))
        tags = [r['slug'] for r in cur.fetchall()]
        
        cur.execute("SELECT view_count, download_count FROM route_stats WHERE route_id = %s", (route_id,))
        stats = cur.fetchone()
        
        cur.close()
        conn.close()

        # Merge DB Metadata
        full_data.update({
            "route_id": row['id'],
            "owner_id": row['user_id'],
            "title": row['title'],
            "description": row['description'],
            "status": row['status'],
            "tags": tags,
            "stats": {
                "views": stats['view_count'] if stats else 0,
                "downloads": stats['download_count'] if stats else 0
            }
        })
            
        return full_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Get Route Detail Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/routes/{route_id}/download")
async def record_download(route_id: int):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE route_stats SET download_count = download_count + 1, updated_at = CURRENT_TIMESTAMP WHERE route_id = %s",
            (route_id,)
        )
        if cur.rowcount == 0:
            # If stats row doesn't exist for some reason, create it
            cur.execute("INSERT INTO route_stats (route_id, download_count) VALUES (%s, 1)", (route_id,))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        print(f"Record Download Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Get Valhalla URL from environment variable, default to localhost for local dev
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")

def get_segment_style(edge: dict):
    surf = str(edge.get("surface", "paved")).lower()
    use = str(edge.get("use", "road")).lower()
    density = edge.get("density", 0)
    
    # 1. 비포장 / 산악 / 험로 (Brown)
    rough_uses = ["track", "path", "bridleway", "steps", "mountain_bike"]
    unpaved_surfaces = ["gravel", "dirt", "earth", "sand", "unpaved", "cobblestone", "grass", "compacted", "fine_gravel", "pebbles", "wood"]
    
    if any(s in surf for s in unpaved_surfaces) or use in rough_uses:
        material = use if use in rough_uses else surf
        return "#8D6E63", f"Rough ({material})", "Rough road. You may need to walk your bike."

    # 2. 자전거 전용 (Green)
    if use in ["cycleway", "bicycle"]: 
        return "#00E676", "Cycleway", "Bicycle only road. Safe and smooth."

    # 3. 위험 / 합류 주의 (Red)
    if use in ["ramp"]:
        return "#FF5252", "Ramp", "High traffic risk - Proceed with caution!"

    # 4. 생활 도로 / 보행자 우선 / 주차장 (Yellow)
    yellow_uses = [
        "service", "residential", "living_street", "pedestrian", "sidewalk", "footway", 
        "crossing", "pedestrian_crossing", "parking_aisle", "alley", "emergency_access", 
        "driveway", "service_road"
    ]
    if use in yellow_uses:
        return "#FFC400", "Residence", "Pedestrians / Shared road. Please slow down."

    # 5. 일반 포장 공도 (Blue)
    blue_uses = ["road", "primary", "secondary", "tertiary", "trunk", "unclassified", "turn_channel", "drive_through", "culdesac"]
    if use in blue_uses:
        desc = "City Area (Traffic Lights Expected)" if density >= 6 else "Open Road (Low Traffic)"
        return "#2979FF", "Paved", desc

    # 6. 페리 (Grey)
    if use == "ferry":
        return "#9E9E9E", "Ferry", "Ferry crossing section."

    # 7. 기타 (Grey)
    return "#9E9E9E", "Other", ""

class RouteRequest(BaseModel):
    locations: List[Location]
    bicycle_type: Optional[str] = "Road"
    use_hills: Optional[float] = 0.5
    use_roads: Optional[float] = 0.5

def decode_valhalla_shape(shape_str):
    try:
        decoded = polyline.decode(shape_str, 6)
        return [[float(lon), float(lat)] for lat, lon in decoded]
    except Exception:
        return []

@app.post("/api/route_v2")
async def get_route_v2(request: RouteRequest):
    # [방어 로직] 800km 초과 경로 차단 (직선거리 기준)
    if len(request.locations) >= 2:
        from math import radians, cos, sin, asin, sqrt
        
        def haversine(lon1, lat1, lon2, lat2):
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a)) 
            r = 6371 # 지구 반지름 (km)
            return c * r

        # 첫 번째 점과 마지막 점 사이의 직선거리 체크
        total_direct_dist = haversine(
            request.locations[0].lon, request.locations[0].lat,
            request.locations[-1].lon, request.locations[-1].lat
        )
        
        if total_direct_dist > 800:
            raise HTTPException(
                status_code=400, 
                detail="Course is too long! Please keep the distance within 800km."
            )

    valhalla_payload = {
        "locations": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations],
        "costing": "bicycle",
        "costing_options": {
            "bicycle": {
                "bicycle_type": request.bicycle_type,
                "use_ferry": 0.1 # 페리 이용 최소화 (기본값 0.5)
            }
        },
        "directions_options": {"units": "km"}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{VALHALLA_URL}/route", json=valhalla_payload, timeout=30.0)
            if resp.status_code != 200: raise HTTPException(status_code=resp.status_code, detail=resp.text)
            
            data = resp.json()
            legs = data.get("trip", {}).get("legs", [])
            if not legs: raise HTTPException(status_code=404, detail="No legs found")
            
            route_coords = []
            for leg in legs:
                if leg.get("shape"): route_coords.extend(decode_valhalla_shape(leg["shape"]))
            
            if not route_coords: raise HTTPException(status_code=500, detail="Empty shape")

            display_features = []
            matched_coords = route_coords
            
            try:
                trace_payload = {
                    "shape": [{"lat": c[1], "lon": c[0]} for c in route_coords],
                    "costing": "bicycle",
                    "shape_match": "map_snap",
                    "filters": {
                        # CRITICAL FIX: Explicitly include indices!
                        "attributes": ["edge.use", "edge.surface", "edge.begin_shape_index", "edge.end_shape_index", "edge.density"], 
                        "action": "include"
                    }
                }
                t_resp = await client.post(f"{VALHALLA_URL}/trace_attributes", json=trace_payload, timeout=30.0)
                
                if t_resp.status_code != 200:
                    print(f"TRACE ERROR: {t_resp.status_code} - {t_resp.text}", flush=True)

                if t_resp.status_code == 200:
                    t_data = t_resp.json()
                    edges = t_data.get("edges", [])
                    if not edges:
                        print("TRACE SUCCESS BUT NO EDGES FOUND!", flush=True)
                    
                    # If we get shape back, use it
                    if t_data.get("shape"): matched_coords = decode_valhalla_shape(t_data["shape"])
                    
                    if edges:
                        current_color, current_label, current_desc = get_segment_style(edges[0])
                        current_coords = []
                        
                        for i, edge in enumerate(edges):
                            color, label, desc = get_segment_style(edge)
                            start_idx = edge.get("begin_shape_index", 0)
                            end_idx = edge.get("end_shape_index", 0)
                            
                            if start_idx is None: start_idx = 0
                            if end_idx is None: end_idx = 0
                            
                            if start_idx >= len(matched_coords): continue
                            if end_idx >= len(matched_coords): end_idx = len(matched_coords) - 1
                            if start_idx == end_idx: end_idx = min(len(matched_coords)-1, end_idx + 1)
                            
                            edge_coords = matched_coords[start_idx : end_idx + 1]
                            
                            if (color != current_color or label != current_label) and current_coords:
                                if len(current_coords) >= 2:
                                    display_features.append({
                                        "type": "Feature",
                                        "geometry": {"type": "LineString", "coordinates": [[float(pt[0]), float(pt[1])] for pt in current_coords]},
                                        "properties": {"color": current_color, "surface": current_label, "description": current_desc}
                                    })
                                current_coords = []
                                current_color, current_label, current_desc = color, label, desc
                            
                            if not current_coords:
                                current_coords.extend(edge_coords)
                            else:
                                if current_coords[-1] == edge_coords[0]:
                                    current_coords.extend(edge_coords[1:])
                                else:
                                    current_coords.extend(edge_coords)
                        
                        if current_coords and len(current_coords) >= 2:
                            display_features.append({
                                "type": "Feature",
                                "geometry": {"type": "LineString", "coordinates": [[float(pt[0]), float(pt[1])] for pt in current_coords]},
                                "properties": {"color": current_color, "surface": current_label, "description": current_desc}
                            })
            except Exception as e:
                print(f"TRACE FAILED: {e}", flush=True)

            if not display_features:
                coords_2d = [[float(c[0]), float(c[1])] for c in matched_coords]
                display_features = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords_2d}, "properties": {"color": "#2a9e92", "surface": "paved"}}]

            # Elevation
            ascent = 0
            full_3d = copy.deepcopy(matched_coords)
            elevation_payload = {"range_candidates": False, "shape": [{"lat": c[1], "lon": c[0]} for c in matched_coords]}
            
            try:
                h_resp = await client.post(f"{VALHALLA_URL}/height", json=elevation_payload, timeout=10.0)
                if h_resp.status_code == 200:
                    elevs = h_resp.json().get("height", [])
                    
                    # 1. 기본 고도 매핑
                    for i, ele in enumerate(elevs):
                        if i < len(full_3d):
                            val = float(ele) if ele is not None else 0.0
                            if len(full_3d[i]) < 3: full_3d[i].append(val)
                            else: full_3d[i][2] = val
                            
                    # 2. Ferry 구간 평탄화 (Flatlining)
                    # Trace 결과(edges)가 있다면 활용
                    if 'edges' in locals() and edges:
                        for edge in edges:
                            if edge.get("use") == "ferry":
                                start_idx = edge.get("begin_shape_index", 0)
                                end_idx = edge.get("end_shape_index", 0)
                                
                                # 시작점 고도로 끝까지 덮어쓰기 (바다 위니까 평평하게)
                                if start_idx < len(full_3d):
                                    base_elev = full_3d[start_idx][2] if len(full_3d[start_idx]) > 2 else 0.0
                                    
                                    for k in range(start_idx, min(end_idx + 1, len(full_3d))):
                                        if len(full_3d[k]) > 2:
                                            full_3d[k][2] = base_elev
                                            # elevs 배열도 같이 수정해야 ascent 계산 시 튀지 않음
                                            if k < len(elevs): elevs[k] = base_elev

                    # 3. 획고(Ascent) 계산 (보정된 데이터 기반)
                    for i in range(1, len(elevs)):
                        diff = elevs[i] - elevs[i-1]
                        if diff > 0.5: ascent += diff
            except Exception as e: 
                print(f"Elevation Error: {e}")
                pass

            return {
                "summary": {
                    "distance": data.get("trip", {}).get("summary", {}).get("length", 0),
                    "time": data.get("trip", {}).get("summary", {}).get("time", 0),
                    "ascent": round(ascent)
                },
                "full_geometry": {"type": "LineString", "coordinates": full_3d},
                "display_geojson": {"type": "FeatureCollection", "features": display_features}
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
