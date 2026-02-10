# UI/UX Refactoring Plan: Bike Course Planner

## 1. Overview
현재의 "지도 위 떠다니는 위젯" 형태에서 **"사이드바 기반의 체계적인 레이아웃"**으로 전환하여, 코스 생성뿐만 아니라 **저장 및 관리(Library)** 기능을 효과적으로 수용한다.

## 2. Layout Structure

### 2.1 Global Layout
- **Header (Top)**
  - Logo: "Riduck Route Planner"
  - User Menu: 로그인 상태 표시, 프로필 이미지, 로그아웃 버튼. (비로그인 시 "Google Login" 버튼)
- **Sidebar (Left, Width: 320px ~ 400px)**
  - 핵심 컨트롤 패널. 탭(Tab) 구조로 기능을 분리.
- **Map View (Right, Flex-grow)**
  - 전체 화면 지도.
  - Elevation Chart는 지도 하단에 오버레이 또는 별도 패널로 배치.

### 2.2 Sidebar Components

#### Header Search (Top of Sidebar)
- **Search Bar:** 장소 검색 창.
  - **Engine:** **Photon (by Komoot)** API 사용 (무료, 전 세계 장소 검색 지원).
  - **Interaction:** 장소 선택 시 해당 좌표로 지도 이동 (`flyTo`).

#### Tab 1: Planner (코스 생성)
- **Stats Summary:** 거리(km), 획득고도(m)를 큼직하게 표시.
- **Action Buttons:** `Undo`, `Redo`, `Clear`
- **Export & Save:** `Download GPX`, `Save Route`

#### Tab 2: Library (내 코스 목록)
- **Course List:** 저장된 코스 카드 목록.
  - 클릭 시 로딩, 삭제 기능 포함.

### 2.3 Map View Enhancements
- **Detailed Map Style:** 건물, POI(관심 지점), 지형 정보가 포함된 상세 스타일로 변경. (기존 Dark 모드에서 가독성 높은 스타일로 전환)
- **Layer Switcher:** (Optional) Satellite, Outdoors, Street 등 레이어 선택 기능.

## 3. Interaction Flow

### 3.1 Course Save (저장)
1. 사용자가 `Save Route` 버튼 클릭.
2. **Check Auth:**
   - 비로그인 상태: "로그인이 필요한 기능입니다." 알림 후 로그인 모달/팝업 호출.
   - 로그인 상태: "코스 저장" 모달 팝업.
3. **Save Modal:**
   - 입력 필드: 코스 제목(Title), 설명(Description - 선택).
   - `저장` 클릭 시 백엔드 API (`POST /api/routes`) 호출.
4. **Post-Save:**
   - 성공 메시지(Toast) 표시.
   - 사이드바의 **Library 탭**으로 자동 전환되어 방금 저장한 코스가 목록 최상단에 표시됨.

### 3.2 Load Course (불러오기)
1. Library 탭에서 코스 카드 클릭.
2. **Confirmation:** "현재 편집 중인 코스가 사라집니다. 불러오시겠습니까?" (편집 내용이 있을 경우)
3. **Load:**
   - 백엔드에서 코스 상세 데이터(`summary_path`) 로딩.
   - 지도에 경로 그리기 (`setSegments`, `setPoints` 상태 업데이트).
   - Planner 탭으로 자동 전환.

---

## 4. Implementation Steps (Prioritized)

1. **Sidebar Layout:** `App.jsx` 구조 변경 (Grid -> Flex Sidebar).
2. **Save Feature:** `Save Route` 버튼 및 제목 입력 `prompt` (임시) 구현.
3. **Library Feature:** `GET /api/routes` 연동 및 목록 표시.
4. **Detail Polish:** 모달 컴포넌트, 탭 전환 애니메이션, 반응형 대응.
