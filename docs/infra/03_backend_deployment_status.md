# 🚀 백엔드 배포 상태 및 향후 조치 사항 (2026-02-04)

## 1. 현재 상태
- **서비스**: Google Cloud Run (`backend-fastapi`)
- **URL**: [https://backend-fastapi-388936157935.asia-northeast3.run.app](https://backend-fastapi-388936157935.asia-northeast3.run.app)
- **배포 방식**: GitHub Actions를 통한 자동 배포 (`main` 브랜치)
- **보안 설정**:
    - **최대 인스턴스**: 1개로 제한 (과금 방지)
    - **접근 권한**: 조직 정책(Domain Restricted Sharing)으로 인해 `allUsers` 접근 불가 상태. 현재는 IAM 인증을 통해서만 접속 가능.

## 2. 향후 조치 과제
### 🔓 백엔드 외부 노출 방법 (선택 필요)
- **방안 A (추천)**: `firebase.json`의 `rewrites` 설정을 사용하여 프론트엔드 도메인을 통해 백엔드 API 호출.
- **방안 B**: 조직 정책 수정 후 `allUsers` 허용 (보안상 비권장).

### 🔗 VPC 연동 (Valhalla 통신)
- 현재 백엔드와 Valhalla VM이 같은 VPC 안에 있으나, Cloud Run에서 접근하기 위한 **Serverless VPC Access Connector** 설정이 필요함.
- 연동 후 백엔드의 `VALHALLA_URL` 환경변수를 VM의 내부 IP로 변경해야 함.

## 3. 관련 명령어 (테스트용)
```bash
# 인증된 상태에서 접속 확인
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://backend-fastapi-388936157935.asia-northeast3.run.app/docs
```
