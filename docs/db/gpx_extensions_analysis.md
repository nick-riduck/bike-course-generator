# GPX vs TCX Format Analysis for Riduck

이 문서는 GPX와 TCX 파일의 표준 구조와 주요 글로벌 서비스들의 확장 데이터 저장 방식을 분석하여, Riduck의 데이터 전략 수립을 위한 가이드를 제공합니다.

---

## 1. 포맷별 핵심 비교 요약

| 구분 | GPX (GPS Exchange Format) | TCX (Training Center XML) |
| :--- | :--- | :--- |
| **주 목적** | **범용 호환성**, 위치 기록 (Trace) | **피트니스 기기**, 훈련/코스 안내 (Course) |
| **단위 데이터** | `<trkpt>` (Track Point) | `<Trackpoint>` + `<CoursePoint>` |
| **안내 방식** | 선 형태의 경로 (Breadcrumb) | **지점 기반 알림 (Turn-by-turn)** |
| **필수 데이터** | Lat, Lon, Ele | Lat, Lon, Ele, **DistanceMeters** |
| **Riduck 전략** | **데이터 보존 및 재편집용 (Master)** | **기기 전송 및 내비게이션용 (Export)** |

---

## 2. 표준 포맷 구조 (Vanilla)

### 2.1 GPX v1.1 표준
가장 범용적인 포맷으로, 경로의 기하학적 형상 저장에 집중합니다.

```xml
<gpx version="1.1" creator="Standard" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Route Name</name>
    <trkseg>
      <trkpt lat="37.51157" lon="126.99964">
        <ele>10.5</ele>
        <time>2026-02-20T10:00:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
```

### 2.2 TCX v2 표준
가민 기기용으로 설계되었으며, 내비게이션 및 훈련 정보 기록에 최적화되어 있습니다.

```xml
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Courses>
    <Course>
      <Track>
        <Trackpoint>
          <Position>
            <LatitudeDegrees>37.51157</LatitudeDegrees>
            <LongitudeDegrees>126.99964</LongitudeDegrees>
          </Position>
          <AltitudeMeters>10.5</AltitudeMeters>
          <DistanceMeters>0.0</DistanceMeters> <!-- 누적 거리 필수 -->
        </Trackpoint>
      </Track>
    </Course>
  </Courses>
</TrainingCenterDatabase>
```

---

## 3. 서비스별 고유 정보 저장 방식 분석

### 3.1 GPX 확장 사례

#### A. 라이딩 가즈아 (Legacy)
표준을 무시하고 태그 내부에 커스텀 속성을 직접 삽입하는 방식입니다.
- **방식:** `<trkpt>` 내 속성(Attribute) 추가
- **데이터:** `sectionIndex`, `originalElevation` 등

```xml
<trkpt lat="37.53256" lon="127.10897" sectionIndex="0" originalElevation="11.2">
  <ele>11.2</ele>
</trkpt>
```

#### B. Komoot
표준 POI 태그인 `<wpt>`를 활용하여 아이콘 정보를 담습니다.
- **방식:** `<wpt>` + `<sym>` 태그 활용
- **데이터:** 지점의 성격(Flag, Bridge, Food 등)

```xml
<wpt lat="50.117042" lon="8.707900">
  <name>Habsburgerallee</name>
  <sym>Flag, Blue</sym>
</wpt>
```

#### C. Ride with GPS (RWGPS) - Route
경로 자체를 안내 포인트의 집합으로 정의합니다.
- **방식:** `<rte>` + `<rtept>` 태그 활용
- **데이터:** `<name>`(회전 방향), `<cmt>`(안내 문구)

```xml
<rtept lat="37.51946" lon="127.07085">
  <name>Slight Left</name>
  <cmt>Bicycle Path로 좌측 유지</cmt>
</rtept>
```

#### D. Strava / Garmin
운동 센서 데이터를 표준 확장 네임스페이스에 담습니다.
- **방식:** `<extensions>` + `gpxtpx:TrackPointExtension`
- **데이터:** 심박, 케이던스, 파워 등

```xml
<trkpt lat="37.51" lon="127.01">
  <extensions>
    <gpxtpx:TrackPointExtension>
      <gpxtpx:hr>145</gpxtpx:hr>
      <gpxtpx:cad>90</gpxtpx:cad>
    </gpxtpx:TrackPointExtension>
  </extensions>
</trkpt>
```

---

### 3.2 TCX 확장 사례 (내비게이션 최적화)

#### A. Ride with GPS (RWGPS) - Course
내비게이션 기기(가민 등)가 직접 인식할 수 있는 전용 알림 포인트를 사용합니다.
- **방식:** `<CoursePoint>` 태그 활용
- **데이터:** `PointType`(아이콘 타입), `Notes`(알림 메시지)

