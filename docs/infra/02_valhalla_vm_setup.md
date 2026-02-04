# Valhalla VM 구축 가이드 (Private VM + Cloud NAT)

이 문서는 GCP Compute Engine(VM)에 Valhalla 경로 엔진을 구축하고, 외부 공인 IP 없이 안전하게 운영하는 방법을 설명합니다.

## 1. 네트워크 구성 (보안 필수)

VM이 외부 공격에 노출되지 않도록 사설 IP만 할당하고, 인터넷 접속(패키지 설치 등)은 Cloud NAT를 통하게 합니다.

```bash
export PROJECT_ID="riduck-bike-course-simulator"
export REGION="asia-northeast3"

gcloud config set project $PROJECT_ID

# 1. Cloud Router 생성
gcloud compute routers create valhalla-router \
    --network=default \
    --region=$REGION

# 2. Cloud NAT 생성 (VM의 인터넷 아웃바운드 허용)
gcloud compute routers nats create valhalla-nat \
    --router=valhalla-router \
    --region=$REGION \
    --auto-allocate-nat-external-ips \
    --nat-all-subnet-ip-ranges

# 3. Private Google Access 활성화 (GCS 등 구글 내부망 접속용)
gcloud compute networks subnets update default \
    --region=$REGION \
    --enable-private-ip-google-access
```

---

## 2. VM 생성

Valhalla 최소 권장 사양인 **8GB RAM**(`e2-standard-2`)으로 생성합니다.

```bash
# 1. 내부 고정 IP 예약
gcloud compute addresses create valhalla-internal-ip \
    --region=$REGION --subnet=default

# 2. VM 생성 (Docker 자동 설치 스크립트 포함)
gcloud compute instances create valhalla-server \
    --zone=${REGION}-a \
    --machine-type=e2-standard-2 \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=50GB \
    --boot-disk-type=pd-ssd \
    --network-interface=network=default,subnet=default,private-network-ip=valhalla-internal-ip,no-address \
    --tags=valhalla-server \
    --metadata=startup-script='#!/bin/bash
      # Swap 4GB 설정 (OOM 방지)
      if [ ! -f /swapfile ]; then
        fallocate -l 4G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
      fi'
```

---

## 3. 데이터 전송 (GCS 활용)

로컬의 대용량 지도 데이터를 VM으로 가장 빠르게 옮기는 방법입니다. `scp`는 느리거나 끊길 수 있습니다.

### 3.1. 로컬 -> GCS 업로드
```bash
# 버킷 생성
gcloud storage buckets create gs://riduck-valhalla-data-temp --location=$REGION

# 데이터 압축 및 업로드 (tiles 폴더 압축 권장)
tar -cf valhalla_tiles.tar valhalla_data/valhalla_tiles
gcloud storage cp valhalla_tiles.tar gs://riduck-valhalla-data-temp/

# 설정 파일 등 나머지 업로드
tar -cf rest_data.tar valhalla_data/valhalla.json valhalla_data/elevation_data docker-compose.yml
gcloud storage cp rest_data.tar gs://riduck-valhalla-data-temp/
```

### 3.2. VM 내부 권한 설정 (필수)
VM이 GCS에서 파일을 읽으려면 권한이 필요합니다.
```bash
# VM의 기본 서비스 계정 찾기
VM_SA=$(gcloud compute instances describe valhalla-server --zone=${REGION}-a --format="value(serviceAccounts[0].email)")

# 스토리지 관리자 권한 부여
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member=serviceAccount:$VM_SA \
    --role=roles/storage.admin
```

### 3.3. VM 내부 다운로드 및 실행
```bash
# VM 접속
gcloud compute ssh valhalla-server --zone=${REGION}-a

# (VM 내부) 데이터 다운로드
gcloud storage cp gs://riduck-valhalla-data-temp/valhalla_tiles.tar ~/valhalla_data/
gcloud storage cp gs://riduck-valhalla-data-temp/rest_data.tar ~

# (VM 내부) 압축 해제 및 폴더 정리
cd ~/valhalla_data
tar -xf valhalla_tiles.tar
# 중요: valhalla_tiles 폴더 구조가 맞는지 확인 ( ~/valhalla_data/valhalla_tiles/...)

cd ~
tar -xf rest_data.tar

# (VM 내부) Docker 실행
# 만약 docker 명령어가 안 되면 수동 설치 필요: curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
sudo docker compose up -d
```

---

## 4. 트러블슈팅

- **"apt-get update 무응답"**: Cloud NAT가 없어서 인터넷이 막힌 상태입니다. NAT를 생성하세요.
- **"gcloud storage cp 무응답"**: Private Google Access가 꺼져 있어서 구글 API에 접속을 못 하는 상태입니다. 서브넷 설정을 확인하세요.
- **"Permission denied (storage.objects.get)"**: VM 서비스 계정에 `roles/storage.admin` 권한이 없습니다.
- **"Docker not found"**: Startup script가 실패했을 수 있습니다. `curl -fsSL https://get.docker.com | sudo sh`로 수동 설치하세요.
