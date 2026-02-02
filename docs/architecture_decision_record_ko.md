# 아키텍처 결정 기록 (ADR) - 2026-01-30

## 1. 경로 탐색 엔진 이주 (프로젝트 Valhalla)

### 결정 사항
기존 **OpenRouteService (ORS)**에서 **Valhalla**로 이주합니다.

### 배경 및 근거
*   **초기 상황:** 한국 한정 서비스였을 때는 ORS로 충분했음.
*   **새로운 요구사항:** **중화권(중국 + 대만)** 및 글로벌 시장 타겟팅으로 확장.
*   **비용 및 성능 이슈:** 
    *   ORS는 지도를 메모리에 통째로 올리는 구조라, 중국 데이터(1.3GB PBF)를 처리하려면 64GB 이상의 RAM 서버가 필요함 (월 비용 약 20~30만 원 이상).
    *   **Valhalla**는 **타일 구조(Tiled Structure)**를 사용하여, 필요한 지역만 메모리에 로드함. 8GB RAM 서버에서도 중국+한국 지도를 효율적으로 운영 가능하여 비용을 1/10로 절감 가능.
*   **유연한 설정:** 요청 시마다 경사도 회피, 자전거 종류 등을 실시간으로 조절하기에 Valhalla가 더 유리함.

### 구현 상태
*   **도커 이미지:** `ghcr.io/valhalla/valhalla-scripted:latest` (Nils Nolde/GIS•OPS 기반)
*   **데이터 소스:** 한국 + 중국 (Geofabrik PBF)
*   **활성화 기능:** 고도 데이터(Elevation), 행정 구역, 시간대 빌드 포함.

---

## 2. 백엔드 아키텍처

### 결정 사항
**Python (FastAPI)**를 사용하여 미들웨어 백엔드를 구축합니다.

### 아키텍처 다이어그램
```mermaid
graph LR
    User[프론트엔드 (React)] -- HTTP --> Backend[FastAPI 서버]
    Backend -- HTTP (JSON) --> Valhalla[Valhalla 도커 (Port 8002)]
    Valhalla -- JSON --> Backend
    Backend -- 가공된 GeoJSON 응답 --> User
```

### 백엔드의 핵심 역할
1.  **프록시 및 보안:** 내부 Valhalla 서버 주소를 숨기고, 추후 사용자 인증 및 API 권한 관리 수행.
2.  **데이터 가공 (BFF 패턴):** 
    *   Valhalla의 복잡한 원본 데이터를 받아서 분석함.
    *   **노면 분석:** 노면 정보(Surface)에 따라 경로를 조각내어 색상 정보를 입힘 (예: 포장도로=청록색, 비포장=주황색).
    *   **렌더링 최적화:** 프론트엔드에서 복잡한 계산 없이 바로 지도에 그릴 수 있는 형태(FeatureCollection)로 변환하여 전달.
3.  **GPX 지원:** 
    *   지도 렌더링용 조각 데이터와 별개로, GPX 파일 생성 및 고도 차트용 원본 좌표(`full_geometry`)를 함께 제공.

### 기술 스택
*   **언어:** Python 3.12+
*   **프레임워크:** FastAPI (비동기 처리 최적화)
*   **라이브러리:** `httpx` (통신), `sqlalchemy` (DB), `pydantic` (검증).

---

## 3. 데이터 응답 전략 (하이브리드 방식)

### 결정 사항
백엔드는 지도 렌더링에 최적화된 데이터와 GPX용 원본 데이터를 동시에 반환합니다.

### 응답 JSON 구조 (예시)
```json
{
  "summary": {
    "distance": 12.5, // km
    "ascent": 150,    // 획득 고도(m)
    "time": 3600      // 예상 시간(초)
  },
  "display_geojson": { 
    // 지도 렌더링용: 노면별로 색깔이 미리 입혀진 데이터
    "type": "FeatureCollection",
    "features": [
      { "geometry": { ... }, "properties": { "color": "#2a9e92", "surface": "paved" } },
      { "geometry": { ... }, "properties": { "color": "#FF9800", "surface": "gravel" } }
    ]
  },
  "full_geometry": {
    // GPX 생성 및 고도 차트용: 끊어지지 않은 원본 좌표 리스트 (고도 포함)
    "type": "LineString",
    "coordinates": [[127.0, 37.0, 15], [127.01, 37.01, 18], ...] 
  }
}
```

### 기대 효과
*   **프론트엔드 코드 단순화:** 복잡한 색상 매핑 로직을 삭제하고 서버가 준 대로 그리기만 하면 됨.
*   **데이터 일관성:** 지도는 조각나 보여도 GPX 파일은 하나의 매끄러운 경로로 생성됨.
*   **디자인 유연성:** 노면별 색상 정책을 서버에서 관리하므로, 앱 업데이트 없이 디자인 변경 가능.

---

## 4. 배포 전략

### 현재 (개발 및 MVP 단계)
*   **방식:** 단일 VM 내에서 Docker Compose를 통해 모든 컴포넌트 실행.
*   **장점:** 비용 최소화 및 서버 간 통신 지연(Latency) 제로.

### 미래 (운영 단계)
*   **Valhalla:** 고성능 I/O를 지원하는 전용 VM으로 분리.
*   **백엔드:** 서버리스(AWS Lambda, GCP Cloud Run) 환경으로 이전하여 확장성 확보.
*   **프론트엔드:** Vercel 또는 AWS S3/CloudFront를 통한 정적 배포.
