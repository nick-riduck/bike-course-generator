# 🏗️ Cloud Run 접근 제어 및 보안 아키텍처 검토 보고서

**Date:** 2026-02-04
**Author:** Gemini (Infrastructure Assistant)
**Issue:** GCP 조직 정책(`Domain Restricted Sharing`)으로 인한 Firebase Rewrites(IAM 인증 기반) 연동 불가 및 보안 취약성 대두.

---

## 🚨 1. 현황 및 문제점 (Problem Statement)

### 현재 아키텍처
- **Frontend:** Firebase Hosting (`riduck-bike-course-simulator.web.app`)
- **Backend:** Google Cloud Run (`backend-fastapi`)
- **Integration:** `firebase.json`의 `rewrites` 설정을 통해 `/api/**` 요청을 Cloud Run으로 터널링 시도.

### 발생한 문제 (Blocker)
1.  **조직 정책 충돌:** GCP 조직 정책 `iam.allowedPolicyMemberDomains`가 활성화되어 있어, Firebase Hosting의 내부 서비스 계정(외부 도메인 취급)에 `roles/run.invoker` 권한 부여가 불가능함.
2.  **보안 딜레마:**
    - Rewrites를 작동시키려면 Cloud Run을 `allUsers`에게 공개해야 함.
    - `allUsers`로 공개하면 인터넷 상의 누구나 백엔드 API를 직접 호출할 수 있어 **DDoS 공격 및 과금 폭탄(Instance Auto-scaling)** 위험에 노출됨.
3.  **현재 임시 조치:**
    - Cloud Run Ingress: `All` (전체 허용)
    - Cloud Run Auth: `Allow unauthenticated` (인증 없음)
    - **방어책:** `max-instances: 1` 제한 및 CORS 설정(Frontend Only) 적용.

---

## 🏗️ 2. 해결 옵션 비교 (Architecture Options)

### 🥇 옵션 1: Cloud Load Balancer (GCP Native 정석)
Cloud Run 앞에 전용 L7 로드 밸런서를 배치하여 보안과 트래픽 관리를 수행하는 방식입니다.

- **구조:** `User` -> `Global Load Balancer` -> `Cloud Run`
- **보안 구성:**
    - **Cloud Run Ingress:** `Internal and Cloud Load Balancing`으로 설정하여 **인터넷 직접 접속 원천 차단**.
    - **Cloud Armor (선택):** LB에 WAF(웹 방화벽)를 연동하여 DDoS, SQL Injection 방어.
- **장점:**
    - 구글이 권장하는 가장 안전하고 표준적인 아키텍처.
    - SSL 인증서 자동 관리 및 커스텀 도메인(`api.riduck.com`) 연결 용이.
- **단점:**
    - **고정 비용 발생:** LB 기본요금 약 $18/월 + 트래픽 비용. (Cloud Armor 별도)
    - 설정 복잡도가 높음 (Serverless NEG 구성 필요).
- **예상 비용:** 월 $20 ~ $50 (트래픽에 따라 변동)

### 🥈 옵션 2: API Gateway
API 호출을 전문적으로 관리하는 완전 관리형 게이트웨이 서비스를 사용하는 방식입니다.

- **구조:** `User` -> `API Gateway` -> `Cloud Run`
- **보안 구성:**
    - API Gateway가 클라이언트의 API Key나 Firebase Auth Token을 1차 검증.
    - 유효하지 않은 요청은 Cloud Run에 도달하기 전에 차단 (비용 절감).
- **장점:**
    - 정교한 API 사용량 제한(Rate Limiting) 및 모니터링 가능.
    - Cloud Run이 비즈니스 로직에만 집중할 수 있음.
- **단점:**
    - Cloud Run의 Ingress를 완전히 닫기 어려움 (Gateway IP가 동적이라 `All`로 열어야 하는 경우가 많음).
    - 호출 횟수당 과금되므로 트래픽 급증 시 비용 예측이 어려울 수 있음.
- **예상 비용:** 호출 100만 건당 약 $3.

### 🥉 옵션 3: Cloudflare Proxy (Hybrid 가성비)
앞단에 Cloudflare를 두고, Cloud Run은 Cloudflare의 트래픽만 허용하도록 구성하는 방식입니다.

