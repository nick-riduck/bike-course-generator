# 1. 고정 내부 IP 예약 (Cloud Run과의 안정적인 통신을 위해 필요)
gcloud compute addresses create valhalla-internal-ip \
    --region=asia-northeast3 \
    --subnet=default \
    --project=riduck-bike-course-simulator

# 2. VM 인스턴스 생성
# - 사양: e2-standard-2 (2 vCPU, 8GB RAM)
# - OS: Ubuntu 22.04 LTS
# - 기능: Docker 자동설치, Swap 4GB 설정
gcloud compute instances create valhalla-server \
    --project=riduck-bike-course-simulator \
    --zone=asia-northeast3-a \
    --machine-type=e2-standard-2 \
    --network-interface=network=default,subnet=default,private-network-ip=valhalla-internal-ip,no-address \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=50GB \
    --boot-disk-type=pd-ssd \
    --tags=valhalla-server \
    --metadata=startup-script=\'#!/bin/bash
      # 1. 패키지 업데이트 및 Docker 설치
      apt-get update
      apt-get install -y docker.io docker-compose
      systemctl enable --now docker
      
      # 2. Swap 4GB 설정 (메모리 부족 방지)
      if [ ! -f /swapfile ]; then
        fallocate -l 4G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
      fi'

# [참고] 외부 접속 차단됨 (--no-address 옵션 적용)
# 관리 목적으로 SSH 접속이 필요할 경우 GCP 콘솔의 'IAP(Identity-Aware Proxy)'를 사용하거나
# 잠시 공인 IP를 할당해야 합니다.
