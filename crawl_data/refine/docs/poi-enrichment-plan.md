# POI 외부 데이터 보강 계획 (Step 2)

## 목표
`unique_pois.json` 1,528개 POI에 대해:
1. **Gemini 3.1 Pro + Google Search grounding** → description, waypoint_type[], 주소, 주변 랜드마크 생성 (메인)
2. **Google Places API + Kakao Local API** → 좌표/이름 기반 cross-check 검증 (보조)

---

## 1. 전략 개요

### 기존 계획 (폐기)
```
Google Places → types 추출 → waypoint_type 매핑
Kakao Local   → 주소 추출
Gemini        → description 생성 (보조)
```

### 변경된 계획
```
Phase A: Gemini 3.1 Pro + Google Search grounding (메인)
  → description + waypoint_type[] + address + nearby_landmarks 한 번에 추출
  → Gemini가 직접 구글 검색해서 그라운딩 → hallucination 방지

Phase B: Google Places + Kakao Local (검증용)
  → Gemini 결과의 정확성 cross-check
  → 매치 실패/불일치 POI 플래그
```

**이유:**
- Google Places는 types만 줌, description 없음
- Kakao는 주소/카테고리만 줌
- 결국 description은 LLM이 만들어야 함 → 그러면 처음부터 Gemini에게 검색 툴 주고 다 맡기는 게 효율적
- 라이더 관점 description이 필요 → 지도 API의 정형 데이터보다 검색 기반 자연어가 적합

---

## 2. Phase A: Gemini 3.1 Pro + Google Search Grounding

### 2a. API 호출 방식

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)

tool = types.Tool(google_search=types.GoogleSearch())

response = client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        tools=[tool],
        temperature=0.3,
        response_mime_type="application/json",
    ),
)
```

### 2b. 프롬프트 설계

```
당신은 한국 자전거 라이딩 전문가입니다.
아래 POI(관심 지점)에 대해 구글 검색을 활용하여 정보를 수집하고,
자전거 라이더 관점에서 정리해주세요.

## POI 정보
- 이름: {name}
- 좌표: {lat}, {lng}
- Komoot 카테고리: {category}
- 등장 코스 수: {tour_count}개
{tips가 있으면: - 사용자 팁: "{tips_text}"}

## 요청 사항
1. 이곳이 어떤 장소인지 구글 검색으로 확인
2. 자전거 라이더에게 유용한 정보 중심으로 정리

## 출력 (JSON)
{
  "description": "라이더 관점 1~2줄 설명 (한국어)",
  "waypoint_type": ["타입1", "타입2"],  // 아래 ENUM 중 선택 (1~3개)
  "address": "도로명주소 또는 지번주소",
  "nearby_landmarks": ["주변 랜드마크1", "랜드마크2"],
  "confidence": "high|medium|low"  // 검색 결과 신뢰도
}

