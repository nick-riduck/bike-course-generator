import requests
import time
import json

VALHALLA_URL = "http://localhost:8002"

def run_benchmark():
    # 1. Route Request (Seoul -> Busan)
    route_payload = {
        "locations": [
            {"lat": 37.5665, "lon": 126.9780}, # Seoul City Hall
            {"lat": 35.1796, "lon": 129.0756}  # Busan City Hall
        ],
        "costing": "bicycle",
        "directions_options": {"units": "km"}
    }

    print("1. Requesting Route (Seoul -> Busan)...")
    start = time.time()
    try:
        resp = requests.post(f"{VALHALLA_URL}/route", json=route_payload, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"Route Failed: {e}")
        return

    route_time = time.time() - start
    data = resp.json()
    shape = data['trip']['legs'][0]['shape']
    print(f"   -> Success! Time: {route_time:.4f}s, Shape Length: {len(shape)} chars")

    # 2. Trace Attributes Request
    # Note: Using 'shape_match':'map_snap' to simulate our backend logic
    trace_payload = {
        "encoded_polyline": shape,
        "costing": "bicycle",
        "shape_match": "map_snap",
        "filters": {
            "attributes": ["edge.use", "edge.surface", "edge.road_class"], 
            "action": "include"
        }
    }

    print("\n2. Requesting Trace Attributes (for the same shape)...")
    start = time.time()
    try:
        t_resp = requests.post(f"{VALHALLA_URL}/trace_attributes", json=trace_payload, timeout=60)
        
        if t_resp.status_code != 200:
            print(f"   -> Failed! Status: {t_resp.status_code}")
            print(f"   -> Msg: {t_resp.text}")
        else:
            trace_time = time.time() - start
            print(f"   -> Success! Time: {trace_time:.4f}s")
            print(f"\n[Comparison] Route: {route_time:.4f}s vs Trace: {trace_time:.4f}s")
            
    except Exception as e:
        print(f"Trace Failed: {e}")

if __name__ == "__main__":
    run_benchmark()
