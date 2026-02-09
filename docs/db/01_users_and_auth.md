# Database Schema Design: Users & Authentication

## 1. 개요 및 설계 목표
이 문서는 `GPX 코스 생성기` 및 `시뮬레이터` 서비스를 위한 사용자(User) 및 인증(Authentication) 스키마를 정의합니다.

### 핵심 설계 원칙 (Design Principles)
1.  **성능 최적화 (Performance):** 내부 조인 성능을 위해 PK는 `BIGINT`를 사용하고, API 노출용으로 별도의 `UUID`를 사용합니다.
2.  **데이터 무결성 및 상태 관리:** 사용자 상태(`ACTIVE`, `BANNED`, `DELETED`)를 명시적으로 관리하고, 제한된 값은 `ENUM`을 사용하여 데이터 오염을 방지합니다.
3.  **확장성(Scalability):** 라이덕 계정(`riduck_id`)과의 충돌을 피하기 위해 내부 ID는 1억부터 시작하며, 인증 토큰은 별도 테이블로 분리합니다.

---

## 2. Schema Definition

### 2.1 Users (사용자 정보)
**역할:** 서비스 내부 계정 관리.
**피드백 반영:** UUID PK의 성능 이슈(인덱스 크기, 정렬, INSERT 속도)를 해결하기 위해 내부 식별자는 `BIGINT`를 사용합니다.

```sql
-- 사용자 상태 ENUM 정의
CREATE TYPE user_status AS ENUM ('ACTIVE', 'BANNED', 'PENDING_DELETION', 'DELETED');

CREATE TABLE users (
    -- [PK] 내부 조인용 고성능 ID (Auto Increment)
    -- 라이덕 레거시 ID와의 충돌 방지 및 구분을 위해 1억(100,000,000)부터 시작
    id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 100000000) PRIMARY KEY,

    -- [Public ID] 외부 API 노출용 식별자 (보안 강화)
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,

    -- [Unique] 라이덕 서비스 연동 키
    riduck_id INTEGER UNIQUE NOT NULL,

    -- 기본 정보
    username VARCHAR(50) NOT NULL,
    email VARCHAR(255),
    
    -- 계정 상태 (가입, 정지, 탈퇴 등)
    status user_status DEFAULT 'ACTIVE' NOT NULL,

    -- 메타 데이터
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index 1: 계정 상태와 이메일을 결합한 복합 인덱스
-- 멘토 피드백 반영: 범위가 넓은 status를 앞에 두어 관리자 조회 등 다양한 쿼리에서 인덱스를 재사용할 수 있도록 설계
-- 예: SELECT * FROM users WHERE status = 'ACTIVE' AND email = ?
CREATE INDEX idx_users_status_email ON users(status, email);

-- Index 2: 라이덕 ID 조회 및 계정 상태 통합 인덱스
-- 이메일 인덱스와 마찬가지로 status를 선행시켜 범용성을 확보
CREATE INDEX idx_users_status_riduck_id ON users(status, riduck_id);
```

### 2.2 UserTokens (인증 토큰 관리)
**역할:** OAuth 토큰 관리.
**피드백 반영:** `provider`를 `ENUM`으로 제한하여 데이터 정합성을 보장합니다.

```sql
-- 인증 제공자 ENUM 정의
CREATE TYPE auth_provider AS ENUM ('RIDUCK', 'GOOGLE', 'STRAVA');
-- 토큰 상태 ENUM 정의 (멘토 피드백: 이력 관리 및 Soft Delete)
CREATE TYPE token_status AS ENUM ('ACTIVE', 'EXPIRED', 'REVOKED');

CREATE TABLE user_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 소유자 (Users 테이블 FK - BIGINT)
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 인증 제공자 (ENUM 사용으로 입력값 제한)
    provider auth_provider NOT NULL,

    -- Access Token (API 호출용)
    access_token TEXT NOT NULL,

    -- Refresh Token (토큰 갱신용)
    refresh_token TEXT,

    -- 토큰 만료 시점
    expires_at TIMESTAMP WITH TIME ZONE,

    -- 토큰 상태 (활성, 만료, 폐기)
    status token_status DEFAULT 'ACTIVE' NOT NULL,

    -- 토큰 권한 범위 (Scope)
    scope TEXT,

    -- 메타 데이터
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- [정책] Provider당 단일 토큰 세트 유지
    -- 인덱스 순서: (user_id, provider) -> "내 연동 계정 조회" 패턴에 최적화
    UNIQUE(user_id, provider)
);

-- Index 3: API 요청 및 갱신 시 토큰 검증 (Status 선행)
-- "활성 상태인 특정 토큰"을 빠르게 찾기 위함
CREATE INDEX idx_user_tokens_status_access ON user_tokens(status, access_token);
CREATE INDEX idx_user_tokens_status_refresh ON user_tokens(status, refresh_token);
```

---

## 3. 인증 흐름 (Authentication Flow)

### 3.1 로그인 (SSO-like Handoff)
1.  **User Action:** "라이덕으로 로그인" 클릭.
2.  **Riduck Server:** JWT 생성 (Payload: `riduck_id`, `email`, `exp`) 후 리다이렉트.
3.  **Backend:**
    *   JWT 검증.
    *   `riduck_id`로 `users` 조회.
    *   없으면 `INSERT` (ID=1억+), 있으면 `UPDATE` (Last Login).
    *   `status`가 `BANNED` 또는 `DELETED`이면 로그인 거부.

### 3.2 로그아웃 처리 전략
*   **Stateless (JWT):** 클라이언트 측 토큰 삭제. (서버는 만료될 때까지 기다림)
*   **Stateful (DB):** 즉시 무효화가 필요할 경우 `user_tokens` 레코드를 삭제하거나, `token_blacklist` 테이블(Redis)에 추가.