## waypoint_type ENUM (반드시 이 중에서만 선택)
convenience_store, cafe, restaurant, restroom, water_fountain,
rest_area, bike_shop, parking, transit, bridge, tunnel, checkpoint,
viewpoint, river, lake, mountain, beach, park, nature,
historic, landmark, museum, hospital, police, other
```

### 2c. 배치 처리

- 1,528개를 **1건씩** 호출 (Google Search grounding은 배치 불가)
- 중간 저장: 50건마다 `enriched_gemini_progress.json`에 저장
- 재시작 가능: 이미 처리된 POI는 스킵
- Rate limit: 2 QPS (Gemini 3.1 Pro 기준) → ~13분

### 2d. 예상 출력 예시

```json
{
  "name": "광나루 자전거공원 인증센터",
  "description": "한강 자전거도로 광나루 구간의 국토종주 인증센터. 광나루한강공원 내에 위치하며, 자전거 보관대와 간단한 정비 도구를 구비.",
  "waypoint_type": ["checkpoint", "park"],
  "address": "서울특별시 강동구 선사로 129",
  "nearby_landmarks": ["암사동 선사유적지", "광나루한강공원 수영장"],
  "confidence": "high"
}
```

```json
{
  "name": "비반령 고개",
  "description": "청주 라이더들의 대표 업힐 코스. 5~7% 경사가 약 5km 이어지며, 정상에서 조망이 좋다.",
  "waypoint_type": ["mountain", "viewpoint"],
  "address": "충청북도 청주시 상당구",
  "nearby_landmarks": ["상당산성"],
  "confidence": "medium"
}
```

---

## 3. Phase B: Google Places + Kakao Local (검증용)

### 3a. 목적
Gemini가 생성한 결과를 좌표/이름 기반으로 cross-check:
- **address 검증**: Kakao 주소와 Gemini 주소 비교
- **waypoint_type 검증**: Google types와 Gemini type 비교
- **존재 여부 확인**: API에서 500m 이내 매치가 없으면 → Gemini 결과 의심

### 3b. Google Places Text Search

```
POST https://places.googleapis.com/v1/places:searchText
Header: X-Goog-Api-Key, X-Goog-FieldMask
Body: {
  "textQuery": "{poi_name}",
  "locationBias": {
    "circle": { "center": {"lat": ..., "lng": ...}, "radius": 500.0 }
  },
  "languageCode": "ko",
  "maxResultCount": 3
}
FieldMask: places.displayName,places.formattedAddress,places.types,places.location
```

**비용:** ~$49 (월 $200 무료 크레딧 내)

### 3c. Kakao Local 키워드 검색

```
GET https://dapi.kakao.com/v2/local/search/keyword.json
Header: Authorization: KakaoAK {REST_API_KEY}
Params: query={poi_name}&x={lng}&y={lat}&radius=500&size=3&sort=distance
```

**비용:** 무료

### 3d. 검증 규칙

```
각 POI에 대해:
  google_match = Google 결과 중 500m 이내 + 이름 유사도 0.4+
  kakao_match  = Kakao 결과 중 500m 이내 + 이름 유사도 0.4+

  validation_status:
    "verified"   → Google OR Kakao 매치 있음 + Gemini 결과와 일관성
    "partial"    → 매치는 있으나 type이나 주소 불일치
    "unverified" → 매치 없음 (자연지형, 비공식 명칭 등)
    "conflict"   → API 결과와 Gemini 결과가 명백히 다름 → 수동 리뷰
