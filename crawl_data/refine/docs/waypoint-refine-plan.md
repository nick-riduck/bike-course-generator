# Komoot 웨이포인트 정제 계획

## 목표
Komoot 크롤링 데이터의 웨이포인트를 정제하여 `waypoints` DB 테이블에 적재.
최종 용도: 코스 생성 시 경로 주변 POI를 LLM에 제공 → 자동 태그/설명 생성.

---

## 1. 현재 진행 상황

### 1a. 크롤링 데이터 현황
| 항목 | 수치 |
|------|------|
| 총 코스 | 882개 |
| GPX 있음 | 862개 |
| metadata.json | 879개 |
| 총 웨이포인트 | 7,400개 |
| 이름 있는 WP (의미 있음) | 3,756개 |
| 이름 없는 WP (경유 포인트) | 3,644개 → 제거 대상 |

- `description` 필드는 전부 비어있음 (smarttour 특성상 정상)
- 사진만 있고 이름 없는 WP = 0개 → 이름 유무가 의미 있는 WP 판별 기준
- 세그먼트 데이터(way_types, surfaces)는 스킵 (Valhalla로 자체 추출 가능)

### 1b. 중복 병합 완료
| 단계 | 방법 | 결과 |
|------|------|------|
| Phase 1 | 정확 이름 + 100m 반경 클러스터링 | 3,756 → 1,551 유니크 POI |
| Phase 2 | 유사 이름 + 500m, Gemini 3.1 Pro 판단 | 37쌍 중 23쌍 병합 확정 |
| 최종 | | **~1,528 유니크 POI** |

- 병합 결과: `crawl_data/refine/merge_result_gemini.json` (사람 검토 완료)
- 지도 시각화: `crawl_data/waypoints_map.html` (등장 빈도별 색상)

### 1c. 현재 POI 데이터 상태
| 필드 | 상태 |
|------|------|
| name | ✅ 있음 |
| 좌표 (lat/lng) | ✅ 있음 (클러스터 평균) |
| category (Komoot raw) | ✅ 있음 (하나) — 병합 시 복수 가능 |
| 사진 URL | ✅ 일부 있음 |
| tips | ✅ 811개 |
| description | ❌ 전부 없음 |
| waypoint_type[] (우리 ENUM) | ❌ 매핑 안 됨 |

### 1d. Komoot 카테고리 분포
| 카테고리 | 개수 | 추정 의미 | 예시 |
|----------|------|----------|------|
| (빈값) | 3,644 | 경유 포인트 | - |
| 219 | 519 | 공원/마을 | 양재시민의숲, 기장 |
| 190 | 482 | 하천/강 | 덕풍천, 영산강 |
| facilities | 476 | 편의시설 | 광나루 인증센터 |
| 63 | 297 | 건물/아파트 | 현대 I-Park |
| cycle_way | 291 | 자전거도로 | 풍납동-삼성동 구간 |
| bridge | 289 | 다리 | 한강철교 |
| other_man_made | 161 | 인공 구조물 | CVS 편의점 |
| river | 150 | 강/하천 | 양재천 입구 |
| viewpoint | 123 | 전망대 | 일몰 전망 |
| cafe | 120 | 카페 | 성심당 DCC |
| 14 | 97 | 전망대/주차장 | 전망대 |
| 21 | 82 | 산/나루터 | 야방산 |
| 12 | 75 | 해변 | 임랑해수욕장 |
| ... | ... | ... | ... |

### 1e. DB 스키마
`docs/db/02_routes_and_segments.md` 섹션 4에 추가 완료:
- `waypoints` 테이블 (PostGIS, waypoint_type[] ENUM 배열)
- `route_waypoints` 관계 테이블
- DB에는 아직 테이블 미생성

---

## 2. 남은 작업

### Step 1: 최종 유니크 POI JSON 생성
- Phase 1 클러스터링 + Phase 2 병합 결과 적용
- 카테고리를 배열로 수집 (병합 시 양쪽 카테고리 모두 포함)
- 사진, tips도 병합
- 출력: `crawl_data/refine/unique_pois.json`

### Step 2: 외부 데이터로 POI 보강
**문제:** 현재 데이터에 description이 없고, Komoot 카테고리 코드가 불명확함.
LLM만으로는 부정확 → 지도 API 검색 결과를 근거 자료로 활용.

**방안: Google Places API 또는 Kakao Local API**
- 입력: POI 이름 + 좌표
- 출력: 정식 명칭, 장소 유형, 주소, 카테고리
- 좌표는 검색 결과 검증용 (올바른 장소인지 거리 비교)

**플로우:**
```
1,528개 POI
  → Google Places / Kakao Local API 검색 (이름 + 좌표)
  → 검색 결과에서 장소 유형, 주소, 정식 명칭 확보
  → 좌표 비교로 올바른 결과인지 검증 (500m 이내)
  → Google/Kakao 유형 → waypoint_type[] 규칙 매핑
  → 매핑 실패 or 애매한 것들 → Gemini로 보조 판단
  → description 생성: Gemini (이름 + 검색 결과 + tips 기반)
```

### Step 3: DB 적재
- `waypoints` 테이블 생성 (init_db.py 또는 SQL 직접)
- 보강된 POI 데이터 INSERT
- `route_waypoints`는 코스별 along-route 매칭 후 별도 적재

### Step 4: 공간 쿼리 API
- `POST /api/waypoints/along-route` — 경로 주변 500m 이내 WP 반환
- `GET /api/waypoints/nearby` — 단일 좌표 근접 검색

---

## 3. 미결정 사항
- [ ] Google Places vs Kakao Local API 선택
- [ ] 검색 실패 시 fallback 전략 (이름만으로 Gemini?)
- [ ] tips 언어 정리 (독일어/영어 → 한국어 번역 여부)
- [ ] 이미지 활용 방안 (LLM 설명 생성에는 불필요, UI용으로 나중에?)

---

## 4. 파일 구조
```
crawl_data/
├── KOMOOT_FULL/           # 원본 크롤링 데이터 (882개 코스)
│   └── {tour_id}/
│       ├── metadata.json
│       ├── *.gpx
│       └── images/
├── waypoints_map.html     # 지도 시각화 (POI 분포)
└── refine/
    ├── docs/
    │   └── waypoint-refine-plan.md  # 이 문서
    ├── merge_candidates.json        # Phase 2 병합 후보 37쌍
    ├── merge_result_gemini.json     # Phase 2 병합 결과 (검토 완료)
    ├── merge_similar_waypoints.py   # Phase 2 병합 스크립트
    ├── unique_pois.json             # (예정) 최종 유니크 POI 데이터셋
    └── enrich_pois.py               # (예정) 외부 API 보강 스크립트
```
