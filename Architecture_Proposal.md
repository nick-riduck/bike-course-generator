# 🏗️ Architecture & Infrastructure Proposal
**Project:** GPX Course Generator & Simulator
**Date:** 2026-01-30

## 1. Project Context
본 프로젝트는 사용자가 직접 GPX 경로를 생성하는 **Web Tool (Generator)**와 경로 데이터 및 외부 환경 변수를 결합하여 주행 시뮬레이션을 수행하는 **Core Engine (Simulator)**으로 구성됩니다.

### 📂 Current Project Structure (Local)
현재 프로젝트는 React 기반 프론트엔드와 시뮬레이션 핵심 로직이 공존하는 구조입니다.

```text
bike_course_generator/
├── frontend/                  # React Application (Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── BikeRoutePlanner.jsx  # 핵심: 경로 생성 UI
│   │   │   ├── MapViewer.jsx         # 핵심: 3D/2D 지도 시각화
│   │   │   └── ElevationChart.jsx    # 핵심: 고도 분석 차트
│   └── vite.config.js
└── Architecture_Proposal.md   # [New] 아키텍처 제안 문서
```

---

## 2. Proposed Infrastructure Architecture
GIS 데이터의 정밀한 처리와 확장성을 고려한 아키텍처 제안입니다.

### 🏛️ System Overview

- **Frontend**: **Firebase Hosting**
    - 빠른 로딩 속도(Global CDN) 및 간편한 CI/CD 파이프라인.
    - SSL 자동 적용 및 정적 자원 효율적 관리.
- **Backend (API & Routing)**: **VM (AWS EC2 / GCP Compute Engine)**
    - **OpenRouteService (ORS)**: Java 기반 라우팅 엔진으로, 그래프 데이터를 메모리에 상주시켜야 하므로 상시 구동되는 VM 환경이 필수적입니다 (Docker Compose 활용).
- **Database**: **PostgreSQL + PostGIS**
    - **Why?**: 위치 기반 데이터 처리에 있어 MySQL보다 강력한 공간 연산(Spatial Query) 성능과 정확성을 제공합니다.
    - 추후 "코스 검색", "구간 분석", "중복 경로 매칭" 등 복잡한 GIS 기능 구현 시 사실상의 표준(Standard)입니다.

### 🏛️ Data Storage Strategy
- **GPX 원본**: AWS S3 등 Object Storage에 저장하여 대용량 파일 관리 비용 최적화.
- **분석 데이터**: PostGIS 컬럼(LineString 등)에 핵심 경로 정보를 저장하여 고속 공간 검색 및 통계 산출.

---

## 3. Deployment Pipeline (CI/CD)

| Stage | Tool | Description |
| :--- | :--- | :--- |
| **Frontend** | GitHub Actions + Firebase | 코드 푸시 시 빌드 및 자동 배포 |
| **Backend** | Docker + GitHub Actions | 컨테이너 이미지화 및 VM 자동 배포 |
| **Monitoring**| Open-Meteo API 연동 | 실시간 날씨 데이터 수집 및 시뮬레이션 반영 |

---

## 4. Key Technical Decisions (Why this?)

1. **PostgreSQL vs MySQL**: GIS 데이터의 기하학적 연산(코스 간 거리 측정, 영역 내 검색 등)에서 PostGIS의 우수성 때문.
2. **VM for ORS**: ORS의 높은 메모리 점유율과 기동 시간 문제로 인해 Serverless 환경(Lambda 등) 사용이 불가함.
3. **Firebase**: 초기 구축 비용 0원 및 프론트엔드 관리의 극단적 편의성.

