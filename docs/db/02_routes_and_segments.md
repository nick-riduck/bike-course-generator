# Database Schema Design: Routes & Segments

## 1. 개요 및 서비스 목표
이 문서는 **GPX 코스 생성기 및 물리 시뮬레이터**의 핵심인 코스(Route)와 구간(Segment) 데이터를 정의합니다.

### 핵심 설계 원칙 (Design Principles)
1.  **성능 및 유연성 (Performance & Flexibility):**
    *   내부 조인용 PK로 `BIGINT`를 사용하여 인덱스 크기를 줄이고 검색 성능을 확보합니다.
    *   **Loose Coupling:** 개발 편의성과 확장성을 위해 물리적 FK(Foreign Key) 제약조건은 배제하고, 논리적으로만 관리합니다.
2.  **지리 정보 최적화 (Spatial):** PostGIS의 `GEOMETRY` 타입을 활용하되, 공간 인덱스(`GIST`)를 통해 "내 주변 검색" 성능을 극대화합니다.
3.  **데이터 일관성:** `ENUM`을 사용하여 코스 상태를 관리하고, 모든 입력 데이터는 Valhalla를 통해 표준화된 포맷으로 정제합니다.

---

## 2. Schema Definition

### 2.1 Routes (코스 메타데이터)
**역할:** 코스 목록, 검색, 공유의 단위.

```sql
-- 코스 상태 ENUM
CREATE TYPE route_status AS ENUM ('PUBLIC', 'PRIVATE', 'LINK_ONLY', 'DELETED');

CREATE TABLE routes (
    -- [PK] 내부 성능 최적화용 ID (Auto Increment)
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    
    -- [Public ID] 공유용 식별자
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    
    -- [Display ID] URL용 짧은 ID
    route_num SERIAL UNIQUE NOT NULL,

    -- 작성자 ID (논리적 연동, FK 제약 없음)
    user_id BIGINT NOT NULL,

    -- [Forking] 원본 코스 추적 (Optional)
    parent_route_id BIGINT,

    -- 기본 정보
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status route_status DEFAULT 'PUBLIC' NOT NULL,

    -- [Media] 미리보기 썸네일 (Static Image URL) - 리스트 렌더링 성능 최적화
    thumbnail_url VARCHAR(255),

    -- [Official] 공식 인증/추천 코스 여부
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,

    -- [Storage] 상세 데이터 파일 경로 (JSON)
    data_file_path TEXT NOT NULL,

    -- [Spatial] 지리 정보 (PostGIS)
    -- 성능 최적화를 위해 GEOMETRY 타입(평면 좌표) 사용
    -- *거리 계산 시 주의:* 정확한 미터(m) 단위 계산이 필요할 경우, 쿼리 레벨에서 
    -- 'Hybrid Query Pattern' (Box Search로 1차 필터링 -> Geography Casting으로 2차 정밀 계산)을 사용해야 함.
    summary_path GEOMETRY(LineString, 4326),
    start_point GEOMETRY(Point, 4326),

    -- 통계 정보
    distance INTEGER NOT NULL,          -- meters
    elevation_gain INTEGER NOT NULL,    -- meters
    
    -- 메타 데이터
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index 1: "내 코스" 목록 조회 (WHERE status != 'DELETED' AND user_id = ?)
CREATE INDEX idx_routes_status_user ON routes(status, user_id);

-- Index 2: 코스 목록 정렬 (WHERE status != 'DELETED' ORDER BY created_at DESC)
CREATE INDEX idx_routes_status_created ON routes(status, created_at DESC);

-- Spatial Index: "내 주변 코스" 공간 검색 (ST_DWithin)
CREATE INDEX idx_routes_summary_path ON routes USING GIST (summary_path);
```

