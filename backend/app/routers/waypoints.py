from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os
from dotenv import load_dotenv
from app.core.security import get_admin_user

load_dotenv()

router = APIRouter(
    prefix="/api/waypoints",
    tags=["waypoints"]
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        port=os.getenv("DB_PORT", "5432")
    )

@router.get("/{waypoint_id}")
async def get_waypoint_detail(waypoint_id: int, user_id: int = Depends(get_admin_user)):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, uuid, name, description, type,
                       ST_X(location::geometry) as lng,
                       ST_Y(location::geometry) as lat,
                       is_verified, etc, created_at
                FROM waypoints WHERE id = %s
            """, (waypoint_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Waypoint not found")

            item = dict(row)
            type_str = item.get('type')
            if isinstance(type_str, str) and type_str.startswith('{') and type_str.endswith('}'):
                inner = type_str[1:-1]
                item['type'] = [t.strip() for t in inner.split(',')] if inner else []
            elif not isinstance(type_str, list):
                item['type'] = []

            etc_data = item.get('etc', {})
            item['tour_count'] = etc_data.get('tour_count', 1)
            item['image_urls'] = etc_data.get('image_urls', [])
            item['tips'] = etc_data.get('tips', [])
            item['nearby_landmarks'] = etc_data.get('nearby_landmarks', [])
            item['address'] = etc_data.get('address', '')
            item['confidence'] = etc_data.get('confidence', '')
            item['category_raw'] = etc_data.get('category_raw', '')

            if item.get('created_at'):
                item['created_at'] = item['created_at'].isoformat()

            return item
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching waypoint detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


@router.get("", response_model=List[Dict[str, Any]])
async def get_waypoints(user_id: int = Depends(get_admin_user)):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # We fetch all waypoints for now. In the future, we might want to paginate or filter by bounding box.
            cur.execute("""
                SELECT 
                    id, 
                    uuid, 
                    name, 
                    description, 
                    type, 
                    ST_X(location::geometry) as lng, 
                    ST_Y(location::geometry) as lat, 
                    is_verified, 
                    etc 
                FROM waypoints
            """)
            rows = cur.fetchall()
            
            result = []
            for row in rows:
                item = dict(row)
                
                # Fix parsing of postgres enum arrays which are returned as strings like '{park,rest_area}'
                type_str = item.get('type')
                if isinstance(type_str, str) and type_str.startswith('{') and type_str.endswith('}'):
                    # Strip {} and split by comma
                    inner = type_str[1:-1]
                    item['type'] = [t.strip() for t in inner.split(',')] if inner else []
                elif isinstance(type_str, list):
                    item['type'] = type_str
                else:
                    item['type'] = []
                    
                # Use standard property names for frontend compatibility
                # tour_count can be mocked or read from 'etc'
                etc_data = item.get('etc', {})
                item['tour_count'] = etc_data.get('tour_count', 1)
                item['has_images'] = len(etc_data.get('image_urls', [])) > 0 or etc_data.get('has_images', False)
                item['has_tips'] = len(etc_data.get('tips', [])) > 0 or etc_data.get('has_tips', False)
                result.append(item)
                
            return result
    except Exception as e:
        print(f"Error fetching waypoints: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()