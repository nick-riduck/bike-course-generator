# Development Phase: Temporary Auth Mapping

## 1. 개요 (Background)
본 문서는 `라이덕(Riduck)` 서버 연동이 완료되기 전까지, **Firebase Auth** 등 외부 인증 수단을 활용하여 개발 및 테스트를 진행하기 위한 임시 매핑 전략을 정의합니다.

### 설계 목표
1.  **기존 스키마 보호:** `users` 테이블의 `riduck_id` 등 핵심 구조를 변경하지 않고 유지합니다.
2.  **유연한 연동:** Firebase UID뿐만 아니라 향후 추가될 수 있는 다양한 임시 인증 수단을 수용합니다.
3.  **손쉬운 제거:** 라이덕 연동 완료 시, 해당 테이블을 삭제(Drop)하는 것만으로 임시 로직을 걷어낼 수 있게 설계합니다.

---

## 2. Schema Definition

### 2.1 auth_mapping_temp (임시 인증 매핑)
**역할:** 외부 인증 제공자(Provider)의 식별자와 서비스 내부 `user_id`를 연결합니다.

```sql
CREATE TABLE auth_mapping_temp (
    -- [PK] 복합키: 어떤 서비스의 어떤 유저인지 정의
    -- B-Tree 인덱스가 자동으로 생성되어 조회 성능 확보
    provider VARCHAR(50) NOT NULL,      -- 예: 'FIREBASE', 'GOOGLE', 'TEST'
    provider_uid VARCHAR(128) NOT NULL, -- 제공자가 발급한 고유 식별자

    -- [FK] 내부 서비스 User ID (users.id 참조)
    -- 논리적 연결만 유지 (개발 단계의 편의성을 위해 물리적 FK 생략 가능)
    user_id BIGINT NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (provider, provider_uid)
);
```

---

## 3. 데이터 흐름 (Data Flow)

### 3.1 로그인 및 회원가입 (Firebase 기준)
1.  **Frontend:** Firebase 로그인 성공 후 `id_token` 획득.
2.  **Backend:** 토큰 검증 후 `provider='FIREBASE'`, `provider_uid='abc-123'` 추출.
3.  **Backend:** `auth_mapping_temp`에서 조회.
    *   **Case A (기존 유저):** 매핑된 `user_id`를 가져와 세션/JWT 발급.
    *   **Case B (신규 유저):** 
        1. `users` 테이블에 신규 레코드 생성 (이때 `riduck_id`는 임시 음수값 또는 Dummy 값 할당).
        2. 생성된 `user_id`와 함께 `auth_mapping_temp`에 매핑 정보 저장.

### 3.2 라이덕 연동 전환 시나리오 (Future)
1.  라이덕 서버로부터 실제 `real_riduck_id`를 획득합니다.
2.  `users` 테이블의 해당 레코드를 업데이트합니다:
    ```sql
    UPDATE users SET riduck_id = [real_riduck_id] WHERE id = [user_id];
    ```
3.  연동이 완료된 사용자는 더 이상 `auth_mapping_temp`가 필요 없으므로 삭제하거나 무시할 수 있습니다.
