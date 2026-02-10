from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import polyline
import copy
import os
import firebase_admin
from firebase_admin import auth, credentials
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# .env 로드
load_dotenv()

# Firebase 초기화 (ADC 방식: 환경변수 기반 자동 인증)
try:
    firebase_admin.initialize_app()
    print("Firebase Admin Initialized with ADC")
except Exception as e:
    print(f"Firebase Init Warning: {e}. (Ignore if running without Google Auth credentials locally)")

app = FastAPI()

# DB 연결 설정
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5433"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "dbname": os.getenv("DB_NAME", "postgres")
}

def get_db_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

class LoginRequest(BaseModel):
    id_token: str

class Location(BaseModel):
    lat: float
    lon: float

class RouteCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    summary_path: List[Location] # Geometry for map matching/preview
    distance: int
    elevation_gain: int
    data_file_path: Optional[str] = "" # For future JSON storage

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

from fastapi import Header, Depends

@app.post("/api/routes")
async def create_route(route: RouteCreateRequest, authorization: str = Header(None)):
    user_id = await get_current_user(authorization)
    
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        
        # Convert list of points to WKT Linestring
        points_str = ", ".join([f"{p.lon} {p.lat}" for p in route.summary_path])
        wkt = f"LINESTRING({points_str})"
        
        # Set start point
        start_wkt = f"POINT({route.summary_path[0].lon} {route.summary_path[0].lat})"

        cur.execute(
            """
            INSERT INTO routes (
                user_id, title, description, summary_path, start_point, distance, elevation_gain, data_file_path
            ) VALUES (
                %s, %s, %s, ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326), %s, %s, %s
            ) RETURNING id, route_num, uuid
            """,
            (user_id, route.title, route.description, wkt, start_wkt, route.distance, route.elevation_gain, route.data_file_path)
        )
        new_route = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "route_id": new_route['id'],
            "route_num": new_route['route_num'],
            "uuid": str(new_route['uuid'])
        }
    except Exception as e:
        print(f"Create Route Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/routes")
async def get_my_routes(authorization: str = Header(None)):
    user_id = await get_current_user(authorization)
    
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT id, route_num, title, distance, elevation_gain, created_at 
            FROM routes 
            WHERE user_id = %s 
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        routes = cur.fetchall()
        cur.close()
        conn.close()
        
        return {"routes": routes}
    except Exception as e:
        print(f"Get Routes Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Get Valhalla URL from environment variable, default to localhost for local dev
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")

def get_segment_style(edge: dict):
    surf = str(edge.get("surface", "paved")).lower()
    use = str(edge.get("use", "road")).lower()
    density = edge.get("density", 0)
    
    # 1. 비포장 / 산악 / 험로 / 페리 (Brown/Grey)
    rough_uses = ["track", "path", "bridleway", "steps", "mountain_bike", "ferry"]
    unpaved_surfaces = ["gravel", "dirt", "earth", "sand", "unpaved", "cobblestone", "grass", "compacted", "fine_gravel", "pebbles", "wood"]
    
    if any(s in surf for s in unpaved_surfaces) or use in rough_uses:
        color = "#8D6E63" if use != "ferry" else "#9E9E9E"
        label = f"Rough/Special ({use})"
        desc = "Rough road. You may need to walk your bike." if use != "ferry" else "Ferry crossing section."
        return color, label, desc

    # 2. 자전거 전용 (Green)
    if use in ["cycleway", "bicycle"]: 
        return "#00E676", "Cycleway", "Bicycle only road. Safe and smooth."

    # 3. 위험 / 합류 주의 (Red)
    if use in ["ramp"]:
        desc = "High traffic risk - Proceed with caution!"
        return "#FF5252", "Ramp", desc

    # 4. 생활 도로 / 보행자 우선 / 주차장 (Yellow)
    yellow_uses = [
        "service", "residential", "living_street", "pedestrian", "sidewalk", "footway", 
        "crossing", "pedestrian_crossing", "parking_aisle", "alley", "emergency_access", 
        "driveway", "service_road"
    ]
    if use in yellow_uses:
        desc = "Pedestrians / Shared road. Please slow down."
        return "#FFC400", f"Living Road ({use})", desc

    # 5. 일반 포장 공도 (Blue)
    blue_uses = ["road", "primary", "secondary", "tertiary", "trunk", "unclassified", "turn_channel", "drive_through", "culdesac"]
    if use in blue_uses:
        if density >= 6:
            desc = "City Area (Traffic Lights Expected)"
        else:
            desc = "Open Road (Low Traffic)"
        return "#2979FF", f"Paved Road ({use})", desc

    # 6. 진짜 알 수 없는 경우 (Grey)
    return "#9E9E9E", f"Other ({use})", "Unknown road type."

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