### 2.2 RouteStats (코스 통계)
```sql
CREATE TABLE route_stats (
    -- route_id (논리적 연동)
    route_id BIGINT PRIMARY KEY,
    view_count INTEGER DEFAULT 0 NOT NULL,
    download_count INTEGER DEFAULT 0 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 2.3 Segments (표준 구간 정보)
**역할:** "남산", "북악" 등 고정된 표준 구간 정의.

```sql
CREATE TABLE segments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    
    creator_id BIGINT, -- 등록자 ID
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    
    -- [Spatial] 표준 폴리라인 정보
    geometry GEOMETRY(LineString, 4326),
    start_point GEOMETRY(Point, 4326),
    end_point GEOMETRY(Point, 4326),

    -- 구간 통계
    length INTEGER NOT NULL,
    avg_grade FLOAT NOT NULL,
    elevation_gain INTEGER NOT NULL,
    
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Spatial Index: 내 주변 업힐 검색 최적화
CREATE INDEX idx_segments_start_point ON segments USING GIST (start_point);
```

### 2.4 RouteSegments (관계 매핑)
```sql
CREATE TABLE route_segments (
    route_id BIGINT NOT NULL,
    segment_id BIGINT NOT NULL,
    sequence INTEGER NOT NULL,
    start_index INTEGER NOT NULL, 
    end_index INTEGER NOT NULL,
    
    -- [PK 변경] (route_id, segment_id) -> (route_id, sequence)
    -- 사유: 인터벌 코스나 순환 코스처럼 동일한 세그먼트를 여러 번 타는 경우를 지원하기 위함
    PRIMARY KEY (route_id, sequence)
);
```

---

## 3. 태그 및 다국어 지원 (Tags)
```sql
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    names JSONB NOT NULL, -- {"ko": "한강", "en": "Han River"}
    slug VARCHAR(50) UNIQUE NOT NULL,

    -- 태그 유형 (Optional): 'GENERAL', 'AUTO_GENERATED' (e.g., 'HC', 'CAT1' 등 등급 자동 부여)
    type VARCHAR(20) DEFAULT 'GENERAL',

    -- 시맨틱 검색용 임베딩 (gemini-embedding-001, 3072차원)
    -- halfvec(float16): HNSW 인덱스 지원 (vector float32는 2,000차원 제한)
    -- 벤치마크 결과: Recall 100%, 쿼리 ~8ms@5K (docs/db/benchmark_vector_index.md)
    embedding halfvec(3072),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 시맨틱 태그 검색용 HNSW 인덱스 (cosine distance)
CREATE INDEX idx_tags_embedding ON tags
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE TABLE route_tags (
    route_id BIGINT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (route_id, tag_id)
);

