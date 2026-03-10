# 벡터 데이터베이스 및 임베딩 인프라 (Vector Database & Embedding Infrastructure)

## 개요 (Overview)
경로 태그에 대한 시맨틱 검색 및 추천 기능을 지원하기 위해 PostgreSQL 데이터베이스에 벡터 임베딩을 통합합니다. 이 문서는 선택된 인프라, 모델 선택 및 구현 세부 사항을 설명합니다.

## 1. 임베딩 모델 (Embedding Model)
Google Cloud Vertex AI의 **`gemini-embedding-001`** 모델을 사용합니다.

*   **모델 ID:** `gemini-embedding-001`
*   **차원:** 3072 (기본값)
*   **서비스:** Vertex AI (`google-genai` SDK 사용)
*   **가격:** 1,000자당 ~$0.000025 (온라인 요청)
*   **선정 이유:**
    *   `text-embedding-004` deprecated → `gemini-embedding-001`로 마이그레이션.
    *   3072차원으로 더 높은 시맨틱 정확도 제공.
    *   500개 미만 태그 규모에서 차원 증가로 인한 비용/성능 영향 무의미.
    *   Vertex AI 생태계의 일부로, GCP 크레딧 사용 및 엔터프라이즈급 신뢰성 확보 가능.

## 2. 데이터베이스 인프라 (Database Infrastructure)
기존 PostgreSQL 인스턴스에 **`pgvector`** 확장을 활용합니다.

*   **확장 기능:** `vector`
*   **인덱스 유형:** HNSW (Hierarchical Navigable Small World) - 빠른 근사 최근접 이웃 검색을 위해 사용.
    *   *참고:* IVFFlat이 대안이 될 수 있으나, 우리 규모에서는 HNSW가 일반적으로 더 나은 성능/재현율 트레이드오프를 제공합니다.
*   **스키마 변경:**
    *   테이블: `tags`
    *   새 컬럼: `embedding vector(3072)`

## 3. 백엔드 통합 (Backend Integration - FastAPI)
백엔드는 Vertex AI를 사용하도록 구성된 `google-genai` Python SDK를 사용하여 임베딩을 생성합니다.

### 구성 (Configuration)
GCP 크레딧과 Vertex AI 할당량을 활용하려면 클라이언트를 `vertexai=True`로 초기화해야 합니다.

```python
from google import genai
import os

client = genai.Client(
    vertexai=True,
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
)

# 사용 예시
result = client.models.embed_content(
    model="gemini-embedding-001",
    contents="낭만적인 강변 길"
)
```

### 환경 변수 (Environment Variables)
*   `GOOGLE_CLOUD_PROJECT`: GCP 프로젝트 ID.
*   `GOOGLE_CLOUD_LOCATION`: Vertex AI 리전 (예: `us-central1`).
*   `GOOGLE_APPLICATION_CREDENTIALS`: 서비스 계정 키 경로 (또는 Cloud Run/Compute Engine의 기본 인증 사용).

## 4. 마이그레이션 계획 (Migration Plan)
1.  **확장 활성화:** 데이터베이스에서 `CREATE EXTENSION IF NOT EXISTS vector;` 실행.
2.  **스키마 업데이트:** `tags` 테이블에 `embedding` 컬럼 추가.
3.  **백필 (Backfill):** 스크립트(`scripts/data_refinement/embed_existing_tags.py`) 생성하여 수행:
    *   `embedding IS NULL`인 모든 기존 태그 조회.
    *   `gemini-embedding-001`를 사용하여 배치로 임베딩 생성.
    *   데이터베이스 레코드 업데이트.
4.  **인덱싱:** 초기 데이터 적재 후 `embedding` 컬럼에 HNSW 인덱스 생성 (빌드 시간 최적화).