```xml
<CoursePoint>
  <Name>Left Turn</Name>
  <Position>
    <LatitudeDegrees>37.51946</LatitudeDegrees>
    <LongitudeDegrees>127.07085</LongitudeDegrees>
  </Position>
  <PointType>Left</PointType> <!-- 기기가 인식하는 화살표 아이콘 -->
  <Notes>Hangang Path로 좌회전하세요</Notes>
</CoursePoint>
```

---

## 4. Riduck 내부 데이터 구조 (Standard JSON v1.0 + Editor Extension)

Riduck은 시뮬레이션 및 차트 생성을 위해 위 표준들을 통합한 JSON 포맷을 내부적으로 사용합니다.

```json
{
  "version": "1.0",
  "meta": {
    "creator": "Riduck Unified Parser",
    "surface_map": { "1": "asphalt", "2": "concrete", "5": "cycleway", "7": "gravel" }
  },
  "stats": { "distance": 15200.5, "ascent": 350.2 },
  "points": {
    "lat": [37.50, 37.51, ...],
    "lon": [127.00, 127.01, ...],
    "ele": [10.5, 11.2, ...],
    "dist": [0.0, 15.2, ...],   // TCX 거리 정보용
    "grade": [0.0, 0.02, ...],
    "surf": [1, 1, 5, ...]       // 노면 정보
  },
  "segments": {
    "p_start": [0, 150, ...],   // GPX trkseg 분리용
    "p_end": [149, 300, ...]
  },
  "editor_state": { // (Optional) 사용자 편집 메타데이터
    "sections": [
      {
        "id": "s1_uuid",
        "name": "Section 1",
        "color": "#2a9e92",
        "points": [
          {
            "id": "p_start",
            "type": "section_start",
            "lat": 37.500000,
            "lng": 127.000000,
            "name": "Section 1",
            "dist_km": 0.000000
          },
          {
            "id": "p_via_1",
            "type": "via",
            "lat": 37.510000,
            "lng": 127.010000,
            "name": "CP1",
            "dist_km": 1.245678
          }
        ],
        "segments": [{ "...": "..." }]
      }
    ]
  }
}
```

### 4.1 `editor_state.sections[].points[].dist_km` 규칙

1. 단위는 **km**이며 `number`(float) 타입으로 저장합니다.
2. 값은 **전체 경로 시작점 기준 누적거리**입니다. (섹션 시작 기준이 아님)
3. 같은 경로 내 waypoint 순서대로 **단조 증가(또는 동일)** 해야 합니다.
4. 권장 정밀도는 소수점 6자리(`0.000001km`)입니다.
5. GPX/TCX 왕복 시 손실 방지를 위해 Export 시 반드시 메타로 직렬화하고, Import 시 우선 복원합니다.

---

## 5. Riduck 데이터 매핑 가이드 (Mapping Guide)

JSON 데이터를 GPX/TCX로 내보내거나(Export), 다시 불러올 때(Import)의 데이터 매핑 규칙입니다.
**핵심 전략:** 호환성과 파편화 방지를 위해 **트랙은 하나로 합치고(Merge All), 섹션 구분은 웨이포인트(WayPoint)를 사용**합니다.

### 5.1 JSON → GPX (내보내기)

| Riduck JSON | GPX Tag (Target) | 설명 |
| :--- | :--- | :--- |
| **`points`** | **`<trkseg>`** | **모든 좌표(`lat/lon/ele`)를 순서대로 나열하여 단일 `<trkseg>` 안에 `<trkpt>`로 저장.** |
| `dist_km namespace` | `<gpx xmlns:riduck="https://riduck.dev/xmlns/1">` | `dist_km` 저장용 커스텀 namespace 선언 |
| **Section 구분** | `<wpt>` | **섹션 시작점마다 웨이포인트 생성.** |
| `section.name` | `<wpt><name>` | "Section 1", "Uphill Start" 등 이름 저장 |
| `section.color` | `<wpt><desc>` | `Color:#2a9e92` 형식으로 설명 필드에 메타데이터 저장 |
| `section.type` | `<wpt><sym>` | `Riduck_Section_Start` (커스텀 심볼 사용) |
| `editor_state.points` | `<wpt>` | 일반 POI(보급, 정상)도 표준 `<wpt>`로 저장 |
| `section.points[].dist_km` | `<wpt><extensions><riduck:dist_km>` | waypoint의 누적 거리(km)를 저장 (소수점 6자리 권장) |
| `section.points[].dist_km`(Fallback) | `<wpt><desc>` | `Riduck_DistKm=1.245678` 토큰 추가 저장 (extensions 유실 대비) |

### 5.2 GPX → JSON (불러오기 & 복원)

