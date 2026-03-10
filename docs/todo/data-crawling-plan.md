# 외부 코스 데이터 크롤링 & 정제 계획

## 목적
- 태그 자동 제안 시스템의 정확도 향상 (근접 태그 통계 신뢰도 확보)
- 코스 수 증가 → 근접 검색 커버리지 확대
- 크롤링 데이터는 **태그 검색/추천 엔진용**으로만 사용, 라이브러리에 직접 노출하지 않음

## 대상 소스

### 1. Komoot (내 계정)
- 로그인 후 bs4 크롤링
- 코스 메타: 제목, 지역, 난이도, 거리, 획득고도, 노면, 코스 유형
- GPX 다운로드 가능
- 한국 자전거 코스 커버리지: 중상

### 2. Ride with GPS (RWGPS)
- 내 계정 또는 공개 코스
- 코스 메타 + GPX
- 한국 코스 수: komoot 대비 적지만 로드바이크 특화 코스 다수

---

## DB 스키마 변경

### source ENUM 추가
```sql
CREATE TYPE route_source AS ENUM ('USER', 'SUIMI', 'KOMOOT', 'RWGPS', 'KORA');

ALTER TABLE routes ADD COLUMN source route_source DEFAULT 'USER' NOT NULL;
ALTER TABLE segments ADD COLUMN source route_source DEFAULT 'USER' NOT NULL;
```

### visibility 전략
- `source = 'USER'` or `'SUIMI'`: 라이브러리에 표시
- `source IN ('KOMOOT', 'RWGPS', 'KORA')`: 라이브러리에 **비노출**
  - 태그 검색/추천 엔진에만 사용
  - 근접 코스 태그 쿼리에 포함
  - 관리자 페이지에서만 조회 가능

```sql
-- 라이브러리 조회 (사용자 노출)
SELECT * FROM routes WHERE source IN ('USER', 'SUIMI') AND status = 'PUBLIC';

-- 태그 추천 엔진 (내부용, 모든 소스 포함)
SELECT t.slug, COUNT(*) FROM routes r
JOIN route_tags rt ON r.id = rt.route_id
JOIN tags t ON rt.tag_id = t.id
WHERE ST_DWithin(r.start_point, ..., 0.2)
  AND ST_DWithin(r.start_point::geography, ...::geography, 20000)
GROUP BY t.slug ORDER BY COUNT(*) DESC;
```

---

## 크롤링 파이프라인

### Phase 1: 수집 (Crawl)
```
[Komoot/RWGPS]
  → 로그인 (session cookie)
  → 코스 목록 페이지네이션
  → 코스별: 메타데이터 + GPX 다운로드
  → raw 저장: scripts/crawl_data/{source}/{id}/
      ├── meta.json    (제목, 지역, 난이도, 거리, 획득고도 등)
      └── course.gpx
```

### Phase 2: 변환 (Transform)
```
raw 데이터
  → GpxLoader.load() → Valhalla 표준화 → v1.0 JSON
  → 기존 import_suimi_routes.py 파이프라인 재사용
  → 출력: backend/storage/routes/{uuid}.json + SQL
```

### Phase 3: LLM 태그 생성 (Tag)
```
코스 메타 + 좌표 샘플
  → Gemini 2.5 Flash Lite 호출
  → 입력: {
      제목, 지역(크롤링 메타에서), 거리, 획득고도,
      좌표 샘플 15개, 고도 프로필,
      기존 태그 목록 (사용빈도 포함)
    }
  → 출력: 태그 리스트
  → 기존 태그 DB와 매칭 (slug 기준)
  → 새 태그는 자동 생성 허용
```

### Phase 4: 태그 정제 (Refine)
```
1차 생성된 태그
  → LLM 2차 검증:
    - 동일 지역 코스들의 태그 일관성 체크
    - 유사 태그 통합 (e.g., "해안" vs "해안도로")
    - 명백한 오분류 제거
  → 최종 태그 확정 → DB 적재
```

---

## 태그 품질 보장 전략

### 문제: 순환 참조
근접 태그 정확도가 기존 태그 품질에 의존하는 문제

### 해결: 다층 태그 소스
| 태그 유형 | 결정 방식 | 기존 태그 의존 |
|-----------|----------|--------------|
| 지역 (시/군/도) | 역지오코딩 or 크롤링 메타 | X |
| 특성 (힐클라임/평지) | stats 규칙 기반 | X |
| 테마 (투어/관광) | LLM + 근접 태그 힌트 | O (보조) |
| 시즌 (벚꽃/단풍) | LLM + 코스 설명 | X |

- 지역/특성 태그는 외부 데이터로 독립적 결정 → 오염 없음
- 테마 태그만 근접 힌트 사용 → 코스 수 증가 시 자연 수렴
- 시즌 태그는 코스 설명/제목에서 LLM이 추출

---

## 예상 데이터 규모
| 소스 | 예상 코스 수 | 비고 |
|------|------------|------|
| Suimi (기존) | 265 | 완료 |
| Komoot | 500~2000+ | 한국 공개 코스 기준 |
| RWGPS | 200~500 | 로드바이크 특화 |
| KORA (기존 크롤러) | ? | 공식 자전거길 |
| **합계** | **1000~3000+** | |

---

## 구현 순서
1. DB 스키마: `source` 컬럼 추가 + 마이그레이션
2. Komoot 크롤러 구현 (bs4, 내 계정)
3. 변환 파이프라인 (기존 GpxLoader 재사용)
4. LLM 태그 생성 + 정제
5. RWGPS 크롤러 추가
6. 자동 태그 제안 API에 근접 태그 쿼리 통합

## 미결정
- Komoot 크롤링 범위: 내 계정 저장 코스만? 지역별 공개 코스?
- rate limit / 크롤링 간격
- RWGPS API 사용 vs 웹 크롤링
- 크롤링 데이터 갱신 주기 (일회성? 주기적?)
