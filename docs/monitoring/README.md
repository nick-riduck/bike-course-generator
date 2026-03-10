# 모니터링 & 관측성 (Monitoring & Observability)

Riduck 서비스의 모니터링/분석 도구 구성 문서.

## 목차
- [도구 구성 개요](#도구-구성-개요)
- [GA4 (Google Analytics 4)](#1-ga4-google-analytics-4)
- [Sentry](#2-sentry)
- [PostHog](#3-posthog)
- [Cloud Monitoring (미구현)](#4-cloud-monitoring-미구현)
- [고도화 로드맵](#고도화-로드맵)

---

## 도구 구성 개요

```
유저 브라우저
  ├── GA4           → 트래픽/유입/페이지뷰 (마케팅 관점)
  ├── PostHog       → 행동 분석/세션 리플레이 (프로덕트 관점)
  └── Sentry (JS)   → 프론트엔드 에러 추적

          ↓ API 호출

Cloud Run (FastAPI)
  └── Sentry (Python) → 백엔드 에러 추적

GCP VM (PostgreSQL)
  └── pg_stat_statements → 느린 쿼리 (미구현)
```

| 도구 | 용도 | 비용 | 대시보드 |
|------|------|------|---------|
| GA4 | 트래픽, 유입 경로, DAU/MAU | 무료 | [analytics.google.com](https://analytics.google.com) |
| Sentry | 에러 추적, 스택 트레이스 | 무료 (5K 에러/월) | [sentry.io](https://sentry.io) |
| PostHog | 유저 행동, 세션 리플레이, 퍼널 | 무료 (100만 이벤트/월) | [us.posthog.com](https://us.posthog.com) |
| Cloud Monitoring | 인프라 메트릭, 업타임 | 무료 | GCP 콘솔 (미구현) |

---

## 1. GA4 (Google Analytics 4)

### 설정 정보
- **측정 ID**: `G-FZ2GBDKLFE`
- **초기화 방식**: gtag.js (외부 스크립트)
- **유틸리티 파일**: `frontend/src/utils/analytics.js`

### 수정된 파일
| 파일 | 변경 내용 |
|------|----------|
| `frontend/src/utils/analytics.js` | GA4 유틸리티 (신규 생성) |
| `frontend/src/main.jsx` | `initGA()` 호출 |
| `frontend/src/App.jsx` | 라우트 변경 시 `trackPageView()` |
| `frontend/src/AuthContext.jsx` | 로그인 시 `setUserId()` + `analytics.login()` |
| `frontend/src/components/BikeRoutePlanner.jsx` | route_viewed, route_created, route_exported, waypoint_viewed |
| `frontend/src/components/SearchPanel.jsx` | route_search, search_tab_changed |

### 추적 이벤트 목록

| 이벤트명 | 발생 시점 | 속성 (parameters) | 파일 위치 |
|---------|----------|-------------------|----------|
| `page_view` | 라우트 변경 | `page_path`, `page_title` | App.jsx |
| `login` | 로그인 성공 | `method` (google) | AuthContext.jsx |
| `route_search` | 검색 실행 | `search_term`, `results_count`, filters | SearchPanel.jsx |
| `route_viewed` | 코스 미리보기 로드 | `route_id`, `distance`, `source` | BikeRoutePlanner.jsx |
| `route_created` | 코스 저장 성공 | `route_id`, `distance`, `elevation_gain`, `tag_count` | BikeRoutePlanner.jsx |
| `route_exported` | GPX/TCX 내보내기 | `format` | BikeRoutePlanner.jsx |
| `waypoint_viewed` | 웨이포인트 클릭 (지도) | `waypoint_id`, `waypoint_type` | BikeRoutePlanner.jsx |
| `search_tab_changed` | 검색 탭 전환 | `tab` (all/my/favorites) | SearchPanel.jsx |

### GA4에서 볼 수 있는 것
- **자동 수집**: 페이지뷰, 세션 수, 유저 수, 체류 시간, 이탈률, 기기/지역/브라우저 정보
- **커스텀 이벤트**: 위 표의 이벤트 기반 분석
- **유입 분석**: 어디서 들어왔는지 (Direct, Organic Search, Social, Referral)
- **전환 퍼널**: 방문 → 로그인 → 코스 조회 → 코스 저장 전환율

---

## 2. Sentry

### 설정 정보
- **프론트엔드 DSN**: `https://b5f5cb7d8513b64a47468ac27d9dc6d3@o4511017491169280.ingest.us.sentry.io/4511017591570432`
- **백엔드 DSN**: `https://93e723471fc93415696de14850f21982@o4511017491169280.ingest.us.sentry.io/4511017595961344`
- **데이터 센터**: US

### 수정된 파일

#### 프론트엔드
| 파일 | 변경 내용 |
|------|----------|
| `frontend/src/main.jsx` | `Sentry.init()` — browserTracing + replayIntegration |
| `frontend/src/App.jsx` | 커스텀 ErrorBoundary → `Sentry.ErrorBoundary`로 교체 |
| `frontend/src/AuthContext.jsx` | 로그인 시 `Sentry.setUser()`, 로그아웃 시 `Sentry.setUser(null)` |

#### 백엔드
| 파일 | 변경 내용 |
|------|----------|
| `backend/app/main.py` | `sentry_sdk.init()` (FastAPI 자동 통합) |
| `backend/requirements.txt` | `sentry-sdk[fastapi]` 추가 |

### Sentry 설정 상세

```javascript
// 프론트엔드 (main.jsx)
Sentry.init({
  dsn: "...",
  integrations: [
    Sentry.browserTracingIntegration(),  // API 호출 성능 추적
    Sentry.replayIntegration(),          // 에러 발생 시 세션 리플레이
  ],
  tracesSampleRate: 1.0,                // 모든 트랜잭션 수집 (프로덕션에서 낮출 수 있음)
  replaysSessionSampleRate: 0.1,         // 일반 세션의 10% 리플레이
  replaysOnErrorSampleRate: 1.0,         // 에러 세션은 100% 리플레이
});
```

```python
# 백엔드 (main.py)
sentry_sdk.init(
    dsn="...",
    traces_sample_rate=1.0,    # 모든 API 요청 추적
    send_default_pii=True,     # 유저 IP 등 개인정보 포함
)
# FastAPI 통합은 자동 — 별도 미들웨어 불필요
```

### Sentry가 자동으로 잡는 것

#### 프론트엔드
- JavaScript uncaught exceptions
- Unhandled promise rejections
- React 컴포넌트 렌더링 에러 (ErrorBoundary)
- API 호출 실패 (fetch 에러)
- 에러 발생 전후 세션 리플레이

#### 백엔드
- FastAPI 엔드포인트 500 에러
- Python 미처리 예외 (unhandled exceptions)
- API 응답 시간 (Performance Monitoring)
- DB 쿼리 에러

### Sentry에서 볼 수 있는 것
- **Issues**: 에러별 발생 횟수, 영향받은 유저 수, 첫 발생/마지막 발생 시점
- **Performance**: API 엔드포인트별 응답 시간, p50/p95/p99
- **유저 컨텍스트**: 에러를 겪은 유저의 ID, 이메일 (로그인 상태일 때)
- **릴리즈 추적**: 배포별 에러 증감 비교

---

## 3. PostHog

### 설정 정보
- **API Key**: `phc_stRRL5l68rbqaxolbumgYm2j72tCFKsxWbQkcOxHfuQ`
- **API Host**: `https://us.i.posthog.com`
- **Person Profiles**: `identified_only` (로그인 유저만 프로필 생성)

### 수정된 파일
| 파일 | 변경 내용 |
|------|----------|
| `frontend/src/main.jsx` | `posthog.init()` — 페이지뷰/세션 리플레이 자동 |
| `frontend/src/AuthContext.jsx` | `posthog.identify()` / `posthog.reset()` |
| `frontend/src/components/BikeRoutePlanner.jsx` | route_viewed, route_created, route_exported, waypoint_viewed |
| `frontend/src/components/SearchPanel.jsx` | route_search |

### PostHog 설정 상세

```javascript
// main.jsx
posthog.init('phc_stRRL5l68rbqaxolbumgYm2j72tCFKsxWbQkcOxHfuQ', {
  api_host: 'https://us.i.posthog.com',
  person_profiles: 'identified_only',  // 비로그인 유저는 익명 이벤트만
  capture_pageview: true,               // 페이지뷰 자동 수집
  capture_pageleave: true,              // 페이지 이탈 자동 수집
  session_recording: {
    recordCrossOriginIframes: true,      // iframe 포함 녹화
  },
});
```

### 추적 이벤트 목록

| 이벤트명 | 발생 시점 | 속성 | 파일 위치 |
|---------|----------|------|----------|
| `$pageview` | 페이지 이동 | (자동) | 자동 수집 |
| `$pageleave` | 페이지 이탈 | (자동) | 자동 수집 |
| `route_viewed` | 코스 미리보기 로드 | `route_id`, `distance`, `title` | BikeRoutePlanner.jsx |
| `route_created` | 코스 저장 성공 | `route_id`, `distance`, `elevation_gain`, `tags`, `is_overwrite` | BikeRoutePlanner.jsx |
| `route_exported` | GPX/TCX 내보내기 | `format` | BikeRoutePlanner.jsx |
| `waypoint_viewed` | 웨이포인트 클릭 | `waypoint_id`, `waypoint_type` | BikeRoutePlanner.jsx |
| `route_search` | 검색 실행 | `query`, `results_count` | SearchPanel.jsx |

### PostHog에서 볼 수 있는 것
- **세션 리플레이**: 유저 화면 영상 재생 (클릭, 스크롤, 입력 포함)
- **퍼널 분석**: 단계별 전환율 (예: 방문 → 로그인 → 코스 조회 → 저장)
- **유저 경로**: 개별 유저의 전체 행동 타임라인
- **코호트 분석**: 가입 시기별 리텐션 비교
- **히트맵**: 클릭 분포 시각화
- **이벤트 트렌드**: 일별/주별 이벤트 발생 추이

### GA4와 PostHog 이벤트 중복 관계

동일한 유저 행동을 GA4와 PostHog 양쪽에 전송합니다. 이유:

| 관점 | GA4 | PostHog |
|------|-----|---------|
| 트래픽/유입 분석 | O (강점) | 약함 |
| 개별 유저 행동 | 약함 | O (강점) |
| 세션 리플레이 | X | O |
| 퍼널 유연성 | 기본적 | 자유롭게 구성 |

→ GA4는 마케팅/트래픽 관점, PostHog는 프로덕트/UX 관점으로 역할 분리.

---

## 4. Cloud Monitoring (미구현)

6월까지 GCP 크레딧 사용 가능한 동안 구성 예정.

### 구성 계획
| 항목 | 설명 | 비용 |
|------|------|------|
| Uptime Check | API 엔드포인트 헬스체크 (5분 간격) | 무료 (영구) |
| Alerting | 에러율 급증, VM 다운 시 알림 | 무료 (영구) |
| Cloud Trace | API 요청 트레이싱 (OpenTelemetry) | 유료 (6월에 끔) |
| pg_stat_statements | PostgreSQL 느린 쿼리 모니터링 | 무료 (VM 내부) |
| 대시보드 | Cloud Run + VM 메트릭 시각화 | 무료 (영구) |

### 구현 시 필요한 작업
- FastAPI에 `opentelemetry-exporter-gcp-trace` 설치 + 미들웨어 추가
- GCP 콘솔에서 Uptime Check, Alerting Policy, 대시보드 구성
- PostgreSQL VM에서 `pg_stat_statements` extension 활성화

---

## 고도화 로드맵

### Phase 1 — 현재 (완료)
기본 연동 완료. 배포 후 데이터 수집 시작.

- [x] GA4: 페이지뷰 + 커스텀 이벤트 7종
- [x] Sentry: 프론트/백엔드 에러 자동 수집
- [x] PostHog: 세션 리플레이 + 커스텀 이벤트 5종

### Phase 2 — 이벤트 확장
데이터 수집 후 부족한 이벤트를 추가.

추가 고려 이벤트:
| 이벤트 | 파일 | 인사이트 |
|--------|------|---------|
| `map_point_added` | BikeRoutePlanner.jsx | 코스 생성 과정 분석 |
| `map_point_removed` | BikeRoutePlanner.jsx | 실수/수정 빈도 |
| `elevation_chart_viewed` | ElevationChart.jsx | 고도 정보 관심도 |
| `tag_searched` | SaveRouteModal.jsx | 인기 태그 파악 |
| `nearby_route_clicked` | BikeRoutePlanner.jsx | 주변 코스 탐색 패턴 |
| `import_gpx` | BikeRoutePlanner.jsx | GPX 임포트 사용률 |
| `waypoint_filtered` | WaypointPanel.jsx | 웨이포인트 타입별 관심도 |
| `error_boundary_hit` | App.jsx | 크래시 빈도 (Sentry와 별도 집계) |

### Phase 3 — PostHog 대시보드 & 퍼널
수집된 데이터로 의미 있는 분석 구성.

**핵심 퍼널:**
```
1. 방문 → 로그인 → 코스 검색 → 코스 조회 → 코스 저장
2. 방문 → 코스 조회 → GPX 내보내기
3. 방문 → 웨이포인트 조회 → 코스 생성
```

**핵심 대시보드:**
- DAU/WAU/MAU 추이
- 코스 저장 전환율
- 인기 검색어/태그
- 디바이스별 사용 비율
- 세션당 평균 이벤트 수

### Phase 4 — 인프라 모니터링
Cloud Monitoring + Cloud Trace 구성.

- API 응답 시간 대시보드 (p50/p95/p99)
- Uptime Check + 장애 알림 (Slack/이메일)
- 느린 쿼리 모니터링 (pg_stat_statements)
- Cloud Trace로 Valhalla/Gemini 외부 호출 병목 분석

### Phase 5 — 고급 분석
서비스 성장 시 고려할 사항.

| 항목 | 설명 |
|------|------|
| **PostHog 피처 플래그** | 신기능 A/B 테스트 (일부 유저에게만 노출) |
| **GA4 + BigQuery 연동** | 원시 데이터 SQL 분석 (무료 export) |
| **Sentry 릴리즈 추적** | 배포별 에러 증감 자동 비교 |
| **커스텀 메트릭** | 비즈니스 KPI 실시간 대시보드 (총 코스 수, 활성 유저 등) |
| **알림 자동화** | 전환율 급락/에러 급증 시 Slack 알림 |

---

## 환경 변수 / 키 관리 참고

현재 모든 키가 소스코드에 하드코딩되어 있음. 프로덕션 보안 강화 시:

| 키 | 현재 위치 | 이동 대상 |
|----|----------|----------|
| GA4 측정 ID | `utils/analytics.js` | `.env` → `VITE_GA_MEASUREMENT_ID` |
| Sentry DSN (FE) | `main.jsx` | `.env` → `VITE_SENTRY_DSN` |
| Sentry DSN (BE) | `backend/app/main.py` | 환경 변수 `SENTRY_DSN` |
| PostHog API Key | `main.jsx` | `.env` → `VITE_POSTHOG_KEY` |

> 참고: GA4 측정 ID, Sentry DSN, PostHog API Key는 모두 **클라이언트 공개 키**이므로
> 소스코드에 있어도 보안 문제는 없음. 환경 분리(dev/staging/prod)가 필요할 때 환경 변수로 이동.
