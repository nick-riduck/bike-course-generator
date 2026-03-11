# Database Schema Design: Embedding Cache

## 1. 개요 및 서비스 목표
이 문서는 사용자의 검색어나 특정 텍스트를 LLM(Gemini) 임베딩 벡터로 변환할 때 발생하는 네트워크 딜레이(200~300ms)와 API 호출 비용을 최소화하기 위한 캐싱 구조를 정의합니다.

### 핵심 설계 원칙 (Design Principles)
1.  **성능 및 인프라 제약 (Performance & Infrastructure Constraints):**
    *   현재 인프라(Cloud Run + e2-standard-2 VM)에서는 메모리 제약(8GB)과 Scale to Zero 특성으로 인해 파이썬 내장 `lru_cache`나 Redis와 같은 외부 인메모리 캐시 도입이 오히려 시스템 불안정(OOM)이나 초기 지연을 유발할 수 있습니다.
    *   이에 따라 이미 안정적으로 운영 중이고 영구적 보존이 가능한 **PostgreSQL DB를 캐시 스토어로 활용**합니다.
2.  **확장성 (Scalability):**
    *   향후 트래픽 증가로 Redis 등 전문 캐싱 솔루션 도입이 필요해질 때를 대비하여, 백엔드 로직에 `query_cache`와 `set_cache` 함수를 추상화하여 분리해 둡니다.
3.  **모니터링 (Monitoring):**
    *   캐시 히트율(Hit Rate)을 분석할 수 있도록, 캐시 히트/미스 시 1줄짜리 로그를 출력하여 추후 통계 분석에 활용합니다.

---

## 2. Schema Definition

### 2.1 search_query_cache (검색어 임베딩 캐시 테이블)
**역할:** 한 번 검색된 단어의 임베딩 값을 저장하여, 다음 검색 시 1ms 이내로 즉시 응답할 수 있도록 합니다.

```sql
CREATE TABLE search_query_cache (
    -- [PK] 사용자가 입력한 검색어 자체를 PK로 사용하여 자동 인덱싱 및 빠른 조회 보장
    query VARCHAR(255) PRIMARY KEY,
    
    -- 시맨틱 검색용 임베딩 (gemini-embedding-001, 3072차원)
    -- 다른 테이블(tags 등)과 동일한 halfvec(float16) 포맷 사용
    embedding halfvec(3072),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 인덱스 및 동시성 고려
- `query` 컬럼을 `PRIMARY KEY`로 설정하여 자연스럽게 B-Tree 인덱스가 생성되므로 빠른 조회가 가능합니다.
- 복수의 사용자가 동시에 동일한 검색어를 입력했을 때 발생할 수 있는 캐시 쓰기 충돌을 방지하기 위해 `ON CONFLICT (query) DO NOTHING` 절을 사용하여 예외를 처리합니다.

---

## 3. 구조적 시사점
*   이 캐시 구조는 AI 기능을 활용하는 아키텍처에서 흔히 사용되는 **Memoization(메모이제이션) 패턴**의 실용적인 구현체입니다.
*   자주 변하지 않는 텍스트-벡터 쌍의 특성을 고려하여, 인프라의 복잡도를 높이지 않고도 300ms의 네트워크 딜레이를 0~1ms 수준으로 단축시키는 높은 효율성을 제공합니다.
