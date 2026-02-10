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

    -- 기본 정보
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status route_status DEFAULT 'PUBLIC' NOT NULL,

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

-- Index 1: 상태와 작성자를 결합한 복합 인덱스 (멘토 피드백 반영: status 선행)
-- 예: 내 코스 목록 보기, 공개된 최신 코스 보기
CREATE INDEX idx_routes_status_user ON routes(status, user_id);
CREATE INDEX idx_routes_status_created ON routes(status, created_at DESC);

-- Spatial Index: 공간 검색용 (GIST)
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE route_tags (
    route_id BIGINT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (route_id, tag_id)
);
```