```

---

## 4. 매핑 테이블 (검증 시 활용)

### 4a. Google types → waypoint_type

| Google place type | → waypoint_type |
|---|---|
| `convenience_store` | `convenience_store` |
| `cafe`, `bakery` | `cafe` |
| `restaurant`, `meal_delivery` | `restaurant` |
| `park`, `amusement_park` | `park` |
| `transit_station`, `train_station`, `bus_station`, `subway_station` | `transit` |
| `hospital`, `doctor` | `hospital` |
| `police` | `police` |
| `bicycle_store` | `bike_shop` |
| `parking` | `parking` |
| `museum` | `museum` |
| `tourist_attraction`, `point_of_interest` | `landmark` |
| `natural_feature` | `nature` |

### 4b. Kakao category_group_code → waypoint_type

| Kakao code | 의미 | → waypoint_type |
|---|---|---|
| CE7 | 카페 | `cafe` |
| FD6 | 음식점 | `restaurant` |
| CS2 | 편의점 | `convenience_store` |
| AT4 | 관광명소 | `landmark` |
| CT1 | 문화시설 | `museum` |
| SW8 | 지하철역 | `transit` |
| HP8 | 병원 | `hospital` |
| PK6 | 주차장 | `parking` |

### 4c. Komoot 카테고리 → waypoint_type (최종 fallback)

API 매치도 Gemini도 실패한 경우:

| Komoot category | → waypoint_type |
|---|---|
| `bridge` | `bridge` |
| `viewpoint` | `viewpoint` |
| `river`, `190` | `river` |
| `cafe` | `cafe` |
| `facilities` | `rest_area` |
| `cycle_way` | `other` |
| `trail` | `nature` |
| `historical_site` | `historic` |
| `settlement`, `219` | `landmark` |
| `12` (해변) | `beach` |
| `21` (산) | `mountain` |
| `mountain_pass` | `mountain` |

---

## 5. 실행 단계

### Step 1: Gemini + Google Search grounding (메인 추출)
```
script:  crawl_data/refine/enrich_with_gemini.py
input:   crawl_data/refine/unique_pois.json (1,528개)
output:  crawl_data/refine/enriched_gemini.json
```
- Gemini 3.1 Pro + GoogleSearch 툴
- POI별 1건씩 호출, 50건마다 중간 저장
- 예상: ~13분 (2 QPS), 비용: Gemini API 토큰 비용만

### Step 2: Google Places + Kakao Local (검증 데이터 수집)
```
script:  crawl_data/refine/collect_verification_data.py
input:   crawl_data/refine/unique_pois.json
output:  crawl_data/refine/verification_raw.json
```
- Google Text Search + Kakao 키워드 검색 병렬 호출
- 예상: ~20분, 비용: Google ~$49 (무료 크레딧 내) + Kakao 무료

### Step 3: Cross-check + 최종 병합
```
script:  crawl_data/refine/validate_and_merge.py
input:   enriched_gemini.json + verification_raw.json
output:  crawl_data/refine/enriched_pois.json (최종)
```
- Gemini 결과를 API 결과로 검증
- validation_status 부여 (verified/partial/unverified/conflict)
- conflict POI 목록 출력 → 수동 리뷰

### Step 4: 수동 리뷰 + DB 적재
- conflict POI 확인/수정
- `enriched_pois.json` → `waypoints` 테이블 INSERT SQL 생성

---

## 6. 최종 출력 형식

`enriched_pois.json`:
```json
{
  "name": "광나루 자전거공원 인증센터",
  "description": "한강 자전거도로 광나루 구간의 국토종주 인증센터. 광나루한강공원 내 위치.",
  "waypoint_type": ["checkpoint", "park"],
  "address": "서울특별시 강동구 선사로 129",
  "nearby_landmarks": ["암사동 선사유적지", "광나루한강공원"],
  "lat": 37.546545,
  "lng": 127.120215,
  "confidence": "high",
  "validation_status": "verified",
  "source": {
    "komoot_category": "facilities",
    "gemini_raw_type": ["checkpoint", "park"],
    "google_types": ["park", "point_of_interest"],
    "kakao_category": "AT4 > 관광명소 > 공원",
    "kakao_address": "서울 강동구 암사동 508-1",
    "match_method": "gemini+google+kakao"
  },
  "tour_count": 45,
  "has_images": true,
  "has_tips": true
}
```

---

## 7. 필요한 API 키

| API | 환경변수 | 용도 | 확인 |
|---|---|---|---|
| Gemini 3.1 Pro | `GEMINI_API_KEY` | 메인 추출 | [x] 기존 사용 중 |
| Google Places API | `GOOGLE_MAPS_API_KEY` | 검증용 | [ ] |
| Kakao Local API | `KAKAO_REST_API_KEY` | 검증용 | [ ] |

---

## 8. 비용 요약

| 항목 | 비용 |
|---|---|
| Gemini 3.1 Pro (1,528 calls) | ~$5~10 (토큰 기준) |
| Google Search grounding | 무료 (Gemini API 포함) |
| Google Places Text Search | ~$49 (월 $200 무료 내) |
| Kakao Local | 무료 |
| **합계** | **~$5~10 실비용** |

---

## 9. 리스크 & 대응

| 리스크 | 대응 |
|---|---|
| 2글자 이하 이름 (270개) Gemini 검색 실패 | 좌표 명시 + Komoot 카테고리 힌트 제공 |
| Gemini hallucination (검색 안 하고 지어냄) | Google/Kakao cross-check로 감지 |
| Gemini rate limit (3.1 Pro) | 2 QPS sleep, 중간 저장으로 재시작 |
| 자연지형 (강, 산, 고개) 검증 어려움 | Google/Kakao 매치 없어도 Komoot cat 기반 허용 |
| Google Places 무료 크레딧 소진 | 검증은 선택적 — Gemini confidence=high면 스킵 가능 |

---

## 10. 파일 구조

```
crawl_data/refine/
├── docs/
│   ├── waypoint-refine-plan.md          # 전체 계획
│   └── poi-enrichment-plan.md           # 이 문서
├── unique_pois.json                     # 입력: 1,528개 유니크 POI
├── enrich_with_gemini.py                # Step 1: Gemini + Google Search
├── enriched_gemini.json                 # Step 1 출력
├── collect_verification_data.py         # Step 2: Google Places + Kakao
├── verification_raw.json                # Step 2 출력
├── validate_and_merge.py               # Step 3: cross-check
├── enriched_pois.json                   # 최종 출력
└── generate_unique_pois.py              # (기존) Phase 1+2 병합
```