| GPX Tag (Source) | Riduck JSON | 복원 로직 |
| :--- | :--- | :--- |
| `<trkseg>` | `points` (Merge) | 파일 내 모든 `<trkseg>`를 **하나의 리스트로 강제 병합.** (추후수정) |
| `<wpt>` (Section) | `segments` | `sym`이 `Riduck_Section_Start`인 웨이포인트를 찾아 **해당 위치에서 섹션 분할.** |
| `<wpt><desc>` | `section.color` | `Color:#...` 패턴을 파싱하여 색상 복원. |
| `<wpt>` (POI) | `editor_state.points` | 일반 웨이포인트는 지도 마커로 매핑. |
| `<wpt><extensions><riduck:dist_km>` | `section.points[].dist_km` | **최우선 복원 소스** |
| `<wpt><desc>`의 `Riduck_DistKm=` | `section.points[].dist_km` | extensions 미존재 시 fallback 복원 |
| `dist_km` 메타 없음 | `section.points[].dist_km` | 웨이포인트를 트랙에 투영해 누적거리 재계산(근사치) |

---

### 5.3 JSON → TCX (내보내기)

| Riduck JSON | TCX Tag (Target) | 설명 |
| :--- | :--- | :--- |
| **`points`** | **`<Track>`** | **모든 좌표를 순서대로 나열하여 단일 `<Track>` 안에 `<Trackpoint>`로 저장.** |
| **Section 구분** | `<CoursePoint>` | **섹션 시작점마다 코스포인트 생성.** |
| `section.name` | `<Name>` | "Section 1" |
| `section.type` | `<PointType>` | `Generic` (표준 타입 사용) |
| `section.color` | `<Notes>` | `Riduck_Section:Color=#2a9e92` 형식으로 노트 저장 |
| `editor_state.points` | `<CoursePoint>` | 일반 POI는 `Food`, `Summit` 등 표준 타입 매핑 |
| `section.points[].dist_km` | `<CoursePoint><Extensions><riduck:dist_km>` | waypoint 누적 거리(km) 저장 |
| `section.points[].dist_km`(Fallback) | `<CoursePoint><Notes>` | `Riduck_DistKm=1.245678` 토큰 병행 저장 |

### 5.4 TCX → JSON (불러오기)

| TCX Tag (Source) | Riduck JSON | 복원 로직 |
| :--- | :--- | :--- |
| `<Track>` / `<Lap>` | `points` (Merge) | `<Lap>` 구분 무시하고 **모든 트랙포인트를 하나로 병합.** |
| `<CoursePoint>` (Section) | `segments` | `<Notes>`에 `Riduck_Section` 키워드가 있는 지점에서 섹션 분할. |
| `<CoursePoint>` (POI) | `editor_state.points` | 일반 코스포인트는 지도 마커로 매핑. |
| `<CoursePoint><Extensions><riduck:dist_km>` | `section.points[].dist_km` | **최우선 복원 소스** |
| `<CoursePoint><Notes>`의 `Riduck_DistKm=` | `section.points[].dist_km` | extensions 미존재 시 fallback 복원 |
| `dist_km` 메타 없음 | `section.points[].dist_km` | 코스포인트를 트랙에 투영해 누적거리 재계산(근사치) |

---

## 6. 변환 예시 (Conversion Examples)

실제 데이터가 어떻게 변환되는지 보여주는 구체적인 예시입니다.

### 6.0 실제 예시 파일 (검증용)

- JSON 소스: `docs/db/examples/dist_km_roundtrip_example.json`
- GPX Export 샘플: `docs/db/examples/dist_km_roundtrip_example.gpx`
- TCX Export 샘플: `docs/db/examples/dist_km_roundtrip_example.tcx`

위 3개 파일은 `dist_km`를 **extensions + fallback(desc/notes)** 모두 포함하도록 작성되었습니다.

### 6.1 JSON → GPX (Export Flow) - **NEW Strategy**

**Source (Riduck JSON):**
```json
{
  "points": { ... }, // 10km track
  "segments": { "p_start": [0, 500] }, // 0~500: Section 1, 500~End: Section 2
  "editor_state": {
    "sections": [
      {
        "name": "Warmup",
        "color": "#00ff00",
        "points": [{ "type": "section_start", "dist_km": 0.000000 }]
      },
      {
        "name": "Main Climb",
        "color": "#ff0000",
        "points": [{ "type": "section_start", "dist_km": 5.000000 }]
      }
    ]
  }
}
```

**Flow Steps (필수):**
1. `editor_state.sections[].points[]`를 순회하며 waypoint 목록을 생성한다.
2. 각 waypoint의 `dist_km`를 읽고, 없으면 세그먼트 기하(geometry) 기준 누적거리로 계산한다.
3. GPX 루트에 `xmlns:riduck="https://riduck.dev/xmlns/1"`를 선언한다.
4. 각 waypoint를 `<wpt>`로 직렬화하고 `riduck:dist_km`를 `<extensions>`에 기록한다.
5. 확장 유실 대비로 `<desc>`에도 `Riduck_DistKm=<value>` 토큰을 함께 기록한다.
6. 트랙은 모든 세그먼트를 하나의 `<trk><trkseg>`로 병합해 `<trkpt>`를 생성한다.

