# Authentication Implementation Guide

본 문서는 현재 프로젝트(`bike_course_generator`)에 적용된 **Firebase 기반 임시 인증 및 유저 매핑 로직**을 상세히 기술합니다.  
다른 프로젝트(예: `riduck-backend`, Admin Tool 등)에서도 동일한 로직을 적용하여 `auth_mapping_temp`를 통해 유저를 식별하고 데이터를 공유할 수 있도록 설계되었습니다.

---

## 0. 전제 조건 (Prerequisites)

이 인증 체계가 여러 프로젝트 간에 정상적으로 동작하기 위해서는 다음 조건이 충족되어야 합니다.

1.  **Shared Firebase Project:** 모든 클라이언트(웹/앱)와 백엔드 서비스는 **동일한 Firebase 프로젝트**를 사용해야 합니다. 그래야 동일한 유저에 대해 동일한 `uid`(Firebase User ID)가 발급됩니다.
2.  **Shared Database:** 모든 백엔드 서비스는 **동일한 PostgreSQL 데이터베이스 인스턴스**의 `users` 및 `auth_mapping_temp` 테이블을 참조해야 합니다.

---

## 1. 아키텍처 개요 (Architecture Overview)

현재 개발 단계에서는 라이덕(Riduck)의 본 서비스 통합 전이므로, **Firebase Authentication**을 IdP(Identity Provider)로 사용합니다.  
하지만 내부 로직은 `users` 테이블의 `id` (BigInt)를 기준으로 동작하며, **Firebase UID**와 **내부 User ID**를 매핑하는 중간 계층을 둡니다.

### 핵심 포인트
1.  **Client:** Firebase SDK를 통해 로그인하고 `id_token`을 발급받습니다.
2.  **Backend:** `id_token`을 검증하고, `auth_mapping_temp` 테이블을 조회하여 내부 `user_id`를 찾습니다.
3.  **Database:** 외부 인증 정보는 `auth_mapping_temp`에만 저장하고, 비즈니스 로직은 `users` 테이블만 참조합니다.

---

## 2. 데이터베이스 스키마 (Database Schema)

### 2.1 Users 테이블 (Core)
서비스의 핵심 유저 정보입니다. 라이덕 연동 전까지 `riduck_id`는 음수 값(Negative Integer)을 사용하여 임시 유저임을 표시합니다.

```sql
CREATE TABLE users (
    -- [PK] 내부 식별자 (1억부터 시작)
    id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 100000000) PRIMARY KEY,
    
    -- [Public ID] 외부 노출용 UUID
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    
    -- [Riduck ID] 라이덕 연동 키 (임시 유저는 음수 값 사용)
    riduck_id INTEGER UNIQUE,
    
    username VARCHAR(50) NOT NULL,
    email VARCHAR(255),
    profile_image_url VARCHAR(255),
    status user_status DEFAULT 'ACTIVE' NOT NULL,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 Auth Mapping Temp 테이블 (Bridge)
Firebase UID와 내부 User ID를 연결합니다.

```sql
CREATE TABLE auth_mapping_temp (
    -- [PK] 복합키: Provider + UID
    provider VARCHAR(50) NOT NULL,      -- 예: 'FIREBASE'
    provider_uid VARCHAR(128) NOT NULL, -- 예: 'firebase_uid_abc123'

    -- [FK] Users 테이블 참조
    user_id BIGINT NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, provider_uid)
);
```

---

## 3. 인증 상세 로직 (Implementation Details)

### 3.1 로그인 및 회원가입 (Login / Registration)
**Endpoint:** `POST /api/auth/login`

1.  **Client:** Firebase 로그인 성공 후 `id_token`을 헤더나 바디에 실어 서버로 전송.
2.  **Server (Verification):** Firebase Admin SDK로 토큰 검증 (`auth.verify_id_token`).
3.  **Server (Lookup):** `auth_mapping_temp`에서 `provider='FIREBASE'` AND `provider_uid={uid}` 조회.
    *   **Case A: 매핑 존재 (기존 유저)**
        *   매핑된 `user_id`로 `users` 테이블 정보를 반환.
    *   **Case B: 매핑 없음 (신규 유저)**
        1.  `users` 테이블에서 가장 작은 음수 `riduck_id` 조회 (예: -5).
        2.  새 `riduck_id` 할당 (예: -6).
        3.  `users` 테이블에 신규 레코드 `INSERT`.
        4.  `auth_mapping_temp` 테이블에 `(FIREBASE, uid, new_user_id)` 매핑 `INSERT`.
        5.  생성된 유저 정보 반환.

### 3.2 인증된 요청 처리 (Authenticated Requests)
**Header:** `Authorization: Bearer {firebase_id_token}`

1.  **Middleware / Dependency:**
    *   모든 인증이 필요한 API 요청마다 헤더의 토큰을 파싱.
    *   Firebase Admin SDK로 토큰 유효성 및 만료 확인.
    *   토큰에서 추출한 `uid`로 `auth_mapping_temp`를 조회하여 `user_id` 획득.
    *   API 핸들러에는 `user_id` (BigInt)를 전달.

---

## 4. 코드 구현 예시 (Code Examples)

### 4.1 Backend (Python/FastAPI)

```python
# backend/main.py 발췌 및 요약

