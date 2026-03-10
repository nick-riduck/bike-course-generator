# Routy.cc 오픈 체크리스트

> **목표: 2026년 3월 14일(금) 오픈**
> 오늘: 3월 10일(화) | D-4

---

## Day 1 - 3/10(화): 인프라 + 브랜딩

### 도메인 & SSL
- [x] `_acme-challenge.routy.cc` TXT 레코드 전파 확인
- [x] Firebase SSL 인증서 발급 완료 (CN=routy.cc, 2026-03-10 발급)
- [x] `https://routy.cc` 정상 접속 확인 (HTTP 200)
- [x] `.firebaserc` hosting target 불일치 수정 (`simulator` vs `generator`)
- [x] Firebase Auth 승인된 도메인에 `routy.cc` 추가
- [x] CORS 설정에 `routy.cc` 추가 (환경변수 `ALLOWED_ORIGINS` 방식, Firebase Auth와 동일 목록)

### 브랜딩 & 디자인
- [ ] Routy 로고/아이콘 제작 (또는 확정)
- [ ] `index.html` title 변경 (`"frontend"` → `"Routy"`)
- [ ] favicon 교체
- [ ] OG 메타태그 추가 (`og:title`, `og:description`, `og:image`)
- [ ] 앱 내 "riduck" 텍스트 → "Routy" 리네이밍
- [ ] 컬러 테마 정리 (primary color 등)

---

## Day 2 - 3/11(수): 온보딩 데모 + DB 마이그레이션

### 온보딩 데모 투어
> 2가지 스텝 구성:
> 1. **핵심 체험** - 경로 생성 → AI 태깅/설명 생성 (실제 UX 따라하기)
> 2. **기능 소개** - 나머지 버튼 하이라이트 + 클릭만 유도

#### 온보딩 상태 관리
> - 비로그인: `localStorage`로 체크
> - 로그인: DB `onboarding_completed` 플래그 우선
> - 로그인 시 localStorage 값 → DB 동기화 (비로그인 때 봤으면 다시 안 뜸)

- [ ] `users` 테이블에 `onboarding_completed BOOLEAN DEFAULT FALSE` 컬럼 추가
- [ ] 온보딩 완료 API 엔드포인트 (`PATCH /api/users/me/onboarding`)
- [ ] 프론트: localStorage + DB 동기화 로직
- [ ] 스텝1 구현: 경로 생성 → AI 태깅/설명 생성 가이드 (tooltip/stepper)
- [ ] 스텝2 구현: 주요 기능 버튼 하이라이트 + 클릭 유도
- [ ] 데모 스킵 버튼
- [ ] 데모 완료 후 회원가입 유도 흐름 (비로그인 시)

### Suimi 코스 데이터 정비
- [x] description 재생성 (중요정보→상세→출처 포맷, Gemini 3.1 Pro, 195개 완료)
- [x] 우여사 계정 생성 (`no232@hanmail.net`, ID 101)
- [x] suimi 코스 소유권 우여사로 이전 (266개)
- [x] 테스트 코스 삭제 (tt, Untitled Route 등 10개)

### 운영 DB 마이그레이션
- [x] 마이그레이션 스크립트 작성/검증 (`scripts/output/production_migration.sql`)
  - [x] `halfvec(3072)` + HNSW index
  - [x] `waypoints` 테이블
  - [x] `route_waypoints` join 테이블
  - [x] `users.onboarding_completed` 컬럼
  - [x] `users.id` 시퀀스 1000부터 시작
  - [x] 우여사 서비스 계정 (ID 101)
- [x] 프로덕션 postgres 이미지 교체 (postgis → postgis+pgvector)
- [x] 프로덕션 마이그레이션 실행 (스키마 + 데이터 이관)
- [x] 마이그레이션 후 데이터 정합성 확인 (users 6, routes 268, tags 236, waypoints 1501)

---

## Day 3 - 3/12(목): 로깅/모니터링 + 버그 수정

### 로깅 & 모니터링 점검
- [ ] **Sentry**: 프론트엔드 에러 수신 테스트
- [ ] **Sentry**: 백엔드 에러 수신 테스트
- [ ] **PostHog**: 이벤트 수집 확인 (페이지뷰, 주요 액션)
- [ ] **GA4**: 트래킹 정상 동작 확인
- [ ] **GCP**: Cloud Run 로그 확인
- [ ] **GCP**: 알럿 정책 설정 (에러율, 레이턴시)
- [ ] 에러 알림 채널 연결 (이메일/슬랙)

### 버그 수정 & UI 개선
- [x] `feature/library-enhancements` 변경사항 리뷰 & 커밋
- [ ] 불필요 파일 정리 (`image.png`, `image copy.png`, `update_auto_tag_endpoint.py`)
- [ ] 모바일 반응형 깨지는 부분 수정
- [ ] 로딩 상태/에러 상태 UX 개선
- [ ] 자잘한 UI 버그 수정 (발견되는 대로)

### 보안 점검
- [ ] GitHub Actions 하드코딩된 키 → Secrets 이동
- [ ] `.gitignore` 민감 파일 확인
- [ ] Cloud Run 환경변수 점검

---

## Day 4 - 3/13(목): QA + 최종 정리

### QA
- [ ] 주요 플로우 수동 테스트
  - [ ] 지도 로딩 & 코스 탐색
  - [ ] 코스 검색 & 필터
  - [ ] 코스 생성 & 저장
  - [ ] Waypoint 상세 (사진, 팁)
  - [ ] GPX 내보내기
  - [ ] 로그인/로그아웃
  - [ ] 온보딩 데모 투어
- [ ] 모바일 테스트 (iOS Safari, Android Chrome)
- [ ] 크로스 브라우저 (Chrome, Safari, Firefox)
- [ ] API 응답 속도 체크
- [ ] 발견된 버그 수정

### 최종 정리
- [ ] main 브랜치 최종 머지
- [ ] GitHub Actions 배포 성공 확인 (frontend + backend)
- [ ] 프로덕션 스모크 테스트
- [ ] 기존 도메인 → `routy.cc` 리다이렉트 설정

---

## Day 5 - 3/14(금): 🚀 오픈

- [ ] `https://routy.cc` 전체 기능 최종 확인
- [ ] DNS/CDN 캐시 정상 확인
- [ ] 모니터링 대시보드 열어두기
- [ ] 오픈 완료 🚀

---

## 일정 요약

| 날짜 | 요일 | 주요 작업 | 비중 |
|------|------|-----------|------|
| **3/10** | 화 | 도메인/SSL, 브랜딩(로고,테마,아이콘) | 인프라 + 디자인 |
| **3/11** | 수 | 온보딩 데모 구현, DB 마이그레이션 | 핵심 기능 |
| **3/12** | 목 | 로깅 점검, 버그 수정, UI 개선, 보안 | 안정화 |
| **3/13** | 금 | QA, 최종 머지, 스모크 테스트 | 검증 |
| **3/14** | **토** | **🚀 routy.cc 오픈** | 출시 |

---

> 작성일: 2026-03-10
