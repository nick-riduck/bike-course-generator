import psycopg2
import random
import time
from psycopg2.extras import execute_values

# DB Configuration (Docker Port 5433)
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "password",
    "dbname": "postgres"
}

def setup_db():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    print("1. Initializing Schema...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    
    # 1. Geometry Table (Flat Earth)
    cur.execute("DROP TABLE IF EXISTS routes_geom;")
    cur.execute("""
        CREATE TABLE routes_geom (
            id SERIAL PRIMARY KEY,
            path GEOMETRY(LineString, 4326)
        );
    """)
    cur.execute("CREATE INDEX idx_routes_geom_path ON routes_geom USING GIST (path);")

    # 2. Geography Table (Round Earth)
    cur.execute("DROP TABLE IF EXISTS routes_geog;")
    cur.execute("""
        CREATE TABLE routes_geog (
            id SERIAL PRIMARY KEY,
            path GEOGRAPHY(LineString, 4326)
        );
    """)
    cur.execute("CREATE INDEX idx_routes_geog_path ON routes_geog USING GIST (path);")
    
    conn.commit()
    cur.close()
    conn.close()

def seed_data(count=100000):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    print(f"2. Seeding {count} records...")
    
    batch_size = 5000
    data = []
    
    # Generate random paths around Seoul (37.5, 127.0)
    for _ in range(count):
        lat = 37.5 + (random.random() - 0.5) * 2.0  # +/- 1 degree
        lon = 127.0 + (random.random() - 0.5) * 2.0 # +/- 1 degree
        
        # Simple line string
        wkt = f'LINESTRING({lon} {lat}, {lon+0.01} {lat+0.01})'
        data.append((wkt,))
        
        if len(data) >= batch_size:
            execute_values(cur, "INSERT INTO routes_geom (path) VALUES %s", data, template="(ST_GeomFromText(%s, 4326))")
            execute_values(cur, "INSERT INTO routes_geog (path) VALUES %s", data, template="(ST_GeogFromText(%s))")
            data = []
            
    if data:
        execute_values(cur, "INSERT INTO routes_geom (path) VALUES %s", data, template="(ST_GeomFromText(%s, 4326))")
        execute_values(cur, "INSERT INTO routes_geog (path) VALUES %s", data, template="(ST_GeogFromText(%s))")

    conn.commit()
    print("   Running ANALYZE...")
    cur.execute("ANALYZE routes_geom; ANALYZE routes_geog;")
    conn.commit()
    cur.close()
    conn.close()

def run_benchmark_query(label, query, params):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Warm up (run once, ignore result)
    cur.execute(query, params)
    
    start_time = time.time()
    for _ in range(5):
        cur.execute(query, params)
    end_time = time.time()
    
    avg_time = (end_time - start_time) / 5 * 1000 # ms
    print(f"[{label}] Avg Time: {avg_time:.2f} ms")
    
    # Get Explain Analyze
    cur.execute("EXPLAIN ANALYZE " + query, params)
    # Only print first line of explain (Execution Time usually at end, but Cost at start)
    # execution_time_line = [row[0] for row in cur.fetchall() if 'Execution Time' in row[0]]
    # if execution_time_line:
    #     print(f"   Explain: {execution_time_line[0]}")
    
    cur.close()
    conn.close()

def run_tests():
    print("\n3. Running Benchmarks (Search radius: 5km around Seoul center)")
    
    # Center Point (Seoul)
    center_lon = 127.0
    center_lat = 37.5
    radius_m = 5000
    radius_deg = 0.05 # Approx 5km
    
    # Case A: GEOMETRY (Fast, Approx)
    # Using ST_DWithin with degrees
    query_a = """
        SELECT count(*) FROM routes_geom 
        WHERE ST_DWithin(path, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
    """
    run_benchmark_query("GEOMETRY (Degree)", query_a, (center_lon, center_lat, radius_deg))

    # Case B: GEOGRAPHY (Accurate, Slower)
    # Using ST_DWithin with meters
    query_b = """
        SELECT count(*) FROM routes_geog 
        WHERE ST_DWithin(path, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
    """
    run_benchmark_query("GEOGRAPHY (Meter)", query_b, (center_lon, center_lat, radius_m))

    # Case C: CASTING (GEOMETRY -> GEOGRAPHY)
    # Converting column on the fly (Index usage check)
    query_c = """
        SELECT count(*) FROM routes_geom 
        WHERE ST_DWithin(path::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
    """
    run_benchmark_query("CAST (Geom->Geog)", query_c, (center_lon, center_lat, radius_m))

    # Case D: HYBRID (Filter by Geom Box first, then refine with Geography)
    # This simulates what we might do in application code or complex query
    query_d = """
        SELECT count(*) FROM routes_geom 
        WHERE ST_DWithin(path, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s) -- Coarse Filter (Index)
        AND ST_DWithin(path::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s) -- Precise Check
    """
    # Note: radius_deg needs to be slightly larger to be safe (0.06 deg)
    run_benchmark_query("HYBRID (Box -> Exact)", query_d, (center_lon, center_lat, 0.06, center_lon, center_lat, radius_m))


if __name__ == "__main__":
    setup_db()
    seed_data(100000)
    run_tests()