from firebase_admin import auth
from fastapi import Header, HTTPException

# 1. Firebase Admin 초기화
import firebase_admin
firebase_admin.initialize_app()

# 2. 유저 식별 Dependency
async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid header")
    
    token = authorization.split(" ")[1]
    try:
        # A. 토큰 검증
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        
        # B. DB 매핑 조회
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id FROM auth_mapping_temp WHERE provider = 'FIREBASE' AND provider_uid = %s",
            (uid,)
        )
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=401, detail="User not found")
            
        return row['user_id'] # 내부 로직용 ID 반환
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
```

### 4.2 Frontend (React)

```javascript
// frontend/src/AuthContext.jsx 발췌

import { onAuthStateChanged } from 'firebase/auth';
import { auth } from './firebase';

// 1. Firebase 상태 감지 및 백엔드 동기화
useEffect(() => {
  const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
    if (firebaseUser) {
      const idToken = await firebaseUser.getIdToken();
      
      // 백엔드에 로그인/가입 요청 (매핑 생성용)
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id_token: idToken }),
      });
      
      // 이후 모든 요청에 Token 포함
      // fetch('/api/routes', { headers: { 'Authorization': `Bearer ${idToken}` } })
    }
  });
  return unsubscribe;
}, []);
```

---

## 5. 환경 설정 가이드 (Configuration Guide)

다른 프로젝트에서 이 인증 모듈을 사용하기 위해 필요한 환경 변수 및 파일 설정입니다.

### 5.1 Backend (.env)
Firebase Admin SDK 초기화를 위해 서비스 계정 키(Service Account Key)가 필요할 수 있습니다. (GCP 환경에서는 자동 감지될 수 있음)

```ini
# Database Connection (반드시 동일한 DB를 바라봐야 함)
DB_HOST=shared-db-instance.riduck.com
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=secret_password
DB_NAME=riduck_core

# Firebase Admin SDK
# 로컬 개발 시: 다운로드 받은 JSON 키 파일 경로
GOOGLE_APPLICATION_CREDENTIALS="./config/firebase-service-account.json"

# GCP 배포 시: 환경 변수 없이 IAM 권한으로 자동 처리 권장
```

### 5.2 Frontend (.env)
클라이언트 사이드 인증을 위한 Firebase 설정입니다.
**이 프로젝트(`bike_course_generator`)와 동일한 Firebase 프로젝트를 사용해야 하므로, 설정값도 동일하게 맞춰야 합니다.**

현재 잘 작동하고 있는 `bike_course_generator/frontend/.env` 파일의 내용을 **그대로 복사**하여, 타 프로젝트(예: `riduck-front` 등)의 `.env` 파일에 붙여넣으십시오.

```ini
# 아래 값들은 예시입니다. 
# 실제 값은 bike_course_generator/frontend/.env 파일에서 복사하세요.

VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_STORAGE_BUCKET=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...
```

---

## 6. 향후 마이그레이션 (Migration Strategy)

라이덕 본 서버와 연동이 완료되는 시점(`Development` -> `Production`)에는 다음 절차를 따릅니다.

1.  **Riduck ID 매핑:** 라이덕 서버 API를 통해 실제 유저의 `real_riduck_id`를 받아옵니다.
2.  **데이터 업데이트:**
    ```sql
    UPDATE users 
    SET riduck_id = {real_riduck_id} 
    WHERE id = {local_user_id};
    ```
3.  **테이블 정리:** `auth_mapping_temp` 테이블은 더 이상 필요하지 않으므로 백업 후 삭제하거나, 레거시 지원을 위해 유지할 수 있습니다.
