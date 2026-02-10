# Project TODOs

## Infrastructure & Deployment
- [ ] **PR Preview Link Automation**: 현재 Firebase Hosting 프리뷰 배포는 되지만 PR에 댓글로 링크가 달리지 않음. `FirebaseExtended/action-hosting-deploy` 액션을 도입하거나 스크립트를 추가하여 PR 리뷰 효율성 증대 필요. (WIF 인증과 호환성 체크 필수)
- [ ] **Production Env Var Management**: 현재 CI 빌드 시 환경변수를 하드코딩 주입 중. GitHub Secrets로 이관하여 보안성 강화 필요.

## Feature Development
- [ ] **Course Save UI**: 프론트엔드에 코스 저장 버튼 및 모달 구현.
- [ ] **My Library**: 저장된 코스 목록 조회 및 불러오기 UI 구현.
- [ ] **Route Detail Page**: `route_num` 기반의 코스 상세 페이지 및 공유 기능.

## Refactoring
- [ ] **Frontend API Client**: `fetch` 호출을 추상화하여 중복 코드 제거 및 에러 처리 통일.
