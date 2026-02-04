# 프론트엔드 배포 가이드 (Firebase Hosting + GitHub Actions)

이 문서는 React 프론트엔드를 Firebase Hosting에 배포하고, GitHub Actions를 통해 CI/CD(지속적 배포)를 구축하는 방법을 설명합니다. 특히 **Workload Identity Federation (WIF)**을 사용하여 서비스 계정 키(JSON) 없이 안전하게 인증하는 방법을 다룹니다.

## 1. 사전 준비

- Firebase 프로젝트 생성 (GCP 프로젝트와 동일)
- GitHub 리포지토리 연결
- `firebase-tools` 설치 (로컬 테스트용, CI에서는 필요 없음)

## 2. 프로젝트 설정 (로컬)

루트 디렉토리에 다음 파일들을 생성합니다.

### .firebaserc
배포할 타겟 프로젝트를 지정합니다.
```json
{
  "projects": {
    "default": "your-project-id"
  }
}
```

### firebase.json
배포할 폴더와 SPA 설정을 정의합니다.
```json
{
  "hosting": {
    "public": "frontend/dist",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

---

## 3. Workload Identity Federation (WIF) 설정

서비스 계정 키(JSON)를 GitHub Secrets에 저장하는 대신, 구글이 권장하는 WIF 방식을 사용합니다.

### 3.1. GCP 설정 (터미널)
다음 명령어들을 순서대로 실행하여 Identity Pool과 Provider를 생성합니다.

```bash
# 환경변수 설정
export PROJECT_ID="your-project-id"
export REPO="owner/repo" # 예: nick-riduck/bike-course-generator

gcloud config set project $PROJECT_ID

# 1. 서비스 계정 생성
gcloud iam service-accounts create "github-action-deploy" \
  --display-name="GitHub Actions Firebase Deployer"

# 2. 권한 부여 (필수 권한 3종 세트)
# - Firebase Admin: 전반적인 관리
# - Service Usage Consumer: API 사용량 체크
# - Firebase Hosting Admin: 호스팅 배포
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:github-action-deploy@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/firebase.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:github-action-deploy@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:github-action-deploy@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/firebasehosting.admin"

# 3. Workload Identity Pool 생성
gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 4. GitHub Provider 생성
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Actions Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$REPO'"

# 5. 서비스 계정과 Pool 연결
# (주의: projectNumber는 gcloud projects describe $PROJECT_ID --format="value(projectNumber)" 로 확인)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud iam service-accounts add-iam-policy-binding "github-action-deploy@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/$REPO"

# 6. 필수 API 활성화 (중요!)
gcloud services enable \
  iamcredentials.googleapis.com \
  firebase.googleapis.com \
  cloudresourcemanager.googleapis.com \
  firebasehosting.googleapis.com \
  serviceusage.googleapis.com
```

### 3.2. Provider 경로 확인
GitHub Actions에 사용할 경로를 확보합니다.
```bash
gcloud iam workload-identity-pools providers describe "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"
# 출력 예: projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider
```

---

## 4. GitHub Actions 설정 (.github/workflows/firebase-hosting.yml)

WIF 인증을 통해 `firebase-tools`가 자동으로 인증된 상태로 배포하도록 구성합니다.

```yaml
name: Deploy to Firebase Hosting

on:
  push:
    branches:
      - main
  pull_request:

jobs:
  build_and_deploy:
    runs-on: ubuntu-latest
    
    # WIF 토큰 발급을 위해 필수
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      # Google Cloud 인증 (WIF)
      # access_token을 직접 발급받아 FIREBASE_TOKEN 환경변수에 주입하는 것이 가장 확실함
      - id: 'auth'
        name: 'Authenticate to Google Cloud'
        uses: 'google-github-actions/auth@v2'
        with:
          workload_identity_provider: 'projects/YOUR_PROJECT_NUMBER/.../providers/github-provider'
          service_account: 'github-action-deploy@your-project-id.iam.gserviceaccount.com'
          token_format: 'access_token'

      - name: Set Firebase Token
        run: echo "FIREBASE_TOKEN=${{ steps.auth.outputs.access_token }}" >> $GITHUB_ENV

      - name: Install Dependencies
        run: cd frontend && npm ci

      - name: Build
        run: cd frontend && npm run build

      # 배포 (루트 디렉토리에서 실행)
      - name: Deploy to Firebase Hosting (Live)
        if: github.ref == 'refs/heads/main'
        run: npx firebase-tools deploy --only hosting --project your-project-id --non-interactive

      - name: Deploy to Firebase Hosting (Preview)
        if: github.event_name == 'pull_request'
        run: npx firebase-tools hosting:channel:deploy pr-${{ github.event.number }} --project your-project-id --non-interactive
```

## 5. 트러블슈팅

- **"Failed to get Firebase project"**: `firebase.googleapis.com` API가 꺼져 있는지 확인하세요.
- **"HTTP Error 403, Firebase Hosting API has not been used"**: `firebasehosting.googleapis.com` API를 켜야 합니다.
- **"could not find sites"**: Firebase 콘솔 > Hosting 메뉴에서 "시작하기"를 눌러 기본 사이트를 초기화해야 합니다.
