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


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5230",
        "http://localhost:5173", # 로컬 개발용 Vite 포트 추가
        "https://riduck-bike-course-simulator.web.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/auth/login")
async def login(request: LoginRequest):
    try:
        # 1. Firebase ID Token 검증
        decoded_token = auth.verify_id_token(request.id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', 'Anonymous Rider')
        picture = decoded_token.get('picture')

        conn = get_db_conn()
        cur = conn.cursor()

        # 2. 임시 매핑 테이블에서 유저 조회
        cur.execute(
            "SELECT user_id FROM auth_mapping_temp WHERE provider = 'FIREBASE' AND provider_uid = %s",
            (uid,)
        )
        row = cur.fetchone()

        if row:
            # 기존 유저: users 테이블에서 상세 정보 가져오기
            user_id = row['user_id']
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
        else:
            # 신규 유저: users 생성 및 mapping 추가
            # riduck_id는 임시로 -1 * (기존 최소값 - 1) 또는 시퀀스 활용 (여기서는 간단히 처리)
            print(f"Creating new user for Firebase UID: {uid}")
            
            # 임시 음수 riduck_id 생성 (나중에 정식 연동 전까지 식별용)
            cur.execute("SELECT COALESCE(MIN(riduck_id), 0) as min_id FROM users WHERE riduck_id < 0")
            min_id = cur.fetchone()['min_id']
            temp_riduck_id = min_id - 1

            # users 테이블에 삽입
            cur.execute(
                """
                INSERT INTO users (riduck_id, username, email, profile_image_url) 
                VALUES (%s, %s, %s, %s) RETURNING *
                """,
                (temp_riduck_id, name, email, picture)
            )
            user = cur.fetchone()
            user_id = user['id']

            # mapping 테이블에 삽입
            cur.execute(
                "INSERT INTO auth_mapping_temp (provider, provider_uid, user_id) VALUES ('FIREBASE', %s, %s)",
                (uid, user_id)
            )
            conn.commit()

        cur.close()
        conn.close()

        # 3. 자체 세션 정보 반환 (간단히 유저 정보 통째로 응답)
        return {
            "status": "success",
            "user": {
                "id": user['id'],
                "uuid": str(user['uuid']),
                "username": user['username'],
                "email": user['email'],
                "profile_image_url": user['profile_image_url']
            }
        }

    except Exception as e:
        print(f"Login Error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid authentication: {str(e)}")

# Get Valhalla URL from environment variable, default to localhost for local dev
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")

def get_segment_style(edge: dict):
    surf = str(edge.get("surface", "paved")).lower()
    use = str(edge.get("use", "road")).lower()
    if use in ["cycleway", "bicycle"]: return "#00E676", f"cycleway ({surf})"
    if use in ["footway", "pedestrian", "path", "track", "steps"]: return "#FFC107", f"path ({surf})"
    if any(un in surf for un in ["gravel", "dirt", "earth", "sand", "unpaved", "cobblestone"]): return "#FF9800", f"unpaved ({surf})"
    if use in ["service", "residential", "living_street"]: return "#4FC3F7", f"{use} ({surf})"
    if use in ["primary", "secondary", "tertiary", "trunk"]: return "#00695C", f"main_road ({surf})"
    return "#2a9e92", f"road ({surf})"

class Location(BaseModel):
    lat: float
    lon: float

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
    valhalla_payload = {
        "locations": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations],
        "costing": "bicycle",
        "costing_options": {"bicycle": {"bicycle_type": request.bicycle_type}},
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
                        "attributes": ["edge.use", "edge.surface", "edge.begin_shape_index", "edge.end_shape_index"], 
                        "action": "include"
                    }
                }
                t_resp = await client.post(f"{VALHALLA_URL}/trace_attributes", json=trace_payload, timeout=10.0)
                
                if t_resp.status_code == 200:
                    t_data = t_resp.json()
                    edges = t_data.get("edges", [])
                    
                    # If we get shape back, use it
                    if t_data.get("shape"): matched_coords = decode_valhalla_shape(t_data["shape"])
                    
                    if edges:
                        current_color, current_label = get_segment_style(edges[0])
                        current_coords = []
                        
                        for i, edge in enumerate(edges):
                            color, label = get_segment_style(edge)
                            start_idx = edge.get("begin_shape_index", 0)
                            end_idx = edge.get("end_shape_index", 0)
                            
                            if start_idx is None: start_idx = 0
                            if end_idx is None: end_idx = 0
                            
                            # Safety
                            if start_idx >= len(matched_coords): continue
                            if end_idx >= len(matched_coords): end_idx = len(matched_coords) - 1
                            if start_idx == end_idx: end_idx = min(len(matched_coords)-1, end_idx + 1)
                            
                            edge_coords = matched_coords[start_idx : end_idx + 1]
                            
                            # Flush buffer
                            if (color != current_color or label != current_label) and current_coords:
                                if len(current_coords) >= 2:
                                    coords_2d = [[float(pt[0]), float(pt[1])] for pt in current_coords]
                                    display_features.append({
                                        "type": "Feature",
                                        "geometry": {"type": "LineString", "coordinates": coords_2d},
                                        "properties": {"color": current_color, "surface": current_label}
                                    })
                                current_coords = []
                                current_color, current_label = color, label
                            
                            # Buffer logic
                            if not current_coords:
                                current_coords.extend(edge_coords)
                            else:
                                if current_coords[-1] == edge_coords[0]:
                                    current_coords.extend(edge_coords[1:])
                                else:
                                    current_coords.extend(edge_coords)
                        
                        if current_coords and len(current_coords) >= 2:
                            coords_2d = [[float(pt[0]), float(pt[1])] for pt in current_coords]
                            display_features.append({
                                "type": "Feature",
                                "geometry": {"type": "LineString", "coordinates": coords_2d},
                                "properties": {"color": current_color, "surface": current_label}
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
                    for i, ele in enumerate(elevs):
                        if i < len(full_3d):
                            val = float(ele) if ele is not None else 0.0
                            if len(full_3d[i]) < 3: full_3d[i].append(val)
                            else: full_3d[i][2] = val
                    for i in range(1, len(elevs)):
                        diff = elevs[i] - elevs[i-1]
                        if diff > 0.5: ascent += diff
            except: pass

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