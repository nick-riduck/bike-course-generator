# 🚨 긴급 상황 대응 및 런칭 스케일업 가이드 (99)

본 문서는 트래픽 급증 시나리오 또는 대규모 유저 대상 데모/런칭 직전에 수행해야 할 인프라 확장 절차를 정리합니다.

## 1. Valhalla VM (수직 확장: Scale-up)
데이터와 설치된 프로그램(Docker 등)을 그대로 유지한 채 컴퓨터 사양만 올리는 방법입니다.

### 🛠️ 실행 순서 (GCP 콘솔 기준)
1. **VM 중지**: `Compute Engine` > `VM 인스턴스` > `valhalla-server` 선택 후 상단의 **[중지]** 클릭.
2. **사양 변경**: 
   - 중지 완료 후 **[수정]** 클릭.
   - `머신 구성` 섹션에서 머신 유형 변경.
   - **추천 사양 (런칭용)**: `e2-highcpu-16` (16 vCPU, 16GB RAM) 또는 `e2-standard-8`.
3. **저장 및 시작**: 하단의 **[저장]** 클릭 후, 다시 상단의 **[시작/재개]** 클릭.

### 💡 주의사항
- **내부 IP**: 현재 고정 내부 IP(`10.178.0.2`)를 사용 중이므로 껐다 켜도 백엔드와의 연결은 유지됩니다.
- **작업 시간**: 중지부터 재시작까지 약 1~2분 정도 소요되며, 이 동안은 경로 생성 서비스가 중단됩니다.

---

## 2. Cloud Run (수평 확장: Scale-out)
백엔드 서버의 동시 처리 능력을 늘리는 방법입니다. (서버 대수 늘리기)

### 🛠️ 실행 명령어
터미널에서 아래 명령어를 실행하여 최대 인스턴스 수를 상향합니다. (서버를 끄지 않고 즉시 반영됨)

```bash
# 최대 인스턴스를 1개에서 50개로 상향
gcloud run services update backend-fastapi \
    --region asia-northeast3 \
    --project riduck-bike-course-simulator \
    --max-instances 50
```

---

## 3. 상황 종료 후 (비용 절감: Scale-down)
데모가 끝나고 트래픽이 안정화되면 다시 사양을 낮춰야 요금 폭탄을 피할 수 있습니다.

1. **Cloud Run**: 다시 `--max-instances 5` 정도로 낮춥니다.
2. **Valhalla VM**: 다시 끄고 `e2-standard-2`로 낮춘 뒤 켭니다.

---

## 4. 체크리스트 (오픈 1시간 전)
- [ ] Valhalla VM 사양 업그레이드 완료 확인
- [ ] Cloud Run Max Instance 상향 완료 확인
- [ ] `docs/infra/03_backend_deployment_status.md`의 테스트 명령어로 최종 통신 확인
- [ ] Firebase Hosting 연동(Rewrites) 정상 작동 확인
