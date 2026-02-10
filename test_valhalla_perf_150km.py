import requests
import time

VALHALLA_URL = "http://localhost:8002"

def run_benchmark():
    # 1. Route Request (Seoul -> Chungju, approx 150km)
    route_payload = {
        "locations": [
            {"lat": 37.5665, "lon": 126.9780}, # Seoul
            {"lat": 36.9918, "lon": 127.9083}  # Chungju Station
        ],
        "costing": "bicycle"
    }

    print("--- 150km Benchmark ---")
    print("1. Requesting Route...")
    start = time.time()
    resp = requests.post(f"{VALHALLA_URL}/route", json=route_payload)
    route_time = time.time() - start
    
    shape = resp.json()['trip']['legs'][0]['shape']
    print(f"   -> Success! Time: {route_time:.4f}s")

    # 2. Trace Attributes Request
    trace_payload = {
        "encoded_polyline": shape,
        "costing": "bicycle",
        "shape_match": "map_snap",
        "filters": {"attributes": ["edge.use", "edge.surface"], "action": "include"}
    }

    print("2. Requesting Trace Attributes...")
    start = time.time()
    t_resp = requests.post(f"{VALHALLA_URL}/trace_attributes", json=trace_payload)
    trace_time = time.time() - start
    
    print(f"   -> Success! Time: {trace_time:.4f}s")
    print(f"\n[Result] Trace is {route_time / trace_time:.2f}x faster than Route")

if __name__ == "__main__":
    run_benchmark()