**Target (GPX):**
```xml
<gpx ... xmlns:riduck="https://riduck.dev/xmlns/1">
  <!-- 1. Section Markers (Defined as Waypoints) -->
  <wpt lat="37.50" lon="127.00">
    <name>Warmup</name>
    <sym>Riduck_Section_Start</sym>
    <desc>Color:#00ff00;Riduck_DistKm=0.000000</desc>
    <extensions>
      <riduck:dist_km>0.000000</riduck:dist_km>
    </extensions>
  </wpt>
  
  <wpt lat="37.55" lon="127.05">
    <name>Main Climb</name>
    <sym>Riduck_Section_Start</sym>
    <desc>Color:#ff0000;Riduck_DistKm=5.000000</desc>
    <extensions>
      <riduck:dist_km>5.000000</riduck:dist_km>
    </extensions>
  </wpt>

  <!-- 2. Track (Merged) -->
  <trk>
    <trkseg>
      <trkpt lat="37.50" lon="127.00"><ele>10</ele></trkpt>
      ... (All points contiguous) ...
      <trkpt lat="37.60" lon="127.10"><ele>500</ele></trkpt>
    </trkseg>
  </trk>
</gpx>
```

### 6.2 GPX → JSON (Import Flow)

**Source (GPX):**
```xml
<gpx>
  <!-- Section Marker Found -->
  <wpt lat="37.55" lon="127.05">
    <sym>Riduck_Section_Start</sym>
    <desc>Color:#ff0000</desc>
  </wpt>

  <trk>
    <!-- Fragmented Track (e.g. signal loss) -->
    <trkseg> ... (0km ~ 5km) ... </trkseg>
    <trkseg> ... (5km ~ 10km) ... </trkseg>
  </trk>
</gpx>
```

**Target (Riduck JSON):**
1.  **Merge:** 두 `<trkseg>`를 합쳐 0~10km의 단일 트랙 생성.
2.  **Scan:** `<wpt>` 중 `Riduck_Section_Start` 검색.
3.  **Split:** 해당 웨이포인트 좌표와 가장 가까운 트랙 포인트(약 5km 지점)를 찾아 `segments` 분할.
4.  **Restore:** 색상(`#ff0000`) 복원.
5.  **Restore `dist_km`:** `extensions/riduck:dist_km` 우선, 없으면 `desc`의 `Riduck_DistKm=` 파싱, 둘 다 없으면 투영 계산.

---

### 6.3 JSON → TCX (Export Flow)

**Source (Riduck JSON):**
```json
{
  "editor_state": {
    "sections": [
      {
        "name": "Warmup",
        "color": "#00ff00",
        "points": [{ "type": "section_start", "dist_km": 0.000000 }]
      },
      {
        "name": "Main Climb",
        "color": "#ff0000",
        "points": [{ "type": "section_start", "dist_km": 5.000000 }]
      }
    ]
  }
}
```

**Target (TCX):**
```xml
<TrainingCenterDatabase ...>
  <Courses>
    <Course>
      <Name>My Route</Name>
      <Lap> ... (One Giant Lap) ... </Lap>
      
      <Track>
        <Trackpoint> ... </Trackpoint>
        ...
      </Track>
      
      <!-- Section Marker via CoursePoint -->
      <CoursePoint>
        <Name>Main Climb</Name>
        <PointType>Generic</PointType>
        <Notes>Riduck_Section:Color=#ff0000;Riduck_DistKm=5.000000</Notes>
        <Extensions>
          <riduck:dist_km xmlns:riduck="https://riduck.dev/xmlns/1">5.000000</riduck:dist_km>
        </Extensions>
      </CoursePoint>
    </Course>
  </Courses>
</TrainingCenterDatabase>
```

**Flow Steps (필수):**
1. `editor_state.sections[].points[]`를 waypoint 순서대로 펼친다.
2. 각 point의 `dist_km`를 읽고, 없으면 세그먼트 기하로 누적거리(km) 재계산한다.
3. 모든 좌표는 단일 `<Track>`의 `<Trackpoint>`로 기록한다.
4. 모든 waypoint는 `<CoursePoint>`로 기록한다.
5. `dist_km`는 `<Extensions><riduck:dist_km>`에 기록하고, `<Notes>`에 `Riduck_DistKm=`를 fallback으로 병행한다.
6. Section 시작점은 `<Notes>`에 `Riduck_Section:Color=#...`를 유지해 구간 복원을 보장한다.

---
*Last Updated: 2026-02-24*
