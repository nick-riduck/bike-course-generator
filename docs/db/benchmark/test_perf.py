import psycopg2
import random
import time
import uuid
from psycopg2.extras import execute_values

# DB 연결 정보 (Docker로 띄울 포트 5433 기준)
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
    
    print("1. 스키마 초기화 및 테이블 생성...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    cur.execute("DROP TABLE IF EXISTS routes CASCADE;")
    cur.execute("DROP TABLE IF EXISTS users CASCADE;")
    cur.execute("DROP TYPE IF EXISTS user_status CASCADE;")
    cur.execute("DROP TYPE IF EXISTS route_status CASCADE;")

    cur.execute("CREATE TYPE user_status AS ENUM ('ACTIVE', 'BANNED', 'PENDING_DELETION', 'DELETED');")
    cur.execute("""
        CREATE TABLE users (
            id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 100000000) PRIMARY KEY,
            uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
            riduck_id INTEGER UNIQUE NOT NULL,
            username VARCHAR(50) NOT NULL,
            email VARCHAR(255) NOT NULL,
            status user_status DEFAULT 'ACTIVE' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # 멘토님 조언: status 선행 인덱스
    cur.execute("CREATE INDEX idx_users_status_email ON users(status, email);")

    cur.execute("CREATE TYPE route_status AS ENUM ('PUBLIC', 'PRIVATE', 'LINK_ONLY', 'DELETED');")
    cur.execute("""
        CREATE TABLE routes (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL,
            title VARCHAR(255) DEFAULT 'Test Course', -- 테스트용 기본값 추가
            status route_status DEFAULT 'PUBLIC' NOT NULL,
            summary_path GEOGRAPHY(LineString, 4326),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("CREATE INDEX idx_routes_status_user ON routes(status, user_id);")
    cur.execute("CREATE INDEX idx_routes_summary_path ON routes USING GIST (summary_path);")

    # 통계 테이블 추가
    cur.execute("DROP TABLE IF EXISTS route_stats CASCADE;")
    cur.execute("""
        CREATE TABLE route_stats (
            route_id BIGINT PRIMARY KEY,
            view_count INTEGER DEFAULT 0 NOT NULL,
            download_count INTEGER DEFAULT 0 NOT NULL
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def seed_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # 1. Users 데이터 (10만 건)
    print("2. 유저 데이터 10만 건 생성 중...")
    users = []
    for i in range(100000):
        status = random.choice(['ACTIVE', 'ACTIVE', 'ACTIVE', 'BANNED', 'DELETED']) # 60% Active
        users.append((
            i + 2000000, # riduck_id
            f"user_{i}",
            f"rider_{i}@example.com",
            status
        ))
    
    execute_values(cur, 
        "INSERT INTO users (riduck_id, username, email, status) VALUES %s", 
        users, page_size=5000)
    
    # 2. Routes 데이터 (5만 건 - 서울 근처 랜덤 폴리라인)
    print("3. 코스 데이터 5만 건 생성 중 (서울 근방)...")
    routes = []
    # 서울 시청 중심 (37.5665, 126.9780)
    for i in range(50000):
        user_id = random.randint(100000000, 100099999)
        status = random.choice(['PUBLIC', 'PUBLIC', 'PRIVATE'])
        
        # 간단한 2개 점으로 된 LineString 생성
        lat1 = 37.4 + random.random() * 0.4
        lon1 = 126.7 + random.random() * 0.5
        lat2 = lat1 + 0.01
        lon2 = lon1 + 0.01
        
        wkt = f'LINESTRING({lon1} {lat1}, {lon2} {lat2})'
        routes.append((user_id, status, wkt))

    # %s 플레이스홀더 오류 수정: template 인자 활용
    execute_values(cur, 
        "INSERT INTO routes (user_id, status, summary_path) VALUES %s", 
        routes, 
        template="(%s, %s, ST_GeogFromText(%s))",
        page_size=2000)

    # route_stats 데이터 생성 (routes 데이터 기반)
    print("4. 코스 통계 데이터 생성 중...")
    cur.execute("SELECT id FROM routes")
    route_ids = [row[0] for row in cur.fetchall()]
    stats = []
    for rid in route_ids:
        views = random.randint(0, 1000)
        downloads = random.randint(0, int(views * 0.1)) # 다운로드는 조회수의 10% 정도
        stats.append((rid, views, downloads))
    
    execute_values(cur,
        "INSERT INTO route_stats (route_id, view_count, download_count) VALUES %s",
        stats, page_size=5000)
    
    conn.commit()
    print("데이터 삽입 완료. ANALYZE 실행 중...")
    cur.execute("ANALYZE users; ANALYZE routes;")
    conn.commit()
    cur.close()
    conn.close()

def run_benchmarks():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    print("\n=== [TEST 1] 로그인 쿼리 분석 (status, email) ===")
    target_email = "rider_99999@example.com"
    cur.execute(f"EXPLAIN ANALYZE SELECT * FROM users WHERE status = 'ACTIVE' AND email = '{target_email}';")
    for row in cur.fetchall():
        print(row[0])

    print("\n=== [TEST 2] 내 주변(5km) 코스 검색 (GIST) ===")
    # 서울 도심의 특정 포인트
    ref_lon, ref_lat = 126.9780, 37.5665 
    cur.execute(f"""
        EXPLAIN ANALYZE 
        SELECT id, status 
        FROM routes 
        WHERE ST_DWithin(summary_path, ST_Point({ref_lon}, {ref_lat})::geography, 5000); -- 형변환 없이 바로 비교
    """)
    for row in cur.fetchall():
        print(row[0])

    print("\n=== [TEST 3] 가중치 랭킹 검색 (거리 + 인기) ===")
    # 내 위치 반경 5km 내 코스 중 (조회수 + 다운로드*5) 점수가 높은 순으로 20개
    # 거리(m)가 멀수록 점수 감점 (Distance Decay)
    cur.execute(f"""
        EXPLAIN ANALYZE 
        SELECT r.id, r.title, s.view_count, 
               ST_Distance(r.summary_path, ST_Point({ref_lon}, {ref_lat})::geography) as dist_m,
               (s.view_count + s.download_count * 5) / (ST_Distance(r.summary_path, ST_Point({ref_lon}, {ref_lat})::geography) + 1) as score
        FROM routes r
        JOIN route_stats s ON r.id = s.route_id
        WHERE ST_DWithin(r.summary_path, ST_Point({ref_lon}, {ref_lat})::geography, 5000)
        ORDER BY score DESC
        LIMIT 20;
    """)
    for row in cur.fetchall():
        print(row[0])

    cur.close()
    conn.close()

if __name__ == "__main__":
    try:
        setup_db()
        seed_data()
        run_benchmarks()
    except Exception as e:
        print(f"Error: {e}")
        print("\n[도움말] 테스트를 위해 Docker가 실행 중이어야 합니다.")
        print("명령어: docker run --name pg_perf_test -e POSTGRES_PASSWORD=password -d -p 5433:5432 postgis/postgis:15-3.3")