- **구조:** `User` -> `Cloudflare (CDN/WAF)` -> `Cloud Run`
- **보안 구성:**
    - Cloudflare의 **DDoS Protection** 및 **WAF** 사용.
    - Cloud Run은 `Ingress: All`로 두되, **방화벽 규칙(Firewall Rules)**을 통해 Cloudflare IP 대역만 허용하거나, 커스텀 헤더 검증 로직 추가.
- **장점:**
    - **무료 플랜**으로도 엔터프라이즈급 보안 기능 사용 가능.
    - 설정이 간편하고 전 세계 CDN 속도 활용 가능.
- **단점:**
    - GCP 외부 서비스 의존성 생김.
    - 완벽한 Ingress 차단(Private Link)은 유료 플랜(Argo Tunnel) 필요.
- **예상 비용:** $0 (Free Plan 기준).

### 📁 옵션 4: Direct Access (MVP/임시)
현재 상태를 유지하되, 코드 레벨에서 최소한의 방어책을 구축하는 방식입니다.

- **구조:** `User` -> `Cloud Run (Public)`
- **보안 구성:**
    - **CORS:** 브라우저 기반의 타 도메인 호출 차단.
    - **Max Instances:** 1~5개로 제한하여 과금 상한선 설정.
    - **Application Rate Limiting:** FastAPI 미들웨어로 IP당 요청 횟수 제한 구현.
- **장점:** 추가 비용 0원, 즉시 구현 가능.
- **단점:** `curl` 등을 이용한 스크립트 공격에 취약. 보안 감사 시 지적 대상.

---

## 💡 3. 종합 추천 (Recommendation)

### 🚀 단기 (데모/MVP 단계)
**[옵션 4] Direct Access**를 유지하되, **[옵션 3] Cloudflare** 도입을 준비합니다.
- 현재 크레딧이 충분하지만, 데모 단계에서 복잡한 LB 구축에 시간을 쏟기보다는 기능 개발에 집중하는 것이 효율적입니다.
- `max-instances` 제한만으로도 초기 리스크는 충분히 관리 가능합니다.

### 🛡️ 중기 (정식 오픈/크레딧 활용)
**[옵션 1] Cloud Load Balancer** 도입을 강력히 권장합니다.
- **이유:** 보유 중인 GCP 크레딧(1년 제한)을 가장 가치 있게 사용하는 방법입니다.
- 보안, 성능, 확장성을 모두 잡을 수 있으며, 추후 투자 유치 시 인프라 안정성을 어필하기 좋습니다.
- Cloud Armor를 붙여 DDoS 공격에 대한 원천 봉쇄 능력을 갖추는 것이 서비스 신뢰도에 중요합니다.

### 📅 장기 (크레딧 소진 후)
비용 효율성을 고려하여 **[옵션 3] Cloudflare** 체제로 전환하거나, 서비스 규모에 따라 **[옵션 1]**을 유지합니다.
- 트래픽이 많지 않다면 LB 비용($20/월)이 부담될 수 있으므로, 그때 가서 Cloudflare 무료 플랜으로 갈아타는 유연한 전략을 취합니다.

---

## 💡 조직 정책 해제 시 베스트 시나리오 (Highly Recommended)
조직 관리자(Organization Admin)를 통해 `iam.allowedPolicyMemberDomains` 정책을 이 프로젝트에 대해서만 예외 처리하거나 해제할 경우 다음과 같은 **비용 0원의 완벽한 보안 환경** 구축이 가능합니다.
1.  **Firebase Rewrites 활성화:** 내부 서비스 계정에 `run.invoker` 권한 부여 가능.
2.  **보안 터널 완성:** Cloud Run의 Ingress를 `Internal`로 잠그고 오직 Firebase만 허용하여 인터넷 직접 접속 차단.
3.  **관리 편의성:** 프론트엔드 코드 수정 없이 `/api` 상대 경로 유지 가능.

---

## ✅ 결론 (Action Item)
1.  **당장의 조치:** Firebase Rewrites가 동작하지 않으므로, `.env.production` 파일을 생성하여 프론트엔드 빌드 시 **Cloud Run 주소를 직접 호출(Direct Call)**하도록 우회 설정한다.
2.  **관리자 협의:** 파운더/멘토 미팅 시 본 문서를 제시하며 **"조직 정책 예외 처리"**를 최우선으로 건의한다.
3.  **정책 해제 시:** `.env.production`을 삭제하고 `firebase.json`의 Rewrites 설정을 복구하여 정석 아키텍처로 회귀한다.
