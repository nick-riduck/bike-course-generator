import httpx
import polyline
import copy
from typing import List, Optional
from math import radians, cos, sin, asin, sqrt
from fastapi import APIRouter, HTTPException
from app.core.config import VALHALLA_URL
from app.models.route import RouteRequest

router = APIRouter(prefix="/api/route_v2", tags=["plan"])

def get_segment_style(edge: dict):
    surf = str(edge.get("surface", "paved")).lower()
    use = str(edge.get("use", "road")).lower()
    density = edge.get("density", 0)
    rough_uses = ["track", "path", "bridleway", "steps", "mountain_bike"]
    unpaved_surfaces = ["gravel", "dirt", "earth", "sand", "unpaved", "cobblestone", "grass", "compacted", "fine_gravel", "pebbles", "wood"]
    if any(s in surf for s in unpaved_surfaces) or use in rough_uses:
        return "#8D6E63", f"Rough ({use if use in rough_uses else surf})", "Rough road. Walk may be needed."
    if use in ["cycleway", "bicycle"]: return "#00E676", "Cycleway", "Safe and smooth."
    if use in ["ramp"]: return "#FF5252", "Ramp", "High traffic risk!"
    yellow_uses = ["service", "residential", "living_street", "pedestrian", "sidewalk", "footway", "crossing", "pedestrian_crossing", "parking_aisle", "alley", "emergency_access", "driveway", "service_road"]
    if use in yellow_uses: return "#FFC400", "Residence", "Pedestrians / Shared road."
    blue_uses = ["road", "primary", "secondary", "tertiary", "trunk", "unclassified", "turn_channel", "drive_through", "culdesac"]
    if use in blue_uses: return "#2979FF", "Paved", "City Area" if density >= 6 else "Open Road"
    if use == "ferry": return "#9E9E9E", "Ferry", "Ferry crossing."
    return "#9E9E9E", "Other", ""

def decode_valhalla_shape(shape_str):
    try:
        decoded = polyline.decode(shape_str, 6)
        return [[float(lon), float(lat)] for lat, lon in decoded]
    except: return []

def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371

@router.post("")
async def get_route_v2(request: RouteRequest):
    if len(request.locations) >= 2:
        if haversine(request.locations[0].lon, request.locations[0].lat, request.locations[-1].lon, request.locations[-1].lat) > 800:
            raise HTTPException(status_code=400, detail="Course is too long! Max 800km.")
    
    valhalla_payload = {
        "locations": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations],
        "costing": "bicycle",
        "costing_options": {"bicycle": {"bicycle_type": request.bicycle_type, "use_ferry": 0.1}},
        "directions_options": {"units": "km"}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{VALHALLA_URL}/route", json=valhalla_payload, timeout=30.0)
            if resp.status_code != 200: raise HTTPException(status_code=resp.status_code, detail=resp.text)
            data = resp.json()
            legs = data.get("trip", {}).get("legs", [])
            route_coords = []
            for leg in legs:
                if leg.get("shape"): route_coords.extend(decode_valhalla_shape(leg["shape"]))
            if not route_coords: raise HTTPException(status_code=500, detail="Empty shape")
            
            display_features, matched_coords = [], route_coords
            try:
                trace_payload = {
                    "shape": [{"lat": c[1], "lon": c[0]} for c in route_coords],
                    "costing": "bicycle", "shape_match": "map_snap",
                    "filters": {"attributes": ["edge.use", "edge.surface", "edge.begin_shape_index", "edge.end_shape_index", "edge.density"], "action": "include"}
                }
                t_resp = await client.post(f"{VALHALLA_URL}/trace_attributes", json=trace_payload, timeout=30.0)
                if t_resp.status_code == 200:
                    t_data = t_resp.json()
                    edges = t_data.get("edges", [])
                    if t_data.get("shape"): matched_coords = decode_valhalla_shape(t_data["shape"])
                    if edges:
                        current_color, current_label, current_desc = get_segment_style(edges[0])
                        current_coords = []
                        for edge in edges:
                            color, label, desc = get_segment_style(edge)
                            start_idx, end_idx = edge.get("begin_shape_index", 0) or 0, edge.get("end_shape_index", 0) or 0
                            if start_idx >= len(matched_coords): continue
                            end_idx = min(len(matched_coords)-1, end_idx)
                            if start_idx == end_idx: end_idx = min(len(matched_coords)-1, end_idx + 1)
                            edge_coords = matched_coords[start_idx : end_idx + 1]
                            if (color != current_color or label != current_label) and current_coords:
                                if len(current_coords) >= 2:
                                    display_features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[float(pt[0]), float(pt[1])] for pt in current_coords]}, "properties": {"color": current_color, "surface": current_label, "description": current_desc}})
                                current_coords, current_color, current_label, current_desc = [], color, label, desc
                            if not current_coords: current_coords.extend(edge_coords)
                            else: current_coords.extend(edge_coords[1:] if current_coords[-1] == edge_coords[0] else edge_coords)
                        if current_coords and len(current_coords) >= 2:
                            display_features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[float(pt[0]), float(pt[1])] for pt in current_coords]}, "properties": {"color": current_color, "surface": current_label, "description": current_desc}})
            except Exception as e: print(f"TRACE FAILED: {e}")
            
            if not display_features:
                display_features = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[float(c[0]), float(c[1])] for c in matched_coords]}, "properties": {"color": "#2a9e92", "surface": "paved"}}]
            
            ascent, full_3d = 0, copy.deepcopy(matched_coords)
            try:
                h_resp = await client.post(f"{VALHALLA_URL}/height", json={"range_candidates": False, "shape": [{"lat": c[1], "lon": c[0]} for c in matched_coords]}, timeout=10.0)
                if h_resp.status_code == 200:
                    elevs = h_resp.json().get("height", [])
                    for i, ele in enumerate(elevs):
                        if i < len(full_3d):
                            val = float(ele) if ele is not None else 0.0
                            if len(full_3d[i]) < 3: full_3d[i].append(val)
                            else: full_3d[i][2] = val
                    if 'edges' in locals() and edges:
                        for edge in edges:
                            if edge.get("use") == "ferry":
                                start_idx, end_idx = edge.get("begin_shape_index", 0) or 0, edge.get("end_shape_index", 0) or 0
                                if start_idx < len(full_3d):
                                    base_elev = full_3d[start_idx][2] if len(full_3d[start_idx]) > 2 else 0.0
                                    for k in range(start_idx, min(end_idx + 1, len(full_3d))):
                                        if len(full_3d[k]) > 2: full_3d[k][2] = base_elev
                                        if k < len(elevs): elevs[k] = base_elev
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
            raise HTTPException(status_code=500, detail=str(e))
