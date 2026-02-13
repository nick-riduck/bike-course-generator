# 🚴 PRO-812: GPX 코스 생성기 고도화 계획

## 🎯 목표
DB 설계(`docs/db/02_routes_and_segments.md`)에 정의된 핵심 기능들을 프론트엔드 UI에 완벽히 구현하고, 사용자 경험을 개선하여 시뮬레이터와 긴밀하게 연동될 수 있는 코스 관리 체계를 구축합니다.

---

## 🗓️ 마일스톤 및 세부 과제

### 1단계: 코스 저장 흐름 개선 (Save Experience)
*   [x] **고급 저장 모달(Save Modal) 구현**
    *   제목(Title), 설명(Description) 입력 UI 추가.
    *   공개 범위(`PUBLIC`, `PRIVATE`, `LINK_ONLY`) 선택 옵션 구현.
    *   **사용자 정의 태그 입력 UI**: 사용자가 직접 태그(예: #훈련, #관광)를 추가/삭제하는 인터페이스.
*   [x] **저장 로직 분기 (Fork vs Overwrite)**
    *   **새로 저장 (Fork):** 다른 사람의 코스이거나 '복제'를 원할 때. `parent_route_id` 연결하여 신규 생성.
    *   **덮어쓰기 (Update):** 본인이 작성한 코스일 때만 활성화. 기존 ID 유지하며 데이터 갱신.
*   [x] **썸네일 자동 생성 시스템**
    *   `mapbox-static-api` 또는 `html2canvas`를 활용하여 코스 전체 경로가 포함된 정적 이미지 생성 및 `thumbnail_url` 저장.

### 2단계: 라이브러리 및 검색 고도화 (Advanced Library)
*   [x] **시각적 라이브러리 UI 개선**
    *   `SearchPanel`의 단순 리스트를 카드 형태의 그리드/리스트로 변경 (썸네일 포함).
*   [ ] **필터링 및 검색 강화**
    *   **검색 옵션 UI**: 코스 이름, 작성자, 태그 중 선택하여 검색 가능하도록 구현.
    *   **태그 기반 필터링**: 사용자가 입력한 태그(예: #업힐)로 목록 필터링.
    *   거리, 획득고도 범위 슬라이더 필터링.
*   [ ] **코스 즐겨찾기 (My Favorites)**
    *   다른 사용자의 공개 코스를 내 라이브러리에 저장(Favorites)하는 기능.

### 3단계: 상세 페이지 및 소셜 기능 (Social & Sharing)
*   [ ] **코스 상세 페이지 구현**
    *   `route_num` 기반의 고유 URL 제공.
    *   상세 고도 차트, 노면 비율 요약, 세그먼트 목록 표시.
*   [ ] **공유 UI 및 인터랙션**
    *   URL 복사 버튼 (SNS 공유는 보류).
    *   다운로드 수, 조회수(`RouteStats`) 기록 로직 연동.

### 4단계: 물리 시뮬레이션 데이터 정밀화 (Simulation Integrity)
*   [x] **노면 매핑 로직 개선 (Critical)**
    *   현재 하드코딩된 `asphalt` 고정값을 Valhalla API 응답 데이터(`surface`)를 기반으로 실시간 매핑. (가장 시급한 데이터 정합성 이슈)
*   [x] **시뮬레이션 전용 JSON 최적화**
    *   `segments` (Atomic Segments) 데이터 생성 로직 검증 및 고도화.
    *   프론트엔드 편집기 상태(`editor_state`)와 시뮬레이션 데이터(`points`, `segments`)의 일관성 유지.
    *   **완료 노트 (2026-02-12):** 시뮬레이터 프로젝트의 `valhalla.py` 모듈을 백엔드로 이식하여 저장 시 물리 엔진과 동일한 로직으로 세그먼트를 자동 재생성하도록 통합함. E2E 테스트를 통해 노면별 세그먼트 분할 및 데이터 정합성 검증 완료.

### 5단계 (후순위)
*   [ ] **자동 태깅 및 배지**
    *   코스 저장 시 고도/노면 분석 후 자동 태그(HC, Gravel 등) 부여.
    *   `Official`, `Verified` 뱃지 시스템.

### 4단계: 물리 시뮬레이션 데이터 정밀화 (Simulation Integrity)
*   [ ] **노면 매핑 로직 개선**
    *   현재 하드코딩된 `asphalt` 고정값을 Valhalla API 응답 데이터(`surface`)를 기반으로 실시간 매핑.
*   [ ] **시뮬레이션 전용 JSON 최적화**
    *   `segments` (Atomic Segments) 데이터 생성 로직 검증 및 고도화.
    *   프론트엔드 편집기 상태(`editor_state`)와 시뮬레이션 데이터(`points`, `segments`)의 일관성 유지.

---

## 🛠️ 기술적 부채 및 인프라 (Tech Debt & Infra)
*   [ ] **Frontend API Client 추상화**: `fetch` 호출을 `apiClient` 모듈로 분리하여 에러 처리 및 토큰 주입 자동화.
*   [ ] **CI/CD 환경변수 보안**: GitHub Secrets를 활용한 환경변수 관리 (`.env` 주입).
*   [ ] **PR Preview 자동 댓글**: Firebase 배포 후 PR에 프리뷰 링크 자동 게시 스크립트.
