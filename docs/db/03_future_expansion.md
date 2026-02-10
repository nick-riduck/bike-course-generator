# Future Architecture Strategy: Activity Logging & Segment Matching

## 1. 개요 및 확장 목표
이 문서는 현재 구축된 **정적 코스/구간 데이터(Plan)**를 기반으로, 향후 **사용자 활동 로그(Execution)** 및 **구간 기록 경쟁(Leaderboard)** 기능으로 확장하기 위한 전략과 데이터베이스 설계 방향을 정의합니다.

### 핵심 원칙
1.  **Plan vs Execution 분리:** 계획(Routes/Segments)과 실행(Activities/Efforts)을 명확히 분리하여 데이터 무결성과 성능을 보장합니다.
2.  **불변성(Immutability) 지향:** 세그먼트의 물리적 속성이 변경될 경우, 기존 데이터를 수정하기보다 새로운 버전을 생성하여 과거 기록의 정합성을 유지합니다.
3.  **점진적 확장(Scalability):** 초기에는 새로운 활동에 대해서만 매칭을 수행하고, 향후 필요 시 배치(Batch) 작업을 통해 과거 데이터 재매칭을 지원합니다.

---

## 2. 확장 스키마 설계 (Draft)

### 2.1 Activities (사용자 활동 로그)
**역할:** 사용자가 실제로 수행한 라이딩 기록의 원본 데이터. Strava의 Activity와 유사합니다.

```sql
CREATE TABLE activities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    
    -- [연결 고리] 계획된 코스를 따라 탔다면? (Nullable)
    -- routes 테이블의 BIGINT PK를 참조하여 조인 성능 최적화
    matched_route_id BIGINT, 
    
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    total_time INTEGER NOT NULL,      -- moving_time (초 단위)
    elapsed_time INTEGER NOT NULL,    -- 총 경과 시간 (휴식 포함)
    total_distance INTEGER NOT NULL,  -- 미터 단위
    
    -- [Spatial] 실제 주행 경로 (GPS 로그 원본)
    -- 향후 세그먼트 매칭 및 지도 표시를 위해 필수
    gps_trace GEOMETRY(LineString, 4326),
    
    -- 분석 데이터 (확장성 고려)
    avg_power INTEGER,
    avg_heartrate INTEGER,
    max_speed FLOAT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index: 내 활동 목록 조회 및 시간순 정렬
CREATE INDEX idx_activities_user_date ON activities(user_id, start_time DESC);
-- Spatial Index: "이 지역에서 탄 활동" 검색 (세그먼트 매칭 배치 작업용)
CREATE INDEX idx_activities_gps_trace ON activities USING GIST (gps_trace);
```

### 2.2 Segment Efforts (구간 기록)
**역할:** 특정 세그먼트를 통과한 기록. 리더보드 및 구간 경쟁의 핵심 데이터입니다.

```sql
CREATE TABLE segment_efforts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    
    activity_id BIGINT NOT NULL, -- 어느 라이딩 활동에서 나왔나?
    user_id BIGINT NOT NULL,
    segment_id BIGINT NOT NULL,  -- 어떤 구간을 탔나? (segments.id 참조)
    
    elapsed_time INTEGER NOT NULL, -- 구간 통과 기록 (초)
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- 순위 정보 (선택적: 실시간 산정 vs 저장)
    kom_rank INTEGER, -- 당시 전체 순위
    pr_rank INTEGER,  -- 당시 개인 순위
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index 1: 리더보드 산출 (특정 세그먼트의 기록 순위)
CREATE INDEX idx_segment_efforts_leaderboard ON segment_efforts(segment_id, elapsed_time ASC);

-- Index 2: 내 기록 조회 (특정 세그먼트의 내 기록)
CREATE INDEX idx_segment_efforts_my_history ON segment_efforts(user_id, segment_id, start_time DESC);
```

---

## 3. 세그먼트 버전 관리 및 매칭 전략

### 3.1 문제 상황: 세그먼트 변경
물리적 도로 환경의 변화(공사, 직선화 등)로 인해 세그먼트의 거리나 경로가 변경될 수 있습니다. 이때 기존 세그먼트(`id=100`)를 수정(`UPDATE`)하면 과거 기록과의 형평성 문제가 발생합니다.

### 3.2 해결책: 불변성(Immutability) 및 Soft Delete
세그먼트 수정 요청이 들어오면 다음과 같은 절차를 따릅니다.

1.  **기존 세그먼트 은퇴 (Retire):**
    *   `id=100` 세그먼트의 상태를 `INACTIVE` 또는 `DELETED`로 변경.
    *   기존에 `id=100`에 매핑된 `segment_efforts` 기록은 그대로 보존 (명예의 전당).
    *   새로운 라이딩 활동과는 더 이상 매칭되지 않음.

2.  **신규 세그먼트 생성 (Spawn):**
    *   변경된 정보를 담은 `id=205` 세그먼트를 신규 생성.
    *   이 시점 이후의 라이딩 활동은 `id=205`와 매칭 시작.
    *   결과적으로, 과거 기록과 현재 기록이 서로 다른 `segment_id`를 가지므로 공정한 경쟁이 유지됨.

### 3.3 과거 데이터 재매칭 (Backfilling)
신규 세그먼트(`id=205`) 생성 시, 과거 활동 기록도 이 세그먼트에 포함시키고 싶다면?

1.  **실시간 처리 불가:** 수백만 건의 활동 데이터를 실시간으로 재계산하는 것은 불가능.
2.  **배치 처리 (Batch Processing):**
    *   `activities` 테이블의 공간 인덱스(`GIST`)를 활용하여, 신규 세그먼트 영역(`Buffer`)을 지나간 활동만 빠르게 추출.
    *   추출된 활동들에 대해서만 정밀 매칭 알고리즘 수행.
    *   매칭 성공 시 `segment_efforts`에 `id=205`에 대한 기록 추가.
    *   이 작업은 시스템 부하가 적은 시간대에 비동기(Background Job)로 수행.