-- PK (route_id, tag_id)는 route_id → tag_id 방향만 커버.
-- 태그 필터링/태그 클라우드는 tag_id → route_id 방향 조인이므로 별도 인덱스 필요.
CREATE INDEX idx_route_tags_tag_id ON route_tags(tag_id);
```

---

## 4. Waypoints (POI 참조 데이터)

코스 경로 주변의 유명 장소(POI) 데이터. 자동 태그/설명 생성 시 LLM 컨텍스트로 활용.
데이터 소스: Komoot 크롤링 → 중복 병합 → Gemini 보강.

### 4.1 waypoint_type ENUM
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

### 4.2 waypoints 테이블
```sql
CREATE TABLE waypoints (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT DEFAULT '',
    type waypoint_type[] NOT NULL DEFAULT '{}',   -- ENUM 배열 (복수 타입 가능: {bridge, viewpoint})
    location GEOMETRY(Point, 4326),
    is_verified BOOLEAN DEFAULT FALSE,
    etc JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_waypoints_location ON waypoints USING GIST (location);
CREATE INDEX idx_waypoints_type ON waypoints USING GIN (type);
```

`etc` JSONB 구조:
```json
{
  "source": "KOMOOT",
  "source_ids": ["1020499", "1250365"],
  "image_urls": ["https://..."],
  "tips": [{"text": "...", "author": "..."}],
  "category_raw": "facilities",
  "tour_count": 5
}
```

### 4.3 route_waypoints 테이블 (관계 매핑)
```sql
CREATE TABLE route_waypoints (
    route_id BIGINT NOT NULL,
    waypoint_id BIGINT NOT NULL,
    sequence INTEGER NOT NULL,
    distance_from_start INTEGER,       -- 시작점에서의 거리 (meters)
    PRIMARY KEY (route_id, waypoint_id)
);
```

---

## 5. Route Data JSON Format (JSON 상세 스펙)
> **[CRITICAL WARNING]** 이 JSON 구조는 프론트엔드 렌더링, 고도 차트 생성, 그리고 **물리 엔진 시뮬레이터**의 핵심 입력 데이터입니다. 
> 백엔드 및 시뮬레이터 개발 시 이 형식을 엄격히 준수해야 하며, **절대로 이 섹션을 삭제하거나 임의로 변경하지 마십시오.**

이 데이터는 `routes.data_file_path`에 저장되는 상세 JSON의 표준 포맷입니다.

```json
{
  "version": "1.0",
  "meta": {
    "creator": "Riduck Engine",
    "surface_map": {
      "0": "unknown", "1": "asphalt", "2": "concrete", 
      "3": "wood_metal", "4": "paving_stones", "5": "cycleway", 
      "6": "compacted", "7": "gravel_dirt"
    }
  },
  "stats": {
    "distance": 2500.5,      // 총 거리 (m)
    "ascent": 152,           // 총 획득고도 (m)
    "descent": 10,           // 총 하강고도 (m)
    "points_count": 1250,    // 전체 포인트 수
    "segments_count": 45     // 생성된 세그먼트 수
  },
  
  // 1. 점 데이터 (지도 렌더링 & 고해상도 차트용)
  // Columnar 포맷으로 용량 최적화 및 프론트엔드 연산 부하 감소
  "points": {
    "lat": [37.123456, ...],  // 위도
    "lon": [127.123456, ...], // 경도
    "ele": [50.5, ...],       // 고도 (m)
    "dist": [0.0, 15.2, ...], // 누적 거리 (m)
    "grade": [0.5, 0.5, ...], // 순간 경사도 (지도 색상용)
    "surf": [1, 1, ...]       // 노면 ID (meta.surface_map 참조)
  },

  // 2. 물리 엔진용 요약 구간 (Simulation Atomic Segments)
  // 시뮬레이터는 points를 순회하지 않고 이 segments 데이터만 보고 즉시 계산 수행
  "segments": {
    "p_start": [0, 15, ...],   // points 리스트 내 시작 인덱스
    "p_end": [15, 32, ...],    // points 리스트 내 끝 인덱스
    "length": [240.5, 120.0, ...], // 구간 길이 (m)
    "avg_grade": [0.052, ...], // 구간 평균 경사도 (소수점)
    "surf_id": [1, 5, ...],    // 구간 노면 ID
    "avg_head": [180.5, ...]   // 구간 평균 방위각 (degrees)
  },
  

  // 4. [New] 프론트엔드 편집기 상태 복구용 데이터 (Editor State)
  // 시뮬레이터는 이 필드를 무시하며, 생성기에서 코스를 다시 불러올 때만 사용함
  "editor_state": {
    "sections": [
      {
        "id": "s1_uuid",
        "name": "Section 1",
        "color": "#2a9e92",
        "points": [
          {"id": "p1", "lng": 127.0, "lat": 37.5, "type": "start", "name": "Start"},
          {"id": "p2", "lng": 127.1, "lat": 37.6, "type": "via", "name": ""}
        ],
        "segments": [
          {
            "id": "seg1",
            "startPointId": "p1",
            "endPointId": "p2",
            "distance": 1.2,
            "ascent": 10,
            "type": "api"
          }
        ]
      }
    ]
  }
}
```

### 💡 데이터 생성 규칙 (Generation Rules)
*   **자동 경로 탐색 모드:** Valhalla의 `trace_attributes` API를 사용하여 포인트별 고도 및 노면 정보를 획득합니다.
*   **수동 그리기 모드 (직선):** 
    *   두 점 사이를 일정 간격으로 보간(Interpolation)하여 포인트를 생성합니다.
    *   **고도:** Valhalla `/height` API를 통해 각 보간 지점의 지형 고도를 채웁니다.
    *   **노면:** 도로 매칭이 불가능한 구간이므로 기본적으로 `0 (unknown)`을 할당합니다.

