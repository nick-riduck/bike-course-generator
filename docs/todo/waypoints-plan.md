# 자동 태그/설명 생성을 위한 Waypoints DB 설계 및 구현

## Context
유저가 코스 생성 시 자동 태그/설명을 생성하려면, 코스 경로 주변의 **유명 장소(POI)** 데이터가 필요함.
현재 DB에는 routes(선), segments(선)만 있고 **점(Point) 기반 참조 데이터**가 없음.
Komoot 크롤링 waypoint 데이터를 DB에 저장하고, 유저 코스 경로와 공간 매칭하여 LLM 프롬프트 컨텍스트로 활용.

---

## Step 1: DB 스키마 변경 (`backend/init_db.py`)

### 1a. 기존 테이블에 `etc JSONB` 추가
```sql
-- routes 테이블에 추가
etc JSONB DEFAULT '{}'::jsonb,

-- segments 테이블에 추가
etc JSONB DEFAULT '{}'::jsonb,
```

### 1b. ENUM 타입
```sql
CREATE TYPE waypoint_type AS ENUM (
    -- 보급/편의
    'convenience_store', 'cafe', 'restaurant', 'restroom',
    'water_fountain', 'rest_area', 'bike_shop',
    -- 인프라
    'parking', 'transit', 'bridge', 'tunnel', 'checkpoint',
    -- 자연/경관
    'viewpoint', 'river', 'lake', 'mountain', 'beach', 'park', 'nature',
    -- 문화/관광
    'historic', 'landmark', 'museum',
    -- 안전
    'hospital', 'police',
    -- 기타
    'other'
);
```

### 1c. 새 테이블: `waypoints`
```sql
CREATE TABLE waypoints (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT DEFAULT '',
    type waypoint_type[] NOT NULL DEFAULT '{}',   -- ENUM 배열! {bridge, viewpoint} 가능
    location GEOMETRY(Point, 4326),
    is_verified BOOLEAN DEFAULT FALSE,
    etc JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_waypoints_location ON waypoints USING GIST (location);
CREATE INDEX idx_waypoints_type ON waypoints USING GIN (type);
```

`etc` JSONB 예시:
```json
{"source": "KOMOOT", "source_id": "1250365", "image_url": "https://...", "tips": [...]}
```

### 1d. 새 테이블: `route_waypoints`
```sql
CREATE TABLE route_waypoints (
    route_id BIGINT NOT NULL,
    waypoint_id BIGINT NOT NULL,
    sequence INTEGER NOT NULL,
    distance_from_start INTEGER,       -- 시작점에서의 거리 (meters). "12.3km 지점에 카페" 설명 생성용
    PRIMARY KEY (route_id, waypoint_id)
);
```

---

## Step 2: Komoot Waypoint Import (`scripts/import_komoot_waypoints.py`)

**LLM 기반 파싱으로 별도 진행 예정**

komoot metadata.json의 waypoints 데이터를 LLM으로 파싱하여:
- 카테고리 매핑 (komoot code → waypoint_type ENUM 배열)
- 중복 체크: `LOWER(name)` + `ST_DWithin(200m)`
- `--dry-run`, `--output-sql` 지원

---

## Step 3: 공간 쿼리 API (`backend/app/routers/waypoints.py`)

### `POST /api/waypoints/along-route`
코스 좌표 배열 → 경로 주변 500m 이내 waypoint 반환.
기존 `routes/nearby`의 hybrid 공간 쿼리 패턴(GEOMETRY bbox + GEOGRAPHY meter) 사용.

### `GET /api/waypoints/nearby?lat=&lon=&radius=`
단일 좌표 근접 검색 (맵 표시용, 향후).

`backend/app/main.py`에 라우터 등록.

---

## 수정 대상 파일
| 파일 | 변경 |
|------|------|
| `backend/init_db.py` | routes/segments에 etc 추가, waypoint_type ENUM, waypoints, route_waypoints DDL |
| `scripts/import_komoot_waypoints.py` | **신규** - komoot waypoint import (LLM 파싱, 별도 진행) |
| `backend/app/routers/waypoints.py` | **신규** - 공간 쿼리 API |
| `backend/app/main.py` | waypoints 라우터 등록 |

## 검증
1. `python backend/init_db.py` → 테이블 생성 확인
2. `psql` → waypoints, route_waypoints 테이블 구조 확인
3. 테스트 INSERT → waypoint_type[] ENUM 배열 동작 확인
4. `curl -X POST /api/waypoints/along-route` → 공간 쿼리 테스